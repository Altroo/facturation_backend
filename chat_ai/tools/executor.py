import json
import time
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

from chat_ai_assistant.contracts import (
    ChatAIError,
)
from django.conf import settings
from django.db import DatabaseError, connection, transaction
from django.db.models import F, Q
from django.utils import timezone
from jsonschema import Draft202012Validator

from account.models import CustomUser
from chat_ai.labels import ENGLISH_FORM_LABELS, FIELD_LABELS
from chat_ai.models import AuditEvent
from chat_ai.security import authorize, authorize_context
from chat_ai.services.actions import prepare
from chat_ai.services.knowledge import ChatAIKnowledgeService
from chat_ai.services.navigation import DETAILS, ROUTES, ChatAINavigationResolver
from chat_ai.tools import catalog, operations
from chat_ai.tools.documents import DOCUMENTS, scoped_queryset
from chat_ai.tools.documents import card as document_card
from chat_ai.tools.documents import search as search_documents
from chat_ai.tools.registry import STOCK_ROUTES, registry
from chat_ai.utils import parse_dates, period_dates
from client.models import Client
from core.nectar import is_nectar_company_id
from core.permissions import can_create, can_delete, can_print, can_update
from dashboard.views import CollectionRateView, KPICardsWithTrendsView
from devi.filters import DeviFilter
from devi.models import Devi
from facture_client.filters import FactureClientFilter
from facture_client.models import FactureClient
from facture_client.serializers import FactureClientPaymentFieldsMixin
from facture_client.views import annotate_payment_and_avoir_totals


class ChatAIToolExecutor:
    def __init__(
        self,
        user_id,
        company_id,
        correlation_id,
        state=None,
        context=None,
        audit=True,
        instruction=None,
    ):
        self.user_id, self.company_id, self.correlation_id = (
            user_id,
            company_id,
            correlation_id,
        )
        self.state = dict(state or {})
        self.context = context or {}
        self.audit = audit
        self.instruction = instruction or ""
        self.registry = registry()
        self.calls = 0

    def authorize(self):
        return authorize(self.user_id, self.company_id)

    def authorize_context(self):
        return authorize_context(self.user_id, self.company_id)

    def authorize_resource(self, resource):
        self.authorize_context()
        if not isinstance(resource, str):
            raise ChatAIError("INVALID_ARGUMENTS")
        normalized = STOCK_ROUTES.get(resource, resource.removesuffix("_edit"))
        if normalized in operations.OPERATIONS:
            return operations.authorize(self, normalized)
        if normalized in ("user", "users"):
            return catalog.authorize(self, "user")
        if normalized in ROUTES or normalized in DETAILS:
            return self.authorize()
        raise ChatAIError("INVALID_ARGUMENTS")

    def capabilities(self):
        context = self.authorize_context()

        caps = ["context", "stock_read"]
        if context.user.is_staff:
            caps.append("user_admin")
        if context.membership is not None:
            caps.append("read")
            if can_create(context.user, self.company_id):
                caps.append("create")
            if can_update(context.user, self.company_id) or can_delete(
                context.user, self.company_id
            ):
                caps.append("mutate")
        return caps

    def _authorize_call(self, name, args):
        self.authorize_context()
        if name in ("search_operations", "get_record", "navigate"):
            self.authorize_resource(args["resource"])
        elif name == "previous_results":
            if self.state.get("resource"):
                self.authorize_resource(self.state["resource"])
        elif name == "search_users":
            self.authorize_resource("user")
        elif name == "knowledge":
            self.authorize_context()  # Retrieval filters document capabilities before reading content.
        else:
            self.authorize()

    def execute(self, name, args):
        started = time.monotonic()
        outcome = "INTERNAL_ERROR"
        try:
            self.authorize_context()
            tool = self.registry.validate(name, args)
            if not set(tool.required_capabilities) <= set(self.capabilities()):
                raise ChatAIError("PERMISSION_DENIED")
            self._authorize_call(name, args)
            self.calls += 1
            if self.calls > 3:
                raise ChatAIError("TOOL_LIMIT")
            with transaction.atomic():
                if connection.vendor == "postgresql":
                    with connection.cursor() as cursor:
                        cursor.execute("SET LOCAL statement_timeout = '5000ms'")
                result = tool.handler(self, **args)
                if (
                    list(Draft202012Validator(tool.output_schema).iter_errors(result))
                    or len(json.dumps(result, ensure_ascii=False)) > 18000
                ):
                    raise ChatAIError("INTERNAL_ERROR")
                self._authorize_call(name, args)
                if not set(tool.required_capabilities) <= set(self.capabilities()):
                    raise ChatAIError("PERMISSION_DENIED")
            outcome = "allowed"
            return result
        except ChatAIError as exc:
            outcome = exc.code
            raise
        except DatabaseError as exc:
            outcome = "TOOL_TIMEOUT"
            raise ChatAIError(outcome) from exc
        finally:
            if self.audit:
                AuditEvent.objects.create(
                    user_id=self.user_id,
                    company_id=self.company_id,
                    tool=name if name in self.registry.tools else "unknown",
                    outcome=outcome,
                    correlation_id=self.correlation_id,
                    model_version=settings.CHAT_AI_MODEL_ID,
                    duration_ms=max(0, int((time.monotonic() - started) * 1000)),
                )

    def invoices(self):
        self.authorize()
        return annotate_payment_and_avoir_totals(
            FactureClient.objects.filter(
                company_id=self.company_id, client__company_id=self.company_id
            ).select_related("client")
        )

    def invoice(self, id):
        obj = self.invoices().filter(pk=id).first()
        if obj is None:
            raise ChatAIError("NOT_FOUND")
        return obj

    def invoice_card(self, obj):
        self.authorize()
        if (
            obj.company_id != self.company_id
            or obj.client.company_id != self.company_id
        ):
            raise ChatAIError("NOT_FOUND")
        calc = FactureClientPaymentFieldsMixin()
        return {
            "id": obj.pk,
            "number": obj.numero_facture,
            "client": str(obj.client)[:200],
            "date": obj.date_facture.isoformat(),
            "status": obj.statut,
            "currency": obj.devise,
            "total_ttc": str(obj.total_ttc_apres_remise),
            "paid": str(calc.get_total_paye(obj)),
            "outstanding": str(calc.get_reste_a_payer(obj)),
            "payment_status": calc.get_statut_paiement(obj),
            "navigation": ChatAINavigationResolver.resolve(
                "invoice", self.company_id, obj.pk
            ),
        }

    def save_results(self, resource, items):
        self.state = {
            "resource": resource,
            "ids": [x["id"] for x in items],
            "expires_at": (timezone.now() + timedelta(minutes=30)).isoformat(),
        }

    def search_invoices(self, **args):
        start, end = parse_dates(args)
        filters = {}
        for k, v in [
            ("invoice_number", "numero_facture"),
            ("client_name", "client_name__icontains"),
        ]:
            if args.get(k):
                filters[v] = args[k]
        if start:
            filters["date_after"] = start
        if end:
            filters["date_before"] = end
        qs = FactureClientFilter(filters, queryset=self.invoices()).qs
        if args.get("unpaid"):
            qs = qs.filter(net_total__gt=F("total_paid"))
        if args.get("product_name"):
            qs = qs.filter(
                Q(lignes__article__designation__icontains=args["product_name"])
                | Q(lignes__article__reference__icontains=args["product_name"]),
                lignes__article__company_id=self.company_id,
            ).distinct()
        offset = args.get("offset", 0)
        limit = args.get("limit", 10)
        page_end = offset + limit + 1
        records = list(qs.order_by("-date_facture", "-pk")[offset:page_end])
        items = [self.invoice_card(x) for x in records[:limit]]
        self.save_results("invoice", items)
        return {
            "type": "record_list",
            "resource": "invoice",
            "items": items,
            "has_more": len(records) > limit,
            "next_offset": offset + limit if len(records) > limit else None,
        }

    def quotes(self):
        self.authorize()
        return Devi.objects.filter(
            company_id=self.company_id, client__company_id=self.company_id
        ).select_related("client")

    def quote_card(self, obj):
        self.authorize()
        if (
            obj.company_id != self.company_id
            or obj.client.company_id != self.company_id
        ):
            raise ChatAIError("NOT_FOUND")
        return {
            "id": obj.pk,
            "number": obj.numero_devis,
            "client": str(obj.client)[:200],
            "date": obj.date_devis.isoformat(),
            "status": obj.statut,
            "currency": obj.devise,
            "total_ttc": str(obj.total_ttc_apres_remise),
            "navigation": ChatAINavigationResolver.resolve(
                "quote", self.company_id, obj.pk
            ),
        }

    def search_quotes(self, **args):
        start, end = parse_dates(args)
        filters = {}
        if args.get("client_name"):
            filters["client_name__icontains"] = args["client_name"]
        if start:
            filters["date_after"] = start
        if end:
            filters["date_before"] = end
        qs = DeviFilter(filters, queryset=self.quotes()).qs
        if args.get("quote_number"):
            qs = qs.filter(numero_devis=args["quote_number"])
        if args.get("product_name"):
            qs = qs.filter(
                Q(lignes__article__designation__icontains=args["product_name"])
                | Q(lignes__article__reference__icontains=args["product_name"]),
                lignes__article__company_id=self.company_id,
            ).distinct()
        offset = args.get("offset", 0)
        limit = args.get("limit", 10)
        page_end = offset + limit + 1
        records = list(qs.order_by("-date_devis", "-pk")[offset:page_end])
        items = [self.quote_card(x) for x in records[:limit]]
        self.save_results("quote", items)
        return {
            "type": "record_list",
            "resource": "quote",
            "items": items,
            "has_more": len(records) > limit,
            "next_offset": offset + limit if len(records) > limit else None,
        }

    def get_invoice(self, invoice_id=None):
        self.authorize()
        id = invoice_id or self.context.get("invoice_id")
        if not id:
            raise ChatAIError("INVALID_ARGUMENTS")
        item = self.invoice_card(self.invoice(id))
        self.save_results("invoice", [item])
        return {"type": "invoice", "items": [item]}

    def search_documents(self, resource, **args):
        return search_documents(self, resource, **args)

    def search_clients(self, query="", client_id=None, related_invoice=False):
        self.authorize()
        if related_invoice:
            id = self.context.get("invoice_id")
            if not id:
                raise ChatAIError("INVALID_ARGUMENTS")
            client_id = self.invoice(id).client_id
        qs = Client.objects.filter(company_id=self.company_id)
        if client_id:
            qs = qs.filter(pk=client_id)
        if query:
            qs = catalog.filter_words(
                qs, query, ("raison_sociale", "nom", "prenom", "code_client")
            )
        items = [
            {
                "id": x.pk,
                "name": str(x)[:200],
                "code": x.code_client,
                "navigation": ChatAINavigationResolver.resolve(
                    "client", self.company_id, x.pk
                ),
            }
            for x in qs.order_by("pk")[:10]
        ]
        if client_id and not items:
            raise ChatAIError("NOT_FOUND")
        self.save_results("client", items)
        return {"type": "record_list", "resource": "client", "items": items}

    def financial_summary(self, **args):
        self.authorize()
        start, end = period_dates(args)
        currency = args["currency"]
        metric = args["metric"]
        request = SimpleNamespace(
            user=CustomUser.objects.get(pk=self.user_id),
            query_params={
                "company_id": str(self.company_id),
                "date_from": start.isoformat(),
                "date_to": end.isoformat(),
                "devise": currency,
            },
        )
        if metric in ("invoiced_net_ttc", "collected"):
            source = CollectionRateView.get(request).data
            value = Decimal(
                str(
                    source[
                        (
                            "total_invoiced"
                            if metric == "invoiced_net_ttc"
                            else "total_collected"
                        )
                    ]
                )
            )
        elif metric == "outstanding":
            source = KPICardsWithTrendsView.calculate_kpi_for_currency(
                currency, start, end, self.company_id, start, end - timedelta(days=7)
            )
            value = Decimal(str(source["outstanding_receivables"]["value"]))
        else:
            value = FactureClient.objects.filter(
                client__company_id=self.company_id,
                company_id=self.company_id,
                date_facture__range=(start, end),
                devise=currency,
            ).count()
        return {
            "type": "financial_summary",
            "metric": metric,
            "value": str(value) if metric == "invoice_count" else format(value, ".2f"),
            "currency": currency,
            "period": {"from": start.isoformat(), "to": end.isoformat()},
            "basis": (
                "Existing dashboard calculation: all invoice statuses, TTC less active "
                "credit notes; valid payments by payment date. Outstanding uses current "
                "balances of invoices issued in the period. Not profit."
            ),
        }

    def search_articles(self, **args):
        return catalog.search(self, "article", **args)

    def search_payments(self, **args):
        return catalog.search(self, "payment", **args)

    def search_users(self, **args):
        self.authorize_context()
        result = catalog.search(self, "user", **args)
        self.authorize_context()
        return result

    def search_operations(self, resource, **args):
        self.authorize_context()
        result = operations.search(self, resource, **args)
        self.authorize_context()
        return result

    def list_payments(self, **args):
        return catalog.search(self, "payment", status="Valide", **args)

    def read_records(self, resource, ids):
        """Refresh exact references without rerunning a broader search."""
        self.authorize_resource(resource)
        if (
            not isinstance(ids, list)
            or len(ids) > 10
            or any(type(id) is not int or id < 1 for id in ids)
        ):
            raise ChatAIError("INVALID_ARGUMENTS")
        if resource in catalog.CATALOG:
            catalog.authorize(self, resource)
            qs = catalog.scoped_queryset(
                self.company_id, resource, user_id=self.user_id
            )
            by_id = {obj.pk: obj for obj in qs.filter(pk__in=ids)}
            items = [
                catalog.card(resource, by_id[id], self.company_id, user_id=self.user_id)
                for id in ids
                if id in by_id
            ]
            catalog.authorize(self, resource)
        elif resource in operations.OPERATIONS:
            operations.authorize(self, resource)
            by_id = {
                obj.pk: obj
                for obj in operations.scoped_queryset(self.company_id, resource).filter(
                    pk__in=ids
                )
            }
            items = [
                operations.card(resource, by_id[id], self.company_id)
                for id in ids
                if id in by_id
            ]
            operations.authorize(self, resource)
        elif resource in DOCUMENTS:
            by_id = {
                obj.pk: obj
                for obj in scoped_queryset(self.company_id, resource).filter(pk__in=ids)
            }
            items = [
                document_card(resource, by_id[id], self.company_id)
                for id in ids
                if id in by_id
            ]
        elif resource == "invoice":
            by_id = {obj.pk: obj for obj in self.invoices().filter(pk__in=ids)}
            items = [self.invoice_card(by_id[id]) for id in ids if id in by_id]
        elif resource == "quote":
            by_id = {obj.pk: obj for obj in self.quotes().filter(pk__in=ids)}
            items = [self.quote_card(by_id[id]) for id in ids if id in by_id]
        elif resource == "client":
            items = []
            for id in ids:
                try:
                    items.extend(self.search_clients(client_id=id)["items"])
                except ChatAIError as exc:
                    if exc.code != "NOT_FOUND":
                        raise
        else:
            raise ChatAIError("INVALID_ARGUMENTS")
        self.authorize_resource(resource)
        return items

    def get_record(self, resource, identifier):
        self.authorize_resource(resource)
        if resource in catalog.CATALOG:
            result = catalog.get(self, resource, identifier)
        elif resource in operations.OPERATIONS:
            result = operations.detail(self, resource, identifier)
        else:
            items = self.read_records(resource, [identifier])
            if not items:
                raise ChatAIError("NOT_FOUND")
            self.save_results(resource, items)
            result = {"type": "record_list", "resource": resource, "items": items}
        self.authorize_resource(resource)
        return result

    def navigate(self, resource, identifier=None, invoice_number=None):
        self.authorize_resource(resource)
        if resource in ("invoice", "invoice_edit"):
            if invoice_number:
                ids = list(
                    self.invoices()
                    .filter(numero_facture=invoice_number)
                    .values_list("pk", flat=True)[:2]
                )
                if not ids:
                    raise ChatAIError("NOT_FOUND")
                if len(ids) != 1:
                    raise ChatAIError("MULTIPLE_MATCHES")
                identifier = ids[0]
            if identifier is None:
                identifier = self.context.get("invoice_id")
            self.invoice(identifier)
        elif resource in ("quote", "quote_edit"):
            if not self.quotes().filter(pk=identifier).exists():
                raise ChatAIError("NOT_FOUND")
        elif resource.removesuffix("_edit") in DOCUMENTS:
            if invoice_number is not None:
                raise ChatAIError("INVALID_ARGUMENTS")
            if (
                not scoped_queryset(self.company_id, resource.removesuffix("_edit"))
                .filter(pk=identifier)
                .exists()
            ):
                raise ChatAIError("NOT_FOUND")
        elif resource in catalog.CATALOG or resource in operations.OPERATIONS:
            if invoice_number is not None:
                raise ChatAIError("INVALID_ARGUMENTS")
            if not self.read_records(resource, [identifier]):
                raise ChatAIError("NOT_FOUND")
        elif resource == "users":
            catalog.authorize(self, "user")
            if identifier is not None or invoice_number is not None:
                raise ChatAIError("INVALID_ARGUMENTS")
        elif resource in ("client", "client_edit"):
            if not Client.objects.filter(
                pk=identifier, company_id=self.company_id
            ).exists():
                raise ChatAIError("NOT_FOUND")
        elif identifier is not None or invoice_number is not None:
            raise ChatAIError("INVALID_ARGUMENTS")
        if resource.endswith("_edit"):
            if not can_update(self.authorize().user, self.company_id):
                raise ChatAIError("PERMISSION_DENIED")
        self.authorize_resource(resource)
        return {
            "type": "navigation",
            "target": ChatAINavigationResolver.resolve(
                resource, self.company_id, identifier
            ),
        }

    def previous_results(self, operation, index=None):
        self.authorize_context()
        if (
            not self.state.get("ids")
            or self.state.get("expires_at", "") < timezone.now().isoformat()
        ):
            raise ChatAIError("CONTEXT_EXPIRED")
        ids = self.state["ids"]
        resource = self.state["resource"]
        self.authorize_resource(resource)
        if operation == "open":
            if type(index) is not int or not 1 <= index <= min(10, len(ids)):
                raise ChatAIError("INVALID_ARGUMENTS")
            return self.navigate(resource, identifier=ids[index - 1])
        if operation == "show":
            items = self.read_records(resource, ids)
            self.save_results(resource, items)
            return {"type": "record_list", "resource": resource, "items": items}
        if operation != "unpaid" or resource != "invoice":
            raise ChatAIError("INVALID_ARGUMENTS")
        self.authorize()
        by_id = {x.pk: x for x in self.invoices().filter(pk__in=ids)}
        items = []
        for id in ids:
            if id not in by_id:
                continue
            obj = by_id[id]
            if obj.net_total <= obj.total_paid:
                continue
            items.append(self.invoice_card(obj))
        self.authorize()
        self.save_results("invoice", items)
        return {"type": "record_list", "resource": "invoice", "items": items}

    def output_labels(self):

        self.authorize_context()
        english = self.context.get("interface_language") == "en"
        labels = {**FIELD_LABELS, **(ENGLISH_FORM_LABELS if english else {})}
        # Same company detection and article price labels as articles-form.tsx.
        if is_nectar_company_id(self.company_id):
            labels["prix_vente"] = "Price excl. tax" if english else "Prix H.T."
        return labels

    def authorize_knowledge(self, documents):
        self.authorize_context()
        sources = [
            {"document_id": doc["document_id"], "version": doc["version"]}
            for doc in documents
        ]
        if not ChatAIKnowledgeService.sources_authorized(
            sources, self.company_id, self.capabilities()
        ):
            raise ChatAIError("CONTEXT_EXPIRED")

    def knowledge(self, query):
        self.authorize_context()
        return {
            "type": "knowledge",
            "documents": ChatAIKnowledgeService().retrieve(
                query, self.company_id, self.capabilities()
            ),
        }

    def prepare_change(
        self, resource, operation, identifier=None, invoice_number=None, changes=None
    ):
        self.authorize()

        if invoice_number:
            if resource != "invoice":
                raise ChatAIError("INVALID_ARGUMENTS")
            identifier = self.resolve_invoice_number(invoice_number)
        if not identifier:
            raise ChatAIError("INVALID_ARGUMENTS")
        return prepare(self, resource, identifier, operation, changes)

    def resolve_invoice_number(self, number):
        ids = list(
            self.invoices()
            .filter(numero_facture=number)
            .values_list("pk", flat=True)[:2]
        )
        if not ids:
            raise ChatAIError("NOT_FOUND")
        if len(ids) != 1:
            raise ChatAIError("MULTIPLE_MATCHES")
        return ids[0]

    def invoice_pdf(self, invoice_id=None, invoice_number=None):

        id = (
            self.resolve_invoice_number(invoice_number)
            if invoice_number
            else invoice_id or self.context.get("invoice_id")
        )
        obj = self.invoice(id)
        if not can_print(self.authorize().user, self.company_id) or obj.statut not in (
            "Brouillon",
            "Accepté",
        ):
            raise ChatAIError("PERMISSION_DENIED")
        return {
            "type": "pdf",
            "invoice_id": obj.pk,
            "company_id": self.company_id,
            "number": obj.numero_facture,
        }
