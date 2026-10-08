# Chat AI Assistant security

Reviewed against the working Facturation implementation on 2026-10-08. This document describes implemented controls, not production approval. Phase 1 is limited to `facturation`; none of the other five applications is integrated.

## Trust boundaries and identity

The Django adapter is the authorization boundary. The model selects a registered operation and arguments; it cannot supply identity, company permissions, executable code, SQL, or an arbitrary URL. The adapter queries existing application models and services under trusted backend scope.

All chat views require the existing `dj_rest_auth.jwt_auth.JWTAuthentication` and DRF `IsAuthenticated`. They inherit the application's authentication/cookie/CSRF configuration; the assistant does not introduce another login system. Streaming uses an authenticated POST, never a token in the streaming URL, and checks JWT expiry before delivering queued output. Responses use `Cache-Control: no-store, private`.

A conversation belongs to one authenticated user and one company. The selected company tab is a user-interface hint; the backend validates the selected company. User-supplied role names and user IDs are rejected by strict API serializers. Current invoice context is resolved through the same authorized invoice lookup before use.

Two distinct checks are intentional:

- `security.authorize()` requires an active user and current company membership. Business reads, reports, knowledge and writes retain this requirement.
- `security.authorize_context()` admits a current member, or an active superuser for an existing company. The latter permits the native stock exception only; opening a conversation does not grant business read access.

The authorization stamp includes the user/company, membership ID, role ID/name, document-validation/status flags, and current staff/superuser flags. A change invalidates the old conversation context. Each execution, history reference refresh, navigation request and final delivery rechecks authorization; stored references never grant access.

## Native permission matrix

These are the current application policies, not a new assistant role hierarchy. A company member can read existing company business data and financial summaries regardless of the five named roles. Do not introduce an additional administrator-only report rule.

| Operation | Required existing access |
| --- | --- |
| Invoice, devis, pro forma, credit note, delivery note, client, article and payment reads | Active membership in the selected company |
| Financial summaries and approved knowledge | Active company membership; knowledge additionally filters document scope/capabilities |
| Logistics order reads | Active company membership; superuser status alone is insufficient |
| Stock balances, movements, receipts and inventories | Active company membership **or** active superuser, matching `StockAccessMixin.get_company` |
| Account/user search and detail | A valid assistant context **and** current `is_staff`, matching native global account administration; excludes the acting user's own account |
| Bounded edit proposal and confirmation | Membership plus existing `can_update`, serializer validation and scoped target |
| Delete proposal and confirmation | Membership plus existing `can_delete`, scoped target and database deletion protections |
| Invoice PDF | Membership plus `can_print`; invoice status must be `Brouillon` or `Accepté` |
| Audit administration | Active superuser; read-only Django admin, no ordinary chat endpoint |

| Member role | Business/stock/logistics read | Bounded edit | Delete | Invoice PDF |
| --- | --- | --- | --- | --- |
| Caissier | Yes | Yes | Yes | Yes |
| Commercial | Yes | Yes | No | Yes |
| Comptable | Yes | No | No | Yes |
| Lecture | Yes | No | No | No |
| Logistique | Yes | No | No | No |

Staff status is separate from company role. A nonmember superuser receives `context` and `stock_read`, not `read`, `create` or `mutate`. If that user is also staff, global user reads remain available. A staff nonmember who is not a superuser cannot create that company's assistant context. A `create` capability can describe existing application access, but no AI creation tool exists.

The registry removes unavailable tools and narrows mixed-resource schemas before prompting. The executor independently checks capabilities and resource permissions before and after execution, including direct history/navigation helpers.

## Record and company isolation

The adapter uses fixed querysets and projections. Invoice/devis/document reads check company and client ownership; credit notes additionally constrain their origin. Payments constrain their invoice and invoice client. Operational adapters reject inconsistent company ownership across stock locations/articles, logistics lines/proformas/clients, receipt lines and inventory lines. Unsafe logistics contributions suppress a stock balance rather than expose a cross-company incoming aggregate.

The global staff-user lookup is the explicit exception to company-owned record scope. It returns a bounded name/email/status projection and no credentials or authentication fields.

Record lists contain no unrestricted count or arbitrary field selection. Results and navigation targets are revalidated before JSON completion, history return and queued SSE completion. Foreign or absent record IDs resolve through the same `NOT_FOUND` path. Financial summaries reuse the same member access and authoritative calculations as the existing dashboards.

## Confirmed changes and accountability

The user's later instruction authorized permission-respecting edits/deletes. They are implemented through a two-step flow:

1. `prepare_change` checks the existing role, resource, target and field allowlist, validates an edit through the native serializer, and stores a user/company-bound `PendingAction`. The response contains the exact before/after preview and a five-minute expiry. It performs no business write.
2. `POST /api/ai/v1/actions/{id}/confirm/` requires `confirmed: true`. It locks the pending action and target row, rechecks current permission and expiry, compares a serializer-based fingerprint, reruns serializer validation, and executes the change atomically. An action cannot be reused.

Only the six resources and fields listed in [AI_TOOLS.md](AI_TOOLS.md) are supported. No price, quantity, status, payment transaction, permission or bulk write tool is exposed. Database `PROTECT` and serializer failures reject the action safely. A changed preview produces `STALE_ACTION`.

Successful writes set `_history_user` to the authenticated requester and record the confirmation ID in the native history reason. A separate durable `AuditEvent` stores actor ID/label, company, resource/record, operation, changed field names, originating instruction ID and confirmation correlation ID. The user FK is nullable with `SET_NULL`; actor identity survives account deletion. Conversation deletion and `purge_ai_history` do not remove `confirmed_` audit events. Audit metadata does not store entire before/after business payloads. Failed tool executions are audited; failed confirmation requests do not currently create a separate durable confirmation-failure event.

Credit-note remarks reuse the existing draft-only serializer. The adapter supplies the existing client to its partial validator without rewriting payment mode/currency. A legacy credit note with no payment mode whose origin would implicitly fill it is rejected with `ACTION_REJECTED`; use the existing form for that case.

**Resolved locally: stock-accounted delivery deletion.** Native single/bulk deletion and assistant-confirmed deletion now reuse the atomic `delete_deliveries_with_stock` service (the single-record entry point is `delete_delivery_with_stock`). The service reverses each actual unreversed posting once, including when stock management has since been disabled or the document has a legacy nonposted status. It retains the existing reservation restoration/release rules, derives reservation provenance from the ledger even after source-invoice deletion, validates the complete company ownership graph, and locks affected proformas and balances in a stable order across the whole batch. Native history records the authenticated deleting actor; assistant history retains the confirmation ID and its durable audit event. Thirty synthetic deletion regressions cover exact-once reversal, multiple posting cycles, reservations, company boundaries, concurrent cancellation, and rollback of ledger/document/history/confirmation/audit failures. The impacted stock, expiry, delivery and assistant suites also pass. This is verified local code, not a production deployment or a repair of previously deleted historical records.

**Serializer-accurate update previews.** The assistant uses native serializer validation to show canonical changes, omit unchanged fields, and reject inputs discarded by native business rules or updates that would also modify an unrequested field. This prevents Nectar's hidden remark from being presented as an applied edit and prevents a bounded date edit from silently clearing legacy discounts. Confirmation repeats this validation, including company rules that changed after the preview. The audit lists the actual approved changed fields. Thirteen additional synthetic document-action regressions verify these cases across all five supported document types, alongside the existing permission and history tests.

## Knowledge, history and revocation

Knowledge retrieval is currently approved lexical retrieval, not a vector database. It filters `application_id=facturation`, `sensitivity=member`, required capabilities and optional company scope **before** reading/ranking titles and content. It examines at most 200 authorized documents and returns at most three excerpts of 3,500 characters each. `sync_ai_knowledge` accepts reviewed, approved Facturation JSON metadata, hashes source versions, updates changed documents and removes obsolete global documents. It does not scrape private business records.

Generated knowledge text records every original source's `document_id` and exact version. All sources must still exist, be in the correct application/company scope, retain permitted sensitivity/capabilities and match the saved versions. Missing legacy source metadata fails closed. This applies to history and completed request-ID replay as well as new output.

Source checks occur before the knowledge prompt, before processing each model delta, after the stream, before persistence, and before queued delivery. The private `_knowledge.sources` event never reaches the browser. Newly retrieved replay cards are checked separately from the original prose sources. Revocation stops subsequent output; it cannot retract content already delivered while authorized.

Saved business cards are rebuilt from current authorized references rather than persisted result snapshots. Only recent user utterances, not old business answers, enter planner history. Messages remain private to their owner/company. History defaults to 30 days; `purge_ai_history` performs cleanup and must be scheduled by deployment. Users' private conversations are not automatically training data.

## Model output and prompt injection

The Colibri-compatible provider requires exactly one schema-valid function call. Free-form planner text is never accepted as a verified answer. Clarifications use fixed reason/language enums and backend-owned text. Financial and record values are returned as structured backend cards rather than regenerated by the model. Retrieved content is quoted as untrusted data; it cannot grant tool access.

`LabelledTextStream` maps known internal identifiers to verified visible form labels. It buffers incomplete words across stream boundaries and rejects unknown snake_case identifiers (with a narrow human-reference allowance such as Atlas_2026) with `INVALID_MODEL_OUTPUT`. The same label guard applies to saved assistant prose. Structured JSON keys remain internal contracts. This guard is a presentation control, not authorization or a complete detector of every possible technical term; legitimate unknown underscore expressions can also be rejected.

The provider accepts operator-configured private/loopback endpoints, rejects public/link-local addresses and redirects, and has no commercial API fallback. Inference receives no database credentials or browser tokens. The input secret-pattern check rejects common credential/private-key patterns but is not a general data-loss prevention system. Infrastructure must still protect the model endpoint, Django database, backups and logs.

## Resource limits and validation status

The current implementation bounds model output, request/prompt sizes, tool schemas, pagination, result size, statement time, inference concurrency and streaming queues; exact values are in [AI_TOOLS.md](AI_TOOLS.md). Disconnect/cancellation stops further delivery, while the bounded worker releases its inference lease when upstream exits or times out. Capabilities/history reads and confirmed writes have separate throttle budgets from inference.

Local synthetic suites cover membership and object isolation, native stock/staff exceptions, confirmed actor history, source revocation, queued/JSON delivery, strict planner output and field-label stream boundaries. The final combined assistant backend suite passed 576 tests, including source revocation, scoped delivery and human-label regressions. This is not a production security audit or full Phase 1 acceptance.

Production readiness remains incomplete: final base/tuned model acceptance, production-server performance/concurrency measurements, full authenticated browser workflows and deployment configuration review are required. Earlier pilot model scores did not meet the requested acceptance targets. No production rollout or Phase 2 approval is implied.

## Source map

- [Security/context checks](../../facturation/facturation_backend/chat_ai/security.py), [executor/registry](../../facturation/facturation_backend/chat_ai/tools.py), [native roles](../../facturation/facturation_backend/core/permissions.py).
- [Views and delivery](../../facturation/facturation_backend/chat_ai/views.py), [conversation service](../../facturation/facturation_backend/chat_ai/services.py), [knowledge](../../facturation/facturation_backend/chat_ai/knowledge.py).
- [Confirmed actions](../../facturation/facturation_backend/chat_ai/actions.py), [history/audit models](../../facturation/facturation_backend/chat_ai/models.py), [audit admin](../../facturation/facturation_backend/chat_ai/admin.py).
- [Provider](../src/chat_ai_assistant/provider.py), [orchestrator](../src/chat_ai_assistant/orchestrator.py), [label guard](../src/chat_ai_assistant/presentation.py).
