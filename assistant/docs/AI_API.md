# Chat AI Assistant — Facturation API

Status at 2026-10-09: implemented contracts inspected in the current checkout. The latest chat frontend client/component run passed 112 tests, TypeScript and a production build. This document is not a production deployment or complete model/end-to-end acceptance report. Only `facturation` is integrated.

## Location, authentication, and scope

The Django adapter is `../facturation/facturation_backend/chat_ai/`. `facturation_backend/urls.py` mounts it at **`/api/ai/v1/`**. Reusable orchestration/provider code is in this repository's `src/chat_ai_assistant/`; existing business services and permission helpers stay in Facturation.

All endpoints inherit DRF `IsAuthenticated` and the application's configured `dj_rest_auth.jwt_auth.JWTAuthentication`. The frontend sends its existing access token in `Authorization: Bearer <token>`, never in an SSE URL. There is no additional assistant login. Requests also require backend `CHAT_AI_ASSISTANT_ENABLED`.

Identity is always the authenticated requester. Company identifiers select a context that the backend validates; a JSON role/user claim cannot confer permission. Existing company membership controls business reads and financial reports. Existing helpers control edit/delete/print. Staff-only account queries retain their native global scope. Native superuser stock access without membership is supported, without granting access to other business tools.

Responses set `Cache-Control: no-store, private`. Payload serializers reject unknown top-level fields and invalid types. Rate limits per authenticated user are 120/minute for GET/HEAD/OPTIONS, 60/minute for ordinary mutations, 12/minute for message inference, and 20/minute for confirmation. DRF throttling retains `Retry-After`.

## Endpoints

Paths below are relative to `/api/ai/v1/`.

| Method/path | Request | Success |
| --- | --- | --- |
| `GET capabilities/?language=fr` | No body; optional native UI language `fr`/`en`. | 200: application, companies/capabilities/suggestions, languages, model identifier, `read_only: false`. |
| `POST conversations/` | `{"company_id": 7}` | 201: `{"id":"<uuid>","company_id":7}`. |
| `GET conversations/?company_id=7` | Required positive company identifier; other query keys are rejected. | 200: up to 30 current-user conversations, newest first. |
| `GET conversations/<uuid>/` | No body. | 200: conversation identifier/company, refreshed messages, `results_refreshed: true`. |
| `DELETE conversations/<uuid>/` | No body. | 204: deletes this authorized conversation and its related history/feedback. |
| `POST conversations/<uuid>/messages/` | `text`, UUID `request_id`, optional `context`. | 200 JSON final message, or authenticated SSE when requested. |
| `POST conversations/<uuid>/selection/` | `resource`, positive `identifier`, `operation: "edit"` or `"delete"`. | 200 assistant message containing navigation or a deletion preview. |
| `POST actions/<uuid>/confirm/` | `{"confirmed":true}` | 200: success, operation, resource, record identifier. |
| `POST feedback/` | `{"message_id":"<uuid>","helpful":true}` | 200: `{"saved":true}`; updates this user's feedback. |

Capabilities company entries include `id`, `name`, `can_update`, `can_delete`, `can_create`, `can_print`, and `suggestions`, plus a permission-filtered `shortcuts` array with `command`, `title`, `help` and `example`. The optional `language` query parameter localizes catalogue captions; it grants no authority and is not a conversation-language selector. Superuser companies without membership additionally set `can_read_business: false` and disable mutation/print flags. Languages are advertised as `fr`, `en`; this declaration is not an accuracy measurement. `read_only: false` means the adapter has explicitly confirmed bounded writes, not that every module supports mutation.

Conversation list rows have `id`, `created_at`, `updated_at`, and `title`: the first user message truncated to 120 characters, or “Nouvelle conversation”. Listing requires a matching current authorization stamp and unexpired conversation. A user may have at most 100 unexpired conversations. Default expiration is 30 days through `CHAT_AI_RETENTION_DAYS`; it is set at creation, not extended by every message. `python manage.py purge_ai_history` removes expired history/pending actions and old non-confirmation audit events. Successful write audits are excluded from that cleanup.

## Messages and context

A message request has this shape; values are illustrative, not a fixture dependency:

```json
{
  "text": "Trouve les devis du client Atlas avec peinture",
  "request_id": "4382456d-f7de-45d1-a219-267e530b3bf1",
  "context": {"invoice_id": 12}
}
```

`text` is trimmed, nonempty, and at most 4,000 characters. Null characters and detected credential/private-key patterns are rejected. Context accepts an optional positive `invoice_id` and an `interface_language` hint (`fr`/`en`); the backend rereads and authorizes the invoice. The current message determines response language, with interface language only as fallback. The frontend supplies it only on an invoice detail route. Company/user/roles are not accepted as message context. Context support does not yet cover every page's selected record automatically.

Final messages are `{"id":"<uuid>","role":"assistant","text":"...","cards":[...]}`. History adds each message's `created_at`. A turn can have empty prose when structured cards contain the result. Record amounts are returned by business operations, not regenerated as model financial claims.

A `(conversation, request_id, role)` database uniqueness constraint and completed-turn replay support retries. A completed request is reauthorized and replayed with fresh cards. An unfinished request identifier cannot be reused with different text. New turns are rejected once the conversation already has 60 persisted messages; history retrieval returns up to 60 messages. Planner history includes the last four user utterances, not historical private tool output.

Conversation access checks user ownership, expiration, and an authorization stamp covering membership/role-sensitive flags and staff/superuser status. Changes invalidate the old context. Replayed record cards reread up to ten stored identifiers. Knowledge prose is withheld if its original document versions/access are no longer authorized. Confirmation history stores only the pending action identifier and language. Reopening reconstructs a preview after fresh ownership, native permission, fingerprint and serializer-rule checks; expired or completed requests return a non-actionable status. Confirmed outcomes remain attributable through durable audit records.

The latest structured result references include resource, authorized identifiers, and a 30-minute expiry. Follow-up selection revalidates those records; saved references do not establish permission.

## SSE and cancellation

Use the same message POST with `Accept: text/event-stream`, JSON content type, and bearer authentication. The backend responds with `text/event-stream; charset=utf-8` and `X-Accel-Buffering: no`.

| Event | Payload | Current behavior |
| --- | --- | --- |
| `message.started` | `{"request_id":"<uuid>"}` | Begins the request. |
| `tool.started` | `{"tool":"<registered name>"}` | Metadata only; no raw business result. |
| `tool.completed` | `{"tool":"<registered name>","success":true}` | Metadata only. |
| `message.delta` | `{"text":"..."}` | Knowledge-answer prose chunks after source access checks and label filtering. |
| `message.completed` | Final assistant message with cards. | Required success terminator. |
| `error` | `{"code":"..."}` | Failure terminator. |

Events use `event: NAME`, `data: JSON`, and a blank-line separator. The internal `_knowledge.sources` event never leaves the backend. `navigation.available` is not implemented; navigation is a final structured card. Most record searches return progress plus a completed card, not token-by-token record narration. The current client displays deltas/final messages and a general loading state rather than technical tool names.

JWT expiry and current authorization are checked before private queued output is delivered. Knowledge sources and final record/navigation cards are also revalidated. The queue is bounded to 256 events. One database inference lease limits concurrent orchestration; contention returns `BUSY`. The configured model timeout defaults to 90 seconds; the lease expires after twice that timeout plus 60 seconds if abandoned.

Client cancellation uses `AbortController`, not a separate cancellation endpoint. Disconnection sets the worker cancellation event; provider cancellation/timeout releases the lease. This is cooperative cancellation, not an instantaneous thread kill. A canceled request may retain its already-recorded user message; it does not persist a completed assistant answer once cancellation is observed. Frontend request generations ignore any stale event delivered after cancellation, history replacement, company changes, or unmount.

Confirmed writes deliberately use a separate non-aborted request. Closing a chat or stopping inference cannot undo an already executed write. The client refreshes caches on confirmed success even after a workspace change.

The client parser supports fragmented Unicode, enforces a 100,000-character buffered-frame limit, and requires `message.completed`; early EOF is `INCOMPLETE_RESPONSE`. An explicit `error` is propagated. Retry uses the original request UUID.

## Structured cards, navigation, and PDFs

Card discriminants in `types.ts` are `record_list`, `invoice`, `client`, `financial_summary`, `navigation`, `knowledge`, `clarification`, `confirmation`, `confirmation_status`, and `pdf`. Optional fields depend on that type. Business result output is validated and bounded by the tool executor, which caps a response at 18,000 serialized characters and allows at most three executions per request. PostgreSQL tool queries use a five-second statement timeout.

Read projections are explicit:

| Resource | Principal record fields |
| --- | --- |
| invoice/quote/proforma/credit_note/delivery_note | Authorized document number, client, date/status/currency and applicable financial values. |
| client | Authorized identity and validated navigation. |
| article | Reference, bounded designation, type/archive state, purchase/sale amounts with separate currencies. |
| payment | Invoice number, client, payment date/status/amount and invoice currency. |
| user | Name/email, active/staff flags; requires native staff authorization. |
| stock_balance | Reference/designation/location, stock state, physical/reserved/available/incoming/projected/minimum quantities. |
| stock_movement | Product/location, movement type, quantity, balance after movement. |
| stock_receipt | Reference/status, dossier/supplier, validation date. |
| stock_inventory | Reference/status/location, validation date. |
| logistics_order | Reference/supplier, workflow/global status, expected/actual dates. |

Receipt, inventory, and logistics detail requests can include at most ten explicit `lines` and `has_more_lines`. Search adapters use bounded limits/offsets and return `has_more`/`next_offset`; the current UI asks the user to refine the search rather than providing a pagination button. Newly added article/payment/user/stock/logistics resources have no assistant mutation tools.

Navigation targets have `application: "facturation"`, `resource`, `identifier` (positive integer or null for a list), `company_id`, and `path`. The backend resolves verified routes after authorization. The client recomputes the exact allowlisted path and rejects changed identifiers/company, extra query parameters, external destinations, or invented resources. Global user/users routes omit `?company_id=...`; other routes include it. Only invoice/client/quote/proforma/credit_note/delivery_note have assistant `_edit` navigation variants. The frontend offers explicit navigation controls and does not redirect an ordinary search automatically.

PDFs reuse existing business endpoints, outside the assistant API:

| Resource | Existing GET path |
| --- | --- |
| Invoice | `/api/facture_client/pdf/fr/<id>/?company_id=<company>` |
| Quote | `/api/devi/pdf/fr/<id>/?company_id=<company>` |
| Pro forma | `/api/facture_proforma/pdf/fr/<id>/?company_id=<company>` |
| Credit note | `/api/facture_avoir/pdf/fr/<id>/?company_id=<company>` |
| Delivery note | `/api/bon_de_livraison/pdf/fr/<id>/?company_id=<company>` |

The client uses fixed endpoint mappings, a positive safe integer identifier, and the current session bearer token. It only downloads successful PDF content, revokes the resulting blob URL, and assigns human filenames such as `Facture pro forma 12.pdf`. PDFs currently use the French endpoint regardless of conversation language. Native PDF permission checks remain in force.

## Confirmed edits and deletions

`selection/` accepts only invoice, quote, client, proforma, credit_note, and delivery_note. The selected identifier must be in this conversation's unexpired latest result references. An edit selection returns a validated existing-form route. A delete selection prepares a pending action. Natural-language bounded edits can also call the registered preview tool; there is no unrestricted browser changes endpoint.

Update preview fields are restricted to:

| Resource | Allowed internal keys |
| --- | --- |
| invoice, proforma | `remarque`, `termes_paiement`, `date_echeance` |
| quote, delivery_note | `remarque`, `date_echeance` |
| credit_note | `remarque` |
| client | `raison_sociale`, `nom`, `prenom`, `adresse` |

Internal identifiers are necessary to the protocol. User-facing cards use the actual form translation labels and reject unknown resource-field pairs instead of showing those keys. Prose also uses the backend verified-label presentation guard. No financial numeric field is exposed as a chat update field.

A preview returns `type: "confirmation"`, action UUID, resource/operation, record/company identifiers, visible record label, proposed `changes`, permitted `before` values, expiry, and a deletion warning when applicable. Its server-side lifetime is five minutes. It binds the requesting user, company, record, proposed changes, original chat request, and a serializer-based record fingerprint.

Confirmation requires `{ "confirmed": true }`. Under a database transaction it locks the action and target, rechecks the requester, native permission and company/object scope, expiry, single-use state, and fingerprint, then uses the existing serializer or delete operation. Stale previews require regeneration. Protected deletes and existing validation rules are not bypassed. A consumed action cannot execute twice; subsequent confirmation does not return a second success.

Success returns `{"success":true,"operation":"update|delete","resource":"...","record_id":12}`. Existing simple-history receives the authenticated user and change reason. A successful mutation audit preserves actor identity, company, target, changed field names, originating request/action identifiers, and outcome. It is committed with the business mutation and remains after chat history deletion; see [AI_AUDIT_HISTORY.md](AI_AUDIT_HISTORY.md).

## Errors and client handling

`ChatAIError` responses have `{"error":{"code":"..."}}`. HTTP mapping is currently:

| Code | HTTP |
| --- | --- |
| NOT_FOUND | 404 |
| NOT_AUTHENTICATED | 401 |
| PERMISSION_DENIED | 403 |
| APPLICATION_UNAVAILABLE | 503 |
| BUSY | 429 |
| CONTEXT_EXPIRED | 409 |
| Other application codes, including INVALID_ARGUMENTS, SENSITIVE_INPUT, STALE_ACTION, ACTION_REJECTED, CONTEXT_LIMIT | 400 |

DRF authentication, serializer, and throttle errors still use the application's existing `status_code`, `message`, `details` envelope; they are not all normalized to `error.code`. Midstream errors use the SSE `error` payload. Unexpected streaming failures become `INTERNAL_ERROR` without a stack trace.

`chatRequest` retries a 401 once when the existing session refresh supplies a different access token, then invokes the application's unauthorized handler if it remains 401. The current UI maps recognized codes to safe messages; unrecognized/native-envelope failures receive a generic unavailable message. A 403 without `error.code` becomes PERMISSION_DENIED. This fallback is a current limitation, not a complete typed error taxonomy for every DRF error.

## Verification boundary

The earlier focused frontend run on 2026-10-08 passed **100/100 tests** and `tsc --noEmit --incremental false`, covering route substitutions, global user routes, fixed authenticated PDF endpoints/names, Unicode/incomplete streams, card projections, confirmation rejection, request/history races, and write cache behavior. These are automated client/component checks, not a claim of live model acceptance. Backend security/integration test results are maintained separately in the project progress/testing evidence.

Actual local browser checks passed invoice, quote and article searches, follow-up selection, navigation, company isolation, history and bilingual workflow delivery. Broad per-module model quality remains below the acceptance targets. Physical mobile keyboard behavior has not been tested. The feedback API exists without a frontend feedback control. Production reverse-proxy streaming, resource behavior under production load, complete multilingual model accuracy, and Phase 1 acceptance are not certified by this document.

Optional message context `interface_language` accepts only `fr` or `en` and is read automatically from the existing application language. It selects visible form labels; it does not set the conversation language or grant authority. Generated answer language follows the current message. Article results may include `sale_label: "price_excl_tax"` to select the native Nectar caption; omitted purchase values are not displayed.


The module-catalogue release passed 112 chat UI/client tests and 819 assistant/backend tests. On 2026-10-09, nine production browser checks verified catalogue/permission parity, English/French capability answers, bounded module cards, a described article search and responsive menu behavior. Streaming final responses worked for those observed flows; exhaustive proxy disconnect behavior and sustained load remain outside this evidence. See AI_TESTING.md.
