# Contracts assistant progress

Application: `contrat`. Status: PARTIALLY IMPLEMENTED; tested source is published with production activation disabled. Model acceptance remains incomplete.

## Current training preparation — 2026-10-11

The current prepared dataset is `contracts-dialogue-v2-en-fr`: **153 / 44 / 78 training / validation / held-out examples**. Its cumulative shared stage is `shared-v6r4-en-fr`: **1,866 / 319 / 516** in the same order. Original logical prompts, expected actions and split membership are preserved. Updated inputs match the reviewed native planner, current-message language, calendar context and explicitly synthetic ordered references. Added neutral greeting/thanks histories are variants, not independent scenarios.

The complete cumulative six-app preparation passed metadata-only tokenizer/Colibri checks without loading local weights. Exact predecessor prefixes, source dependencies and manifests are pinned. This is preparation, not a measured Contracts model score. The sole active optimization is shared V5r4; subsequent stages remain **Contracts → Gestion Magasin → Réservation**, one at a time after predecessor acceptance. See the [current training queue](AI_TRAINING_QUEUE.md) for the shared evidence and launch gates. Earlier dataset counts below describe the preserved initial preparation.

## IMPLEMENTED and verified locally

- Native permission/company-scoped registry, bounded searches, contract/project/user retrieval, approved navigation, scoped PDF/Word delegation, confirmation-only native writes, actor history and audit.
- User/company-scoped conversations, saved references, retention command, request cancellation, retry identifiers, safe history replay and permission-aware knowledge.
- Canonical responsive MUI interface in the authenticated root, local robot, company choice, EN/FR starter questions, described-record shortcuts, bare-command usage, greeting/thanks handlers and structured cards.
- Eight approved bilingual knowledge records and incremental synchronization, including scope/sensitivity validation.
- Final full backend suite: 576 tests plus 4 subtests passed. The focused assistant security/API suite contains 56 tests plus 4 subtests. These are application tests, not model accuracy.
- Focused frontend suite: 63 tests passed, including company-hint navigation and theme provider. Final assistant/form subset: 60 tests passed. TypeScript, scoped ESLint and the final assistant-enabled production build passed.
- Actual local browser checks: dummy JWT login, greeting, `/voir` help, `/contrats` returning only the selected company's synthetic contract, card-to-detail navigation, explicit list return, native PDF download, both company scopes, preserved chat, 390×844 and 390×420 layouts, and native-overlay priority. Read-only login hid mutation/print/admin controls, rejected a delete command and isolated history. A disposable contract deletion required confirmation and recorded the instructing user in native history and the assistant audit. Reopened results removed the deleted record; per-turn English/French text remained intact. Eight light/dark, empty/filled, shortcuts open/closed screenshots were compared with Design Workflow at matching scroll positions; all six canonical MUI source files match. No browser API responses were substituted.

## PREPARED, not trained

`training/datasets/contracts-v1-en-fr` contains 122 training, 30 validation and 78 held-out cases. The generator uses the actual registry/planner and blocks database queries. Values are synthetic; languages are English and French only. Paired translations stay within one split. Exact prompt overlaps are rejected; semantic-independence limitations are documented in the manifest.

No Contracts model score is available. The server tokenizer/Colibri preflight passed all 1,440 shared training and 198 validation rows: exact parser round trips, prompt/template parity, loss boundaries and semantic alignment. Maximum lengths were 4,744/4,977 tokens within the 8,192 budget. This loaded tokenizer metadata only and started no training. Base/candidate evaluation, serial server training and shared regression acceptance remain PLANNED. Do not represent a dataset or test count as fine-tuning success.

## Remaining gates

- Natural-language model-driven flows remain unevaluated; local browser checks exercised real native handlers and confirmed selections, not substitute model responses.
- Freeze source/dataset provenance before baseline measurement.
- Finish the current shared V5r4 training/export/evaluation before any new training process starts.
- Retain all three existing application curricula and frozen evaluation sets when adding Contracts to the same shared model.
- Meet at least 95% tool selection and eligible exact arguments, 99% valid structure, and no unresolved critical authorization failures. Report failures honestly.
- Obtain activation authorization after model acceptance. Management Projet remains disabled as previously instructed.

The independent Contracts/Réservation login-theme correction is published to all remotes and verified live. It does not activate this adapter.

## Disabled source release

Backend `00503a910cda` and frontend `875524520cc0` are published to company, personal and production; all six heads match. Central preparation `bb51d7ff6eca` is published to its three remotes. Production builds passed. The additive assistant migration and eight-document knowledge synchronization passed; existing contract, project and user row counts remained unchanged. A validated private database restore file remains on the server. Web/database/cache/frontend containers are healthy; the worker is running. Exact login and native health routes return HTTP 200; anonymous assistant access returns 401. The production feature flag is false. The shared training process identity remained unchanged. These checks establish a disabled source release, not live assistant/model acceptance.


## Reviewed conversation-reference update — 2026-10-11

IMPLEMENTED locally: complete saved selections are freshly authorized before model planning, preserving displayed order and inline-selection retry/page binding. Shared core 0.2.1 separates current-request language from history and validates explicit ordinal mutation targets. Native confirmation and actor history remain unchanged. Assistant suite: 84 tests and 10 subtests passed. One reviewer found no remaining code issues. Backend `d2347ff8f402` is published to company/personal; its production restart awaits approval. Shared-model acceptance and feature activation remain incomplete.
