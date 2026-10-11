# Réservation assistant progress

Application: `reservation`. Status: PARTIALLY IMPLEMENTED. Local adapter/UI tests pass. Shared-model accuracy, server fine-tuning and production activation remain incomplete.

## Current training preparation — 2026-10-11

The current prepared dataset is `reservation-dialogue-v2-en-fr`: **180 / 40 / 84 training / validation / held-out examples**. Its cumulative shared stage is `shared-v8r4-en-fr`: **2,244 / 402 / 690** in the same order. Original logical prompts, expected actions and split membership are preserved. Updated inputs match the reviewed native planner, current-message language, calendar context and explicitly synthetic ordered references. Added neutral greeting/thanks histories are variants, not independent scenarios.

The complete cumulative six-app preparation passed metadata-only tokenizer/Colibri checks without loading local weights. Exact predecessor prefixes, source dependencies and manifests are pinned. This is preparation, not a measured Réservation model score. The sole active optimization is shared V5r4; subsequent stages remain **Contracts → Gestion Magasin → Réservation**, one at a time after predecessor acceptance. See the [current training queue](AI_TRAINING_QUEUE.md) for the shared evidence and launch gates. Earlier dataset counts below describe the preserved initial preparation.

## Implemented and verified

The existing shared Colibri provider is reused. No new model was downloaded and no local training ran. Native JWT, active-user checks, read/create/edit/delete flags, independent Hilton access and staff-only user screens remain authoritative. Réservation has no company membership/tab feature; there is no company selector or browser-supplied scope. Conversations belong to the authenticated user and one internal application partition.

Seven bounded tools support search, details, safe navigation, annual native financial metrics, approved knowledge, previous-result references and exact change proposals. Eight native resources are bound: reservations, residences, apartments, costs, commercial premises, recorded rents, saved Hilton reports and staff user accounts. Search filters are validated, combined and never silently discarded. Apartments navigate to their residence; rents to their premises; Hilton reports to their native shared screen.

Financial results reuse native dashboard/balance/local calculations. Arrival-year reservation amounts are not collected cash; Airbnb/Bank returned amounts are a narrower metric; recorded paid rents are not accounting profit. Annual summaries require a year and may narrow to a verified residence. Monthly/arbitrary-period summaries are unsupported. Saved Hilton reports are read without recalculation or preview writes. Recorded unpaid rents exclude implicit, unrecorded dues.

Supported edits are reservation guest name/notes, residence/apartment name, cost description, premises name/address/tenant/notes and rent notes. Supported deletions require native permission and reject dependent residences/apartments/premises. Each change requires an owned five-minute exact confirmation, target fingerprint, fresh permission checks and locks. Native PUT handlers receive current validated fields; any normalization of an unrequested field is rejected. Native history and retained assistant audit identify the instructing user. Financial amounts, dates, payment flags, relationships, users/permissions and Hilton writes remain unsupported.

Persistent conversations, permission-revalidated history, feedback, cancellation and authenticated SSE reuse the common architecture. Ten approved EN/FR knowledge documents are synchronized by version and filtered before retrieval. Sensitive record snapshots are not stored as replay authority. Canonical MUI chat, SVG robot, light/dark styling, structured cards, native field labels, immediate suggestions and explanatory slash commands are integrated once in the authenticated root. Greetings/thanks follow the current message's English/French language without inference.

## Tests and browser evidence

Final isolated PostgreSQL suite: **514 tests passed**, including **43 assistant tests** (overlapping counts). Tests cover authentication, native permissions, Hilton-only access, restricted queries, strict schemas, native calculations, safe routes, history isolation/revocation, malicious content, protected fields, native PUT normalization, exact target/expiry checks and actor history. Concurrent confirmations produce one successful mutation, one rejection and one audit/history event. Consumed and purged confirmations replay a status without reexecution.

Frontend: **26 assistant tests passed**; TypeScript, scoped ESLint and production build passed. The tests cover feature visibility, owner-scoped API calls, absence of fabricated company context, route persistence, history, cancellation/late responses, safe cards/URLs, form labels and fragmented SSE.

Real local dummy-login checks use native APIs without substituted responses: slash record search, record navigation from another page and explicit list return, route-persistent chat, exact native confirmation and disposable cost deletion with matching history/audit actor, native logout clearing the assistant, read-only controls and Hilton denial, independent Hilton-only report access with ordinary reservation denial, current-message English greeting in the French interface, and owned conversation history. Model-driven natural-language accuracy is not established by this disconnected preview.

Eight actual light/dark × empty/filled × shortcuts-open/closed screenshots were compared with Design Workflow. One reviewer found no visual mismatch. Desktop panel: 392×602 CSS pixels. Mobile390×844 and 390×420: composer remains visible and no horizontal overflow. Company controls are intentionally absent. Artifacts remain in ignored local test directories. Physical-device keyboard and screen-reader certification are not claimed.

## Prepared, not trained

`reservation-v1-en-fr`: **150 training, 30 validation, 84 held-out** synthetic EN/FR cases. Generation forbids database queries; labels pass actual registry/shortlist schemas and trusted-target validation. Native achievable capability profiles are used. Bilingual pairs remain in one split; duplicate prompt/ID and sensitive-pattern checks pass. Exact deduplication does not establish exhaustive semantic independence. Review corrections were made before any baseline; the final held-out inputs must now stay fixed.

Proposed `shared-v8-en-fr`: **1,756 training, 258 validation and 580 held-out cases** across the six approved applications. All preceding curriculum rows remain an exact prefix. Current V5's fourteen pinned inputs are unchanged. No Réservation baseline, training, model score or performance measurement exists yet.

## Remaining gates

Complete the current shared V5r4 training/export/frozen evaluation; resolve failures without altering held-out labels. Advance subsequent app training serially, preserving earlier application evaluation sets. Required acceptance: ≥95% tool selection/eligible exact arguments, ≥99% structured output and zero unresolved critical authorization defects. Exact server tokenizer/Colibri preflight passed the cumulative six-app dataset; measured model performance remains required. Activation and replacing the shared production model require separate authorization.

## Verified disabled source release

Backend `105cc4e24c90`, frontend `3c09a4d8a103`: all six company/personal/production heads match. Production builds passed; 37 deployed backend source files match the reviewed local hashes. The assistant migration and ten knowledge documents were applied, with all 26 business-table counts unchanged against the private verified restore snapshot. Backend/frontend/database/Redis are healthy; anonymous assistant access returns 401. Live MCP verification confirms the login page, top theme control and absence of the assistant on the public page. The feature remains disabled; no authenticated production model workflow is claimed. Shared inference start time and current training process identity were unchanged.

Server preflight passed all 2,014 cumulative shared-v8 rows (1,756 training, 258 validation): schema/parser round trips, exact runtime prompt parity, loss boundaries and weighted-token alignment. Maximum train/validation lengths: 4,744/4,977 within 8,192 tokens. It loaded tokenizer metadata only, with no model download, inference or new training. See [public-safe report](../training/reports/shared-v8-en-fr-preflight.json).


## Reviewed conversation-reference update — 2026-10-11

IMPLEMENTED locally: complete saved selections are freshly authorized before model planning, preserving displayed order and inline-selection retry/page binding. Shared core 0.2.1 separates current-request language from history and validates explicit ordinal mutation targets. Native confirmation and actor history remain unchanged. Assistant suite: 70 tests and 6 subtests passed; one tenant-move test was skipped because Réservation has no native tenant partition. One reviewer found no remaining code issues. Backend `9f977d592709` is published to company/personal; its production restart awaits approval. Shared-model acceptance and feature activation remain incomplete.
