"""Public list-column ordering, applied to the filtered dataset before pagination."""

from django.db.models import (
    Case,
    CharField,
    Count,
    DecimalField,
    F,
    OuterRef,
    Q,
    Subquery,
    Sum,
    TextField,
    Value,
    When,
)
from django.db.models.functions import (
    Cast,
    Coalesce,
    Concat,
    Greatest,
    Lower,
    NullIf,
    Trim,
)


def user_name(prefix):
    return Coalesce(
        NullIf(
            Trim(
                Concat(
                    F(f"{prefix}__first_name"), Value(" "), F(f"{prefix}__last_name")
                )
            ),
            Value(""),
        ),
        F(f"{prefix}__email"),
        output_field=CharField(),
    )


def client_name(prefix):
    return Case(
        When(
            Q(**{f"{prefix}__client_type__in": ["PM", "CD"]})
            & ~Q(**{f"{prefix}__raison_sociale": ""})
            & Q(**{f"{prefix}__raison_sociale__isnull": False}),
            then=F(f"{prefix}__raison_sociale"),
        ),
        When(
            **{f"{prefix}__client_type": "PP"},
            then=Trim(Concat(F(f"{prefix}__nom"), Value(" "), F(f"{prefix}__prenom"))),
        ),
        default=F(f"{prefix}__code_client"),
        output_field=CharField(),
    )


def _direct(names):
    return {name: F(name) for name in names.split()}


def _stock_fields(queryset):
    from logistique.models import LogisticsOrderLine
    from stock.services import INCOMING_EXCLUDED_STATUSES

    money = DecimalField(max_digits=16, decimal_places=3)
    available = F("physical_quantity") - F("reserved_quantity")
    incoming = (
        LogisticsOrderLine.objects.filter(
            commande__company_id=OuterRef("company_id"),
            commande__statut_commande_lancement="Terminée",
            expected_emplacement_id=OuterRef("emplacement_id"),
            article_id=OuterRef("article_id"),
        )
        .exclude(commande__statut_global="Annulé")
        .exclude(commande__statut__in=INCOMING_EXCLUDED_STATUSES)
        .order_by()
        .values("article_id")
        .annotate(total=Sum(F("quantity") - F("received_quantity")))
        .values("total")[:1]
    )
    queryset = queryset.alias(
        _sort_available=available,
        _sort_incoming=Greatest(
            Coalesce(Subquery(incoming), Value(0), output_field=money),
            Value(0),
            output_field=money,
        ),
    )
    fields = _direct("physical_quantity reserved_quantity")
    fields.update(
        {
            "article_reference": F("article__reference"),
            "article_designation": F("article__designation"),
            "emplacement_name": F("emplacement__nom"),
            "available_quantity": F("_sort_available"),
            "incoming_quantity": F("_sort_incoming"),
            "projected_quantity": F("_sort_available") + F("_sort_incoming"),
            "stock_state": Case(
                When(_sort_available__lt=0, then=Value("a_approvisionner")),
                When(
                    article__stock_minimum__gt=0,
                    _sort_available__lte=F("article__stock_minimum"),
                    then=Value("minimum"),
                ),
                default=Value("disponible"),
                output_field=CharField(),
            ),
        }
    )
    return queryset, fields


def _fields(queryset, field):
    model = queryset.model._meta.label_lower
    common_user = _direct(
        "first_name last_name email gender is_staff is_active date_joined last_login"
    )
    maps = {
        "accounts.customuser": common_user,
        "company.company": _direct(
            "raison_sociale ICE nom_responsable email telephone nbr_employe date_created"
        ),
        "client.client": {
            **_direct("code_client client_type raison_sociale nom prenom date_created"),
            "ville_name": F("ville__nom"),
        },
        "article.article": _direct(
            "reference type_article designation prix_achat prix_vente date_created"
        ),
        "reglement.reglement": {
            **_direct("montant date_reglement statut"),
            "facture_client_numero": F("facture_client__numero_facture"),
            "client_name": client_name("facture_client__client"),
            "mode_reglement_name": F("mode_reglement__nom"),
        },
        "stock.stockmovement": {
            **_direct("movement_type quantity balance_after note date_created"),
            "article_reference": F("balance__article__reference"),
            "article_designation": F("balance__article__designation"),
            "emplacement_name": F("balance__emplacement__nom"),
            "actor_name": user_name("actor"),
        },
        "stock.stockreceipt": {
            **_direct("status date_created"),
            "reference": Coalesce(
                NullIf(F("reference"), Value("")),
                Concat(Value("REC-"), Cast("pk", CharField())),
            ),
            "logistics_order_number": F("logistics_order__numero_commande"),
            "created_by_name": user_name("created_by"),
        },
        "stock.inventorysession": {
            **_direct("status date_created"),
            "reference": Coalesce(
                NullIf(F("reference"), Value("")),
                Concat(Value("INV-"), Cast("pk", CharField())),
            ),
            "emplacement_name": F("emplacement__nom"),
        },
        "logistique.logisticsorder": _direct(
            "numero_commande fournisseur date_prevue statut_paiement statut_titre_importation cout_total"
        ),
    }
    if model == "stock.stockbalance":
        return _stock_fields(queryset)
    if model == "article.article" and field == "available_quantity":
        from stock.models import StockBalance

        balances = (
            StockBalance.objects.filter(
                article_id=OuterRef("pk"), emplacement_id=OuterRef("emplacement_id")
            )
            .order_by("id")
            .annotate(available=F("physical_quantity") - F("reserved_quantity"))
            .values("available")[:1]
        )
        maps[model][field] = Case(
            When(
                company__stock_management_enabled=True,
                type_article__iexact="Produit",
                then=Coalesce(Subquery(balances), Value(0)),
            ),
            default=Value(0),
            output_field=DecimalField(max_digits=16, decimal_places=3),
        )
    documents = {
        "devi.devi",
        "facture_proforma.factureproforma",
        "facture_client.factureclient",
        "facture_avoir.factureavoir",
        "bon_de_livraison.bondelivraison",
    }
    if model in documents:
        # Only expose public columns that exist on this document model.
        names = "numero_devis numero_facture numero_avoir numero_bon_livraison numero_demande_prix_client numero_bon_commande_client date_devis date_facture date_avoir date_bon_livraison statut total_ttc_apres_remise"
        concrete = {f.name for f in queryset.model._meta.fields}
        maps[model] = _direct(" ".join(n for n in names.split() if n in concrete))
        maps[model].update(
            client_name=client_name("client"),
            lignes_count=Count("lignes", distinct=True),
        )
        if model == "facture_avoir.factureavoir":
            maps[model]["motif_avoir_label"] = Case(
                *[
                    When(motif_avoir=value, then=Value(str(label)))
                    for value, label in queryset.model.MOTIF_CHOICES
                ],
                default=F("motif_avoir"),
                output_field=CharField(),
            )
            maps[model]["facture_origine_numero"] = F("facture_origine__numero_facture")
        if model == "facture_client.factureclient" and field in {
            "nombre_paiements",
            "total_paye",
            "reste_a_payer",
            "statut_paiement",
        }:
            from facture_client.views import annotate_payment_and_avoir_totals

            queryset = annotate_payment_and_avoir_totals(queryset).alias(
                _sort_remaining=F("net_total") - F("total_paid")
            )
            maps[model].update(
                nombre_paiements=F("payment_count"),
                total_paye=F("total_paid"),
                reste_a_payer=F("_sort_remaining"),
                statut_paiement=Case(
                    When(_sort_remaining__lte=0, then=Value("Payée")),
                    When(total_paid__gt=0, then=Value("Partiellement payée")),
                    default=Value("Non payée"),
                ),
            )
    return queryset, maps.get(model, {})


def apply_list_ordering(queryset, query_params):
    ordering = query_params.get("ordering", "")
    if not ordering or not hasattr(queryset, "model"):
        return queryset
    descending = ordering.startswith("-")
    field = ordering[1:] if descending else ordering
    # These display values depend on the full workflow and ordered, deduplicated
    # line labels. Reuse their business logic, on the server, before slicing.
    if queryset.model._meta.label_lower == "logistique.logisticsorder" and field in {
        "clients_display",
        "projects_display",
        "statut_global",
    }:
        from logistique.serializers import LogisticsOrderListSerializer

        getter = getattr(LogisticsOrderListSerializer, f"get_{field}")
        return sorted(
            queryset,
            key=lambda row: ((getter(row) or "").casefold(), row.pk),
            reverse=descending,
        )
    queryset, fields = _fields(queryset, field)
    expression = fields.get(field)
    if expression is None:
        return queryset
    # Resolve aliases/related fields to sort names case-insensitively and numbers
    # numerically. A primary-key tie breaker keeps page boundaries stable.
    resolved = expression.resolve_expression(queryset.query)
    if isinstance(resolved.output_field, (CharField, TextField)):
        expression = Lower(expression)
    queryset = queryset.alias(_list_ordering_value=expression)
    order = F("_list_ordering_value")
    return queryset.order_by(
        order.desc(nulls_last=True) if descending else order.asc(nulls_last=True),
        "-pk" if descending else "pk",
    )
