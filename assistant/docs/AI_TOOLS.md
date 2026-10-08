# Chat AI Assistant tools

Current source contract, reviewed 2026-10-08. The Django adapter registers **17 tools** for `facturation`. Resource identifiers below are internal API keys; users see verified application labels. This is implemented coverage, not a claim that every Facturation action is supported or that the model has met acceptance targets.

## Execution contract

Each `ChatAITool` declares its name, description, application, strict input schema, output schema, capabilities, read/proposal classification, timeout and audit classification. `ChatAIToolExecutor.execute` resolves trusted context, validates the registered tool/arguments, enforces fresh native capability and resource permissions, bounds execution, validates the result, rechecks authorization and records an audit outcome.

`registry().permitted(capabilities)` narrows mixed-resource schemas before the model sees them. The multilingual `shortlist` reduces the prompt catalog but never grants permission. Ordinary tools require company membership; stock and staff-user exceptions are described in [AI_SECURITY.md](AI_SECURITY.md).

The planner chooses one tool or the provider's separate `clarify` function. `clarify` is **not** an eighteenth backend business tool: it accepts only `reason=missing_details|ambiguous_metric|unsupported` and `language=fr|en`; the backend writes its text. Bare slash commands can return usage without invoking a model. Natural descriptions such as a client plus a product are valid search inputs; internal record IDs are not required from users.

## Module shortcuts and access questions

`chat_ai/shortcut_catalog.py` is the single source of permitted module commands, English/French labels and examples. The capabilities API returns the filtered catalogue for each authorized company; the frontend renders it. It mirrors the existing read, stock-superuser, staff-user, edit, delete and print policies. Selecting a shortcut does not grant any permission, and every actual tool invocation still reauthorizes.

Bare module commands select existing read tools: invoices, quotes, pro formas, credit notes, delivery notes, clients, articles, payments, stock balances/movements/receipts/inventories, logistics and staff-only users. Descriptive arguments remain available to the planner; the module prefix supplies a trusted shortlist hint while the original user message, language and every supplied filter remain unchanged. Exact module-access questions return verified access and usage only, with no model call or business query. Compound requests are not treated as capability questions. These handlers are application behavior and do not change the frozen raw-model score.

## Registered tools

Common search limits, where exposed: `limit` 1–10, `offset` 0–1000, ISO `date_from`/`date_to`. Unsupported fields are rejected. Company/user identity is never a tool argument.

| Tool | Accepted intent and principal arguments | Result / authorization |
| --- | --- | --- |
| `search_invoices` | `invoice_number`, `client_name`, `product_name`, dates, `unpaid`, pagination | Company-scoped invoice cards with native payment calculations; member read |
| `search_quotes` | `quote_number`, client **and** product, dates, pagination | Devis cards; member read |
| `search_documents` | Required `resource=proforma|credit_note|delivery_note`; `document_number`, client/product, dates, pagination | Native document filters and bounded cards; member read |
| `search_articles` | `query`, `reference`, `product_name`, `type_article=Produit|Service`, `archived`, dates, pagination | Article projection including existing member-visible purchase/sale amounts; member read |
| `search_payments` | `query`, invoice/client/product, `status=Valide|Annulé`, dates, pagination | Payment/invoice/client projection; member read |
| `search_users` | `query`, `name`, `email`, `is_active`, dates, pagination | Native global account lookup, excluding self; current staff within authorized assistant context |
| `search_operations` | Required operational resource; resource-specific fields/statuses below | Read-only stock/logistics cards; native resource permissions |
| `get_record` | Required `resource` and positive `identifier` from an authorized result | Refresh one pro forma, credit note, delivery note, article, payment, user, stock or logistics record; resource permission |
| `get_invoice` | `invoice_id`, or authorized current invoice context | Invoice card; member read |
| `search_clients` | `query`, `client_id`, or `related_invoice=true` with current invoice | Up to ten client cards; member read |
| `financial_summary` | Required `metric`, `period`, `currency`; custom dates where applicable | Existing dashboard aggregate; member read |
| `list_payments` | Optional dates | Latest valid payments, capped at ten; member read |
| `navigate` | Required approved resource/page; optional `identifier`, or `invoice_number` for invoice targets | Backend-resolved route, never an arbitrary URL; target read permission and `can_update` for supported edit routes |
| `previous_results` | `operation=show|open|unpaid`; 1-based `index` for open | Revalidate stored ordered references; `unpaid` is invoice-only |
| `prepare_change` | Required resource and `operation=update|delete`; target ID (or invoice number), allowlisted `changes` for update | Human confirmation preview only; existing edit/delete rights |
| `invoice_pdf` | `invoice_id`, invoice number, or current invoice | Structured PDF action; existing print permission and invoice status restrictions |
| `knowledge` | Required `query`, 2–300 characters | Up to three approved authorized excerpts, optionally explained by the model; authorized application context plus fresh document capability/company scope (stock-only contexts cannot retrieve member documents) |

There are no generic SQL, shell, Python, URL-fetch, database-table, bulk extraction or arbitrary field-update tools. Internet search is not exposed by this business assistant's registry.

## Operational search schemas

The `search_operations` schema uses one strict branch per resource, including that resource's native status enum. `reference`, `product_name` and `location_name` are available on every branch; each term is at most 120 characters. All branches also expose the common dates/pagination fields.

| Resource | Visible module | Additional filters | `status` values |
| --- | --- | --- | --- |
| `stock_balance` | Stock | None | `disponible`, `minimum`, `a_approvisionner` |
| `stock_movement` | Mouvement de stock | None | `opening`, `adjustment`, `receipt`, `delivery`, `inventory`, `reversal` |
| `stock_receipt` | Réception | `client_name`, `supplier_name` | `draft`, `validated`, `cancelled` |
| `stock_inventory` | Inventaire | None | `draft`, `validated`, `cancelled` |
| `logistics_order` | Dossier logistique | `client_name`, `supplier_name` | The existing `LogisticsOrder.STATUT_CHOICES` phases, from `Réception commande` through `Clôture`/`Annulé` |

Logistics `status` means **Phase du dossier**, not the calculated global status. Search results also include `global_status` from `calculate_global_status()` without saving or synchronizing the order. Stock balances reuse read-only `prepare_balance_snapshots()`. No stock bootstrap, alert generation, reservation synchronization, receipt validation, inventory validation or logistics synchronization is invoked.

Stock search reference matches the article reference for balances/movements, the receipt/inventory reference for those records, and the dossier number for logistics. Client/product/location filters on a receipt or logistics order must match the same related line. Results exclude inconsistent related-company records and unsafe incoming aggregates.

## Structured output and navigation

Outputs use `type` values `record_list`, `invoice`, `client`, `financial_summary`, `navigation`, `knowledge`, `clarification`, `confirmation` or `pdf`. A record list contains `resource`, bounded `items` and, where supported, `has_more`/`next_offset`. There is no unrestricted total count. Detail results for receipts, inventories and logistics include at most ten lines plus `has_more_lines`.

Cards are explicit projections, not full serializers. Document cards contain number/client/date/status/currency/total; invoices add native paid/outstanding/payment status. Operational cards omit free-form notes, credentials, emails, costs and actor/source internals. User cards intentionally expose native staff-visible name/email/active/staff fields.

Navigation targets contain `application=facturation`, resource, validated identifier, trusted company and a fixed mapped path. Document routes use the actual Facturation module paths; stock uses `/dashboard/stock/`, its movements/receipts/inventories subroutes, and logistics uses `/dashboard/logistique/`. Company routes include the validated company query parameter; global user routes do not. Only invoice/client/quote/proforma/credit_note/delivery_note have assistant edit-route mappings. External destinations and `javascript:` URLs are not accepted.

Previous results retain the resource, ordered IDs and a 30-minute expiry. Reopening or selecting a result checks its current authorization and company ownership. History cards are refreshed from these references; model prose is not parsed for links.

Visible field labels come from the application forms and translations, for example `physical_quantity` → **Physique**, `reserved_quantity` → **Réservé**, `available_quantity` → **Disponible**, `incoming_quantity` → **Entrant**, `projected_quantity` → **Projeté**, `stock_minimum` → **Minimum**, `balance_after` → **Stock après mouvement**. Structured keys stay internal; generated prose passes the label guard described in [AI_SECURITY.md](AI_SECURITY.md).

## Financial semantics

`financial_summary` supports exactly:

| Metric | Existing source / meaning |
| --- | --- |
| `invoiced_net_ttc` | `CollectionRateView`: invoiced TTC less active credit notes, using existing dashboard status rules |
| `collected` | `CollectionRateView`: valid payments by payment date |
| `outstanding` | `KPICardsWithTrendsView`: current outstanding balances of invoices issued in the selected period |
| `invoice_count` | Scoped invoice count by issue date and currency |

Periods are `current_month`, `previous_month`, `current_year`, `previous_year` or `custom`; custom requires both dates. Relative periods use the application's current local date. Currency is explicitly `MAD`, `EUR` or `USD`; no exchange-rate conversion exists. These values are not profit, expenses or interchangeable meanings of “income.” Ambiguous metrics use clarification. Financial cards come from the backend, not model arithmetic.

## Supported confirmed writes

The model can only propose a change. Human confirmation is a separate authenticated endpoint, bound to the actor/company and expiring after five minutes. The exact preview and current serialized fingerprint must still match. See [AI_SECURITY.md](AI_SECURITY.md) for transaction and durable actor-history details.

| Resource | Supported update fields / visible labels | Delete |
| --- | --- | --- |
| `invoice` | `remarque` (Remarque), `termes_paiement` (Termes de paiement), `date_echeance` (Date d’échéance) | Existing `can_delete` and native database protections |
| `quote` | `remarque`, `date_echeance` | Same |
| `proforma` | `remarque`, `termes_paiement`, `date_echeance` | Same; protected stock reservations can block deletion |
| `credit_note` | `remarque`, through existing **Brouillon-only** serializer | Existing delete policy; no new draft-only delete rule is invented |
| `delivery_note` | `remarque`, `date_echeance` | Existing delete policy; shared native transactional stock reversal, ownership checks and exact-once locking |
| `client` | `raison_sociale` (Raison sociale), `nom` (Nom), `prenom` (Prénom), `adresse` (Adresse) | Existing `can_delete` and native database protections |

These limits are deliberate: other edits open an existing authorized form where available. Users, articles, payments, logistics and all stock resources are read-only through this assistant. Creation, document status changes, line/price/quantity changes, payment edits, role changes and bulk deletions are not implemented. Credit-note partial updates reject the legacy null-payment-mode case that would silently change another field.

## Bounds and errors

| Boundary | Implemented limit |
| --- | --- |
| User text | 4,000 characters; nonempty, no NUL; common secret patterns rejected |
| Tool arguments | Strict JSON schema; serialized argument payload at most 6,000 characters |
| Tool execution | At most three calls per executor; normal planner selects one |
| SQL statement | PostgreSQL local statement timeout: 5 seconds |
| Structured result | At most 18,000 serialized characters; output type validated |
| Search/detail | At most ten results/lines; exposed offset at most 1,000; date interval at most 3,660 days |
| Knowledge | At most 200 authorized candidates, three excerpts, 3,500 characters/excerpt |
| Model transport defaults | 512 output tokens, 90-second model timeout; prompt payload at most 48,000 bytes, streamed transport at most 500,000 bytes |
| Concurrency | One shared database inference lease; an occupied lease returns `BUSY` |
| Conversations | At most 100 unexpired conversations per user, 60 persisted messages/conversation; list returns at most 30 |
| Throttles per user | Reads 120/minute; inference/messages 12/minute; confirmations 20/minute; ordinary chat writes 60/minute |
| SSE queue | 256 events; overflow/disconnection cancels delivery |

The provider may wait for a bounded network read before cancellation completes. Limits and model settings are configuration, not measured throughput or acceptance results.

Errors are stable codes, without database errors, raw serializer details or stack traces in assistant responses:

- `NOT_AUTHENTICATED`, `PERMISSION_DENIED`, `NOT_FOUND`: authentication, current permission or unavailable authorized target.
- `INVALID_ARGUMENTS`, `MULTIPLE_MATCHES`, `SENSITIVE_INPUT`: invalid schema/value, ambiguous invoice number, or rejected credential-like input.
- `CONTEXT_EXPIRED`, `STALE_ACTION`, `ACTION_REJECTED`: revoked/expired context, changed preview, or rejected native action.
- `BUSY`, `CONTEXT_LIMIT`, `TOOL_LIMIT`, `TOOL_TIMEOUT`: bounded resource exhaustion or database timeout.
- `APPLICATION_UNAVAILABLE`, `MODEL_TIMEOUT`, `INCOMPLETE_RESPONSE`, `INVALID_MODEL_OUTPUT`, `CANCELLED`, `INTERNAL_ERROR`: inference, transport or safe execution failure.

The API maps not-found/authentication/permission/unavailable/busy/expired-context to 404/401/403/503/429/409; other `ChatAIError` codes currently map to 400. SSE sends a typed `error` event after the streaming response has started. Throttled responses retain `Retry-After`.

## Verification and extension rules

Focused synthetic database tests exercise document, catalog and operations adapters, confirmed writes, native permission exceptions, stale references, delivery revalidation and schema rejection. Independent module integration tests passed 188 cases; the affected history/integration suites passed 253 after the stream revocation-order fix. The full backend rerun passed2,272tests and30subtests; the later assistant run passed765tests followed by52targeted review regressions. Server v4 evaluation and performance measurements are complete, while broad model-quality acceptance remains below target. Actual local invoice/quote/article/financial and navigation workflows passed. Production evidence is tracked in the Phase1 report; these backend tests alone are not a production-readiness claim.

To add a tool/resource, inspect its actual native permission and serializer/service path, add fixed metadata and strict schemas, add scoped read/proposal execution, visible labels and verified navigation, then add denial/revocation and workflow tests. Update this table and the multilingual held-out dataset. Do not register any other ecosystem application until Phase 2 receives explicit approval.

Source of truth: [registry/executor](../../facturation/facturation_backend/chat_ai/tools.py), [documents](../../facturation/facturation_backend/chat_ai/documents.py), [catalog](../../facturation/facturation_backend/chat_ai/catalog.py), [operations](../../facturation/facturation_backend/chat_ai/operations.py), [actions](../../facturation/facturation_backend/chat_ai/actions.py), [navigation](../../facturation/facturation_backend/chat_ai/navigation.py), [core contracts](../src/chat_ai_assistant/contracts.py), [model provider](../src/chat_ai_assistant/provider.py).
