# Gestion Magasin assistant progress

Application: `gestion_magasin`. Status: PARTIALLY IMPLEMENTED. Local adapter/UI checks pass; model accuracy, server fine-tuning and production activation remain incomplete.

## Current training preparation — 2026-10-11

The current prepared dataset is `gestion-magasin-dialogue-v2-en-fr`: **198 / 43 / 90 training / validation / held-out examples**. Its cumulative shared stage is `shared-v7r4-en-fr`: **2,064 / 362 / 606** in the same order. Original logical prompts, expected actions and split membership are preserved. Updated inputs match the reviewed native planner, current-message language, calendar context and explicitly synthetic ordered references. Added neutral greeting/thanks histories are variants, not independent scenarios.

The complete cumulative six-app preparation passed metadata-only tokenizer/Colibri checks without loading local weights. Exact predecessor prefixes, source dependencies and manifests are pinned. This is preparation, not a measured Gestion Magasin model score. The sole active optimization is shared V5r4; subsequent stages remain **Contracts → Gestion Magasin → Réservation**, one at a time after predecessor acceptance. See the [current training queue](AI_TRAINING_QUEUE.md) for the shared evidence and launch gates. Earlier dataset counts below describe the preserved initial preparation.

## Implemented and verified locally

- One shared Colibri provider abstraction; no model download or local training. Native JWT, read/print/write flags, store memberships and role checks remain authoritative. Vendeur-only accounts retain POS guidance/navigation; mixed-role users retain POS access for their selected vendeur store. Pointage-only accounts receive attendance capabilities only, including their native delete exception. MBR-South list expansion does not grant detail/write access.
- Fourteen native resource bindings; eight bounded tools: search, detail, navigation, native financial summary, approved knowledge, previous results, wholesale PDF, confirmed change proposals. Generic and named searches preserve related-record scope; delivery/history fail closed when a related customer/employee leaves scope. Product catalogue visibility is global; selected-store stock remains scoped.
- Native dashboard calculations with explicit metric definitions. Dashboard balance is not accounting profit; current stock value and today's paid amounts require today's date in both bounds and reject historical/future ranges before querying. Only the selected authorized metric is returned.
- Supported native edits are descriptive/contact fields on products, customers, expenses, attendance and sale notes. Exact-target, owned, five-minute confirmations recheck permissions, scope, fingerprint and native validation under locks. Native history and an immutable actor-attributed assistant event record successful operations. Product/customer deletes with dependencies are rejected; no financial amount, relationship, quantity, role, bulk, sale-delete/void, stock-approval or transaction-validation writes are implemented.
- User/store-scoped persistent conversations, safe replay, request retry/cancellation, retention and feedback; twelve approved EN/FR knowledge records with versioned synchronization and pre-retrieval capability filtering.
- Canonical MUI chat in the authenticated root, local SVG robot, responsive light/dark panel, structured cards, native labels/status translations, greetings/thanks, descriptive slash commands and permission-filtered suggestions. The active native store tab scopes the assistant; pages without a scope request a permitted store choice. Starting a new conversation preserves the selected store.

## Verification evidence

The complete local PostgreSQL backend suite passed 448 tests before five additional intent-synonym/current-metric regressions; the final focused assistant suite passed 56 tests. These overlapping counts are not model accuracy. Frontend assistant/store-tab tests passed 40 cases; TypeScript, scoped ESLint and the final production build pass.

Real dummy-login MCP browser checks used native APIs, with no substituted responses: greeting and EN-to-FR switch, slash search, Store A/B stock results 2/30, active-tab conversation isolation, record navigation and explicit list return, native wholesale PDF, a disposable expense deletion with exact confirmation and the same actor in native history/audit, restricted reader action denial and history reopening. Read-only controls omit edit/delete/print and no other store is offered. Model-driven free-text accuracy was not tested in this disconnected local preview.

Eight light/dark, empty/filled, shortcuts-open/closed screenshots were compared side by side with the actual Design Workflow interface. Desktop panels both measure 392 by 602 CSS pixels; the native store row is the expected difference. Mobile 390 by 844 and 390 by 420 checks kept the composer visible without horizontal overflow. One reviewer checked all eight comparisons and the authorization fixes. Evidence lives in ignored local test artifacts, not public application data.

## Prepared, not trained

`gestion-magasin-v1-en-fr`: 166 training, 30 validation and 90 held-out synthetic English/French cases. Registry/shortlist schemas and trusted-target checks validate labels with database queries blocked. Bilingual pairs stay within a split; normalized exact cross-split overlaps and sensitive patterns are rejected. Semantic independence is not claimed merely from exact-deduplication.

The proposed `shared-v7-en-fr` mix retains all preceding curricula: 1,606 training and 228 validation rows, with 496 held-out cases across five applications. This is preparation only. No Gestion Magasin training job or accuracy result exists. Frozen baseline, serial tuning and non-regression acceptance remain required. The subsequent cumulative shared-v8 server preflight includes every shared-v7 source row and passed tokenizer/Colibri checks; see the shared training queue. The active V5 inputs/evaluator must stay unchanged.

## Remaining gates

Finish the current shared V5r4 training/export/evaluation; resolve acceptance failures honestly, then advance the serial queue. Meet >=95% tool selection and eligible exact arguments, >=99% structure, and zero unresolved critical authorization failures before activation. Tested source is published disabled: backend `a7acaefa4891`, frontend `ee6ffbaf750e`, all six remote heads verified. The additive migration and twelve knowledge records were applied; all sixty existing business-table counts stayed unchanged. Backend/frontend/database/Redis are healthy, anonymous AI access returns 401, and the shared inference start time and training process remained unchanged. Obtain activation authorization separately. Réservation is the next serial model-training stage; its local adapter and dataset preparation are documented separately.


## Reviewed conversation-reference update — 2026-10-11

IMPLEMENTED locally: complete saved selections are freshly authorized before model planning, preserving displayed order and inline-selection retry/page binding. Shared core 0.2.1 separates current-request language from history and validates explicit ordinal mutation targets. Native confirmation and actor history remain unchanged. Assistant suite: 84 tests and 6 subtests passed. One reviewer found no remaining code issues. Backend `f83393f6352e` is published to company/personal; its production restart awaits approval. Shared-model acceptance and feature activation remain incomplete.
