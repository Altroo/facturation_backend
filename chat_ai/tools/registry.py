from dataclasses import replace
from functools import partial
from typing import Any

from chat_ai_assistant.contracts import (
    ID,
    STRING,
    ChatAITool,
    ChatAIToolRegistry,
    object_schema,
)

from chat_ai.services.navigation import DETAILS, ROUTES
from chat_ai.tools import catalog, operations
from chat_ai.tools.documents import DOCUMENTS

DATE = {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"}
PERIOD = {
    "type": "string",
    "enum": [
        "current_month",
        "previous_month",
        "current_year",
        "previous_year",
        "custom",
    ],
}
OUTPUT = {
    "type": "object",
    "required": ["type"],
    "properties": {
        "type": {
            "enum": [
                "record_list",
                "invoice",
                "client",
                "financial_summary",
                "navigation",
                "knowledge",
                "clarification",
                "confirmation",
                "pdf",
            ]
        }
    },
    "maxProperties": 12,
}


STOCK_ROUTES = {
    "stock": "stock_balance",
    "stock_movements": "stock_movement",
    "stock_receipts": "stock_receipt",
    "stock_inventories": "stock_inventory",
}


SEARCH_ARGUMENT_DESCRIPTIONS = {
    "client_name": (
        "Customer / Client: the customer name, never the article name or reference."
        " Combine with product_name when both are requested."
    ),
    "product_name": (
        "Article / Produit: the article designation or reference on a document "
        "line. Keep the customer separately in client_name."
    ),
    "invoice_number": "Numéro de facture / Invoice number: the invoice business number, not a database ID.",
    "quote_number": "Numéro de devis / Quote number: the exact quote business number.",
    "document_number": (
        "Numéro du document / Document number: the exact pro forma, "
        "credit note or delivery note number."
    ),
    "date_from": (
        "Inclusive first date (YYYY-MM-DD). Include every requested date bound. "
        "Resolve relative dates using trusted today; do not invent a missing year."
    ),
    "date_to": (
        "Inclusive last date (YYYY-MM-DD). Include every requested date bound. "
        "Yesterday is the day before trusted today."
    ),
    "limit": (
        "Maximum number of records returned. Set the requested number explicitly "
        "when the user asks for at most/only N records (1 to 10). Default 10."
    ),
    "offset": "Number of matching records to skip for pagination. Default 0.",
    "unpaid": (
        "Impayées / Unpaid: true when the user requests invoices with a remaining "
        "unpaid balance, including partially paid invoices."
    ),
}


def described_search_properties(properties):
    return {
        name: {
            **schema,
            **(
                {"description": SEARCH_ARGUMENT_DESCRIPTIONS[name]}
                if name in SEARCH_ARGUMENT_DESCRIPTIONS
                else {}
            ),
        }
        for name, schema in properties.items()
    }


def operation_status_description(resource, adapter):
    if resource == "stock_balance":
        return (
            "État: a_approvisionner = À approvisionner (available stock below zero); "
            "minimum = Stock minimum (configured minimum > 0 and available stock from zero to minimum); "
            "disponible = Disponible (all other balances)."
        )
    choices = (
        adapter.model.TYPE_CHOICES
        if resource == "stock_movement"
        else (
            adapter.model.STATUT_CHOICES
            if resource == "logistics_order"
            else adapter.model.STATUS_CHOICES
        )
    )
    label = (
        "Phase du dossier"
        if resource == "logistics_order"
        else "Type de mouvement"
        if resource == "stock_movement"
        else "Statut"
    )
    english = {
        "opening": "Opening stock",
        "adjustment": "Adjustment",
        "receipt": "Receipt",
        "delivery": "Delivery",
        "inventory": "Inventory",
        "reversal": "Reversal",
        "draft": "Draft",
        "validated": "Validated",
        "cancelled": "Cancelled",
    }
    return (
        label
        + ": "
        + ", ".join(
            f"{value} = {title}" + (f" / {english[value]}" if value in english else "")
            for value, title in choices
        )
        + ". Include the exact enum value whenever a status or movement type is requested."
    )


def operations_schema(resources):
    """Each resource advertises only its supported filters and native statuses."""
    branches = []
    for resource in resources:
        adapter: operations.OperationAdapter = operations.OPERATIONS[resource]
        descriptions = {
            "reference": (
                "Article reference only."
                if resource in ("stock_balance", "stock_movement")
                else (
                    "Logistics order number."
                    if resource == "logistics_order"
                    else "Receipt/inventory document reference, not an article reference."
                )
            ),
            "product_name": (
                "Article designation or article reference. For receipts, inventories and "
                "logistics, searches their lines."
            ),
            "location_name": "Stock location name; expected line location for logistics orders.",
            "client_name": "Customer business name, surname or first name on related logistics lines.",
            "supplier_name": "Supplier name on the logistics order.",
        }
        properties: dict[str, dict[str, Any]] = {
            name: {**STRING, "description": descriptions[name]}
            for name in sorted(adapter.filters)
        }
        properties.update(
            resource={"const": resource},
            status={
                "enum": sorted(adapter.statuses),
                "description": operation_status_description(resource, adapter),
            },
            date_from=DATE,
            date_to=DATE,
            limit={"type": "integer", "minimum": 1, "maximum": 10},
            offset={"type": "integer", "minimum": 0, "maximum": 1000},
        )
        # Keep resource-specific meanings; common date/pagination labels are shared.
        for name in ("date_from", "date_to", "limit", "offset"):
            properties[name] = {
                **properties[name],
                "description": SEARCH_ARGUMENT_DESCRIPTIONS[name],
            }
        branches.append(object_schema(properties, ("resource",)))
    return {"type": "object", "oneOf": branches}


class ChatAIContextToolRegistry(ChatAIToolRegistry):
    def permitted(self, capabilities):
        caps = set(capabilities)
        stock = [name for name in operations.OPERATIONS if name.startswith("stock_")]
        operation_resources = list(operations.OPERATIONS) if "read" in caps else stock
        record_resources = (
            list(DOCUMENTS) + ["article", "payment"] if "read" in caps else []
        )
        record_resources += operation_resources
        if "user_admin" in caps:
            record_resources.append("user")
        navigation_resources = (
            list(ROUTES) + list(DETAILS)
            if "read" in caps
            else list(STOCK_ROUTES) + stock
        )
        if "user_admin" in caps:
            navigation_resources += ["user", "users"]
        else:
            navigation_resources = [
                name for name in navigation_resources if name not in ("user", "users")
            ]
        if "mutate" not in caps:
            navigation_resources = [
                name for name in navigation_resources if not name.endswith("_edit")
            ]
        permitted = []
        for tool in super().permitted(caps):
            if tool.name == "search_operations":
                tool = replace(
                    tool, input_schema=operations_schema(operation_resources)
                )
            elif tool.name in ("get_record", "navigate"):
                properties = dict(tool.input_schema["properties"])
                resources = (
                    record_resources
                    if tool.name == "get_record"
                    else navigation_resources
                )
                properties["resource"] = {"enum": list(dict.fromkeys(resources))}
                if tool.name == "navigate" and "read" not in caps:
                    properties.pop("invoice_number", None)
                tool = replace(
                    tool,
                    input_schema=object_schema(
                        properties, tool.input_schema["required"]
                    ),
                )
            elif tool.name == "previous_results" and "read" not in caps:
                properties = dict(tool.input_schema["properties"])
                properties["operation"] = {"enum": ["show", "open"]}
                tool = replace(
                    tool, input_schema=object_schema(properties, ("operation",))
                )
            permitted.append(tool)
        return permitted


def _execute_tool(name, executor, **arguments):
    return getattr(executor, name)(**arguments)


def registry():
    def tool(name, description, properties, required=(), capabilities=("read",)):
        if name in {
            "search_invoices",
            "search_quotes",
            "search_documents",
            "search_articles",
            "search_payments",
        }:
            properties = described_search_properties(properties)
            description += (
                " Combine all requested supported filters (AND), including status, dates "
                "and result limit; do not silently omit one."
            )
            if name == "search_articles":
                properties["product_name"] = {
                    **properties["product_name"],
                    "description": (
                        "Article / Produit: designation or reference in the article "
                        "catalogue; no document is required."
                    ),
                }
            if name == "search_payments":
                properties["status"] = {
                    **properties["status"],
                    "description": (
                        "Statut / Status: Valide = valid/validated/collected; Annulé = cancelled. "
                        "Include when explicitly requested."
                    ),
                }
        return ChatAITool(
            name,
            description,
            object_schema(properties, required),
            OUTPUT,
            partial(_execute_tool, name),
            required_capabilities=capabilities,
        )

    return ChatAIContextToolRegistry(
        [
            tool(
                "search_invoices",
                (
                    "Search invoices by exact number, client name, date interval or unpaid "
                    "balance. Dates ISO. No guessed year."
                ),
                {
                    "invoice_number": STRING,
                    "client_name": STRING,
                    "product_name": STRING,
                    "date_from": DATE,
                    "date_to": DATE,
                    "unpaid": {"type": "boolean"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                    "offset": {"type": "integer", "minimum": 0, "maximum": 1000},
                },
            ),
            tool(
                "search_quotes",
                (
                    "Find devis/quotes by client name AND product name/reference, date range or"
                    " quote number. Return authorized choices, never require an internal ID."
                ),
                {
                    "quote_number": STRING,
                    "client_name": STRING,
                    "product_name": STRING,
                    "date_from": DATE,
                    "date_to": DATE,
                    "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                    "offset": {"type": "integer", "minimum": 0, "maximum": 1000},
                },
            ),
            tool(
                "search_documents",
                (
                    "Search pro forma invoices (proforma), credit notes/factures avoir "
                    "(credit_note), or delivery notes/bons de livraison (delivery_note). "
                    "Combine client AND product filters; never require remembered IDs."
                ),
                {
                    "resource": {"enum": ["proforma", "credit_note", "delivery_note"]},
                    "document_number": STRING,
                    "client_name": STRING,
                    "product_name": STRING,
                    "date_from": DATE,
                    "date_to": DATE,
                    "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                    "offset": {"type": "integer", "minimum": 0, "maximum": 1000},
                },
                ("resource",),
            ),
            tool(
                "search_articles",
                (
                    "Find articles/products/services by reference or designation. Archived is "
                    "optional. Prices follow the existing member access."
                ),
                {
                    "query": STRING,
                    "reference": STRING,
                    "product_name": STRING,
                    "type_article": {"enum": ["Produit", "Service"]},
                    "archived": {"type": "boolean"},
                    "date_from": DATE,
                    "date_to": DATE,
                    "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                    "offset": {"type": "integer", "minimum": 0, "maximum": 1000},
                },
            ),
            tool(
                "search_payments",
                (
                    "Find règlements/payments by invoice number, client name, product, status "
                    "or dates. Valide means collected; Annulé is not collected."
                ),
                {
                    "query": STRING,
                    "invoice_number": STRING,
                    "client_name": STRING,
                    "product_name": STRING,
                    "status": {"enum": ["Valide", "Annulé"]},
                    "date_from": DATE,
                    "date_to": DATE,
                    "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                    "offset": {"type": "integer", "minimum": 0, "maximum": 1000},
                },
            ),
            ChatAITool(
                "search_users",
                (
                    "Staff-only account lookup by name or email using the existing global "
                    "account administration scope; excludes your own account."
                ),
                object_schema(
                    {
                        "query": STRING,
                        "name": STRING,
                        "email": STRING,
                        "is_active": {"type": "boolean"},
                        "date_from": DATE,
                        "date_to": DATE,
                        "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                        "offset": {"type": "integer", "minimum": 0, "maximum": 1000},
                    }
                ),
                OUTPUT,
                partial(_execute_tool, "search_users"),
                required_capabilities=("user_admin",),
            ),
            ChatAITool(
                "search_operations",
                (
                    "Find stock balances, movements, receipts, inventories, or permitted "
                    "logistics orders by product/reference/location/client/supplier. Use only "
                    "filters supported for that resource. Balance status is État, movement "
                    "status is Type de mouvement, receipt/inventory status is Statut; logistics"
                    " status is Phase du dossier. Read only."
                ),
                operations_schema(operations.OPERATIONS),
                OUTPUT,
                partial(_execute_tool, "search_operations"),
                required_capabilities=("stock_read",),
            ),
            tool(
                "get_record",
                (
                    "Retrieve a previously identified proforma, credit note, delivery note, "
                    "article, payment, user, stock record or logistics order. IDs must come "
                    "from authorized results, never guesses."
                ),
                {
                    "resource": {
                        "enum": list(DOCUMENTS)
                        + list(catalog.CATALOG)
                        + list(operations.OPERATIONS)
                    },
                    "identifier": ID,
                },
                ("resource", "identifier"),
                capabilities=("context",),
            ),
            tool(
                "get_invoice",
                "Get a specific authorized invoice. Omit invoice_id only when current page is an invoice.",
                {"invoice_id": ID},
            ),
            tool(
                "search_clients",
                "Search client name or exact client ID; use related_invoice for the current invoice client.",
                {
                    "query": STRING,
                    "client_id": ID,
                    "related_invoice": {"type": "boolean"},
                },
            ),
            tool(
                "financial_summary",
                (
                    "Existing dashboard metric: invoiced_net_ttc = invoices TTC minus active "
                    "credits, collected = valid payments, outstanding = invoice balance, "
                    "invoice_count = issued records. Not profit. Currency required."
                ),
                {
                    "metric": {
                        "enum": [
                            "invoiced_net_ttc",
                            "collected",
                            "outstanding",
                            "invoice_count",
                        ]
                    },
                    "period": PERIOD,
                    "currency": {"enum": ["MAD", "EUR", "USD"]},
                    "date_from": DATE,
                    "date_to": DATE,
                },
                ("metric", "period", "currency"),
            ),
            tool(
                "list_payments",
                "Latest valid payments in the current company; optional date range.",
                {"date_from": DATE, "date_to": DATE},
            ),
            tool(
                "navigate",
                (
                    "Explicit request to open an authorized page or a specific invoice/client. "
                    "Supply ID or invoice_number. Never a URL."
                ),
                {
                    "resource": {"enum": list(ROUTES) + list(DETAILS)},
                    "identifier": ID,
                    "invoice_number": STRING,
                },
                ("resource",),
                capabilities=("context",),
            ),
            tool(
                "previous_results",
                "Show or open previous authorized results by 1-based index. Unpaid filtering applies only to invoices.",
                {
                    "operation": {"enum": ["show", "unpaid", "open"]},
                    "index": {"type": "integer", "minimum": 1, "maximum": 10},
                },
                ("operation",),
                capabilities=("context",),
            ),
            ChatAITool(
                "prepare_change",
                (
                    "Prepare an edit or deletion of ONE authorized invoice, quote, proforma, "
                    "credit note, delivery note or client for human confirmation. Never "
                    "executes it. Changes: invoice remarque/termes_paiement/date_echeance; "
                    "client raison_sociale/nom/prenom/adresse. Quotes allow "
                    "remarque/date_echeance only. Credit notes allow remarque only and must be "
                    "Brouillon; delivery notes allow remarque/date_echeance; proformas use "
                    "invoice fields. Other edits use the existing form."
                ),
                object_schema(
                    {
                        "resource": {
                            "enum": [
                                "invoice",
                                "client",
                                "quote",
                                "proforma",
                                "credit_note",
                                "delivery_note",
                            ]
                        },
                        "identifier": ID,
                        "invoice_number": STRING,
                        "operation": {"enum": ["update", "delete"]},
                        "changes": object_schema(
                            {
                                k: {"type": ["string", "null"], "maxLength": 2000}
                                for k in [
                                    "remarque",
                                    "termes_paiement",
                                    "date_echeance",
                                    "raison_sociale",
                                    "nom",
                                    "prenom",
                                    "adresse",
                                ]
                            }
                        ),
                    },
                    ("resource", "operation"),
                ),
                OUTPUT,
                partial(_execute_tool, "prepare_change"),
                required_capabilities=("mutate",),
                classification="proposal",
            ),
            tool(
                "invoice_pdf",
                "Offer a PDF of an invoice only with existing print rights; requires invoice_id.",
                {"invoice_id": ID, "invoice_number": STRING},
            ),
            tool(
                "knowledge",
                (
                    "Retrieve approved instructions, invoice creation workflow, payment/status "
                    "meanings or financial definitions."
                ),
                {"query": {"type": "string", "minLength": 2, "maxLength": 300}},
                ("query",),
                capabilities=("context",),
            ),
        ]
    )
