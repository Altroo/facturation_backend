# Phase 1 progress

Current phase: **facturation only**. Current step: final server model training/evaluation, then authorized production release and browser verification. The user authorized pushes to all three remotes and production testing. Phase2 is not authorized.

## Current verified status (2026-10-08)
- IMPLEMENTED: shared Python core, native Django authentication/permissions,17typed tools, company/user-scoped history, context, safe navigation, permission-filtered knowledge and audit.
- IMPLEMENTED: bounded supported document/client edits and deletion require native rights plus exact-target confirmation. Native and durable AI histories identify the requesting user. Delivery deletion shares verified stock reversal with native endpoints.
- IMPLEMENTED: authenticated root floating chat, native components/theme, human field labels, useful slash help, structured cards, automatic English/French response policy, explicit company-aware list routes, retry preserving original context, restored confirmation history.
- IMPLEMENTED:12approved PostgreSQL knowledge documents; incremental synchronization and permission filtering before ranking.43retrieval regressions and16confirmation-history tests passed; development recall20/20top-three. Model explanation factuality is still separate acceptance work.
- IMPLEMENTED: all 2,217 backend tests and 30 subtests passed in 76.04 seconds. Focused assistant/stock/delivery suite: 816 passed. Frontend full-project run's five stale assertions were corrected;167affected tests passed, followed by 62 chat tests after the retry fix. TypeScript, ESLint and final production build passed.
- IMPLEMENTED: English/French v3 server-only training completed192steps; same-server52-case tuned evaluation42/52tools,27/50arguments,51/52schema, below acceptance. Full hashes and synthetic evidence preserved.
- PARTIALLY IMPLEMENTED: expanded v4server-only training (410train/86validation) is active, with independent80-case acceptance frozen before use. Base result44/80tools,18/76arguments,61/80schema. No v4success or accepted adapter is claimed.
- IMPLEMENTED: isolated Linux backend/model image checks, fresh PostgreSQL migrations and knowledge synchronization passed. Source changes since these checks require final release builds.
- IMPLEMENTED: server-local restricted DB backup, rollback image tags, backed-up scoped deployment hooks installed. Dedicated inference key and disabled backend feature configuration staged. Existing application containers and development/translation/grammar models unchanged.
- PLANNED: final model export/evaluation, dedicated performance measurements, release pushes, production activation and authenticated browser verification. Production login remains user-controlled; no business mutation smoke tests will run there.
- LIMITATIONS: supported writes are bounded document/client actions; stock/logistics/account/payment writes remain outside this implementation. General record context is limited to invoices; result cards and follow-up references cover other supported modules. Physical-device keyboard and full screen-reader testing are not claimed.

The entries below are a chronological work log; older statuses are superseded by the current status above.

- IMPLEMENTED: source inventory and discovery documentation, verified against both current checkouts.
- PLANNED: reusable provider/orchestrator/tool registry, Django adapter/API/history/RAG, floating UI, local model benchmarks, dataset generation, training, security and end-to-end tests, deployment configuration.
- Training: not executed. Baseline: not measured. No model selected yet.
- No other applications modified; existing three AI workloads left untouched.
- Permission policy: reuse current membership-based read access, including financial reports, per explicit user clarification.

## Repository-grounded plan
1. Reusable Python core + private replaceable Colibri provider; host orchestration in facturation Django.
2. Bounded read tools reuse existing models, filters and financial helpers; company authorization checked at every invocation.
3. Versioned authenticated chat API, scoped history, reference state, audit and approved knowledge synchronization/retrieval.
4. MUI bottom-right FAB and responsive panel mounted once in dashboard layout; structured cards and safe routes.
5. Benchmark small local models on held-out multilingual facturation intents; train LoRA on the approved SERVER only and evaluate the exported model with Colibri.
6. Security/backend/UI/E2E tests, actual performance measurements, deployment files and honest completion report. Stop for user approval; no Phase 2.

## User corrections
- Colibri ONLY for inference; aborted llama.cpp bootstrap and removed its downloaded runtime/GGUF artifacts. No llama.cpp inference ran. Re-evaluating supported small architectures.
- Four server models installed; three active (development, translation, grammar), per user. New assistant is fifth installed/fourth active only after deployment approval.
- Follow currently selected company tab; when absent require authorized company selection before business queries. Conversations remain company-scoped.

## Implemented code awaiting full validation
- Shared core provider, native tool selection, typed tool registry.
- Facturation membership adapter, invoice/client/payment/report/navigation tools; history models/API/SSE; approved lexical knowledge retrieval and sync command.
- MUI panel/FAB, scope isolation and active company-tab bridge; initial TypeScript findings being corrected.
- Local synthetic PostgreSQL database migrated; no production data copied.
- User supersedes read-only restriction: editing/deleting must follow existing permissions, with exact action preview and confirmation. Implementing bounded confirmed writes; no bulk financial operations.
- Qwen3.5-0.8B conversion required materializing tied output embeddings. Lossless preparation script added; engine unchanged. Runtime validated locally for CPU inference; held-out benchmark running.


## 2026-10-08 verification update
- IMPLEMENTED: edit/delete history uses the authenticated user; durable write audit preserves actor identity and original request correlation after conversation/account deletion. 54 backend tests passed before adding three capability checks.
- IMPLEMENTED: frontend type check passed; permitted shortcuts now reflect each company's existing role. Browser validation remains pending.
- PARTIALLY IMPLEMENTED: 96 synthetic training examples, 16 validation examples, 48 held-out test examples across English/French/Arabic/Darija generated from verified tools. No private database data used. Baseline tool benchmark running.
- Training location correction: user explicitly requires SERVER training only. No local fine-tuning has run. Server environment and bounded CPU training pipeline are being prepared; training remains unexecuted.
- Server read-only refresh: Ryzen 7 7700, 16 logical CPUs, 62 GiB RAM, 37 GiB available, 134 GiB disk free. Temporary job resource limits verified: CPUQuota 200%, MemoryMax 8 GiB, MemorySwapMax 0, low CPU weight. No active model service modified.

- User increased training allowance: up to 90% of server CPU, preserving approximately 10% memory headroom. Use 14 PyTorch threads (16 logical CPUs) and a 1440% systemd CPU quota; earlier two-core restriction superseded.

## Active user-reported fixes
- PLANNED: Detail-page "Back to list" uses browser.back and returns to the previous page after an AI link. Replace that behavior with the correct document list route and active company context; cover AI-to-detail-to-list with browser regression tests.
- PARTIALLY IMPLEMENTED: `/voir` and other slash prefixes accept descriptions; search by client/product/date, including actual Devis entities. Authorized result selection can prepare deletion or open the existing edit form. Expanded security tests being run.
- PARTIALLY IMPLEMENTED: replace generic chat UI with existing TextButton, ActionModals, DashboardStatCard, DarkTooltip and Sass tokens. Move labelled conversation controls above company context; add visible slash explanations/examples. Manual language selector removed.
- IMPLEMENTED: first server-only LoRA optimization completed (96 steps, 593,920 trainable parameters, 611.8 seconds, peak RSS 6.60 GiB). Validation loss 0.20077 → 0.12091. This does not establish held-out improvement or deployment readiness. Adapter not deployed. The first dataset predates expanded quote/product searches and automatic-language changes; further evaluation/dataset revision required.
- Base 0.8B native-tool benchmark (48 synthetic prompts, local Colibri CPU): tool selection 54.17%, exact argument correctness 25%, schema validity 83.33%; below acceptance. A first-visible-event decode-rate calculation was invalid because Colibri buffers tool calls; corrected reports use end-to-end throughput instead. 2B comparison in progress.
- PLANNED UI bug from `[local workspace] 2026-10-08 at 12.21.14.png`: "Nouvelle conversation" and "Historique" controls are oversized; the new-conversation label wraps inside a large pill. Make this a compact single-line toolbar with restrained spacing and existing application styling. Verify visually at desktop/mobile sizes.
- PLANNED coverage expansion requested by user: action shortcuts must work across actual Facturation modules (users, devis, pro forma, client invoices, credit notes, delivery notes, logistics, stock, and remaining discovered modules). Reuse action commands; do not invent one command per module or offer unimplemented actions. Build a verified capability/permission matrix and extend registered adapters incrementally. This remains within facturation only.


## 2026-10-08 independent review and UI correction pass
- User requests cavecrew self-reviews. One UI reviewer now owns visual/interaction review; separate backend/security review is used for authorization work.
- IMPLEMENTED: assistant text, help and result cards have a labelled message box; streaming/loading use the same box. Removed decorative welcome search icon and redundant minimize button; close preserves the conversation.
- IMPLEMENTED: actual application theme blue reused (browser computed `rgba(2, 116, 215, 0.5)`), white floating/send icons as explicitly requested. Existing TextButton foreground retained for readable small labels. Composer placeholder alignment measured at zero vertical offset; mobile text is 16px to avoid focus zoom.
- IMPLEMENTED: details return to explicit module lists with company context, rather than browser history. Shared document/list wrapper tests cover all five document types and company URL/manual-tab behavior. Root company resolution validates authorized hints and retains the latest detail-company scope across ordinary navigation.
- PARTIALLY IMPLEMENTED: history previews and target-specific delete controls, scroll-follow behavior and compact mobile shortcut help are under the UI review pass.
- IMPLEMENTED: planner now requires one schema-valid registered tool call. Clarifications use bounded reason/language codes and backend-owned text; arbitrary model prose cannot be presented as verified financial output.
- IMPLEMENTED: saved knowledge answers bind to original document versions and recheck all source permissions. Source authorization is also rechecked before each generated knowledge delta and before persistence; concurrent-revocation tests are being added.
- Base 2B comparison completed: 48 held-out pilot prompts; tool accuracy 79.17%, argument correctness 52.08%, schema validity 100%; mean latency 22.591s and p95 23.871s on local M4 Colibri CPU (4 threads). Base 0.8B: 54.17% / 25% / 83.33%. Neither meets acceptance. These historical pilot numbers precede the stricter clarification contract; rerun both base and tuned models with the final same contract before selection.
- Fine-tuned export exists on approved server. Transfer to local evaluation storage is incomplete; do not load the partial directory. No tuned inference score reported.
- Existing server model services unchanged. No production deployment; remaining five ecosystem applications untouched.

## 2026-10-08 visible labels and deployment verification
- IMPLEMENTED: native form labels for generated/replayed prose, confirmations, human-labelled shortcut parsing, and history titles. CamelCase aliases covered; stored user instructions stay unchanged. Native Nectar article price caption/visible values respected. Browser `/modifier 0901/26 Termes de paiement 30 jours` displayed the exact form label and no DB key.
- IMPLEMENTED: actual article model search/card/navigation and explicit article-list return with company context; conversation persisted.
- PARTIALLY IMPLEMENTED: real model stock question selected an inventory instead of a stock balance. Card authorization/type was correct, intent selection was wrong. Retained as a model-quality failure, not an E2E pass.
- IMPLEMENTED: Linux model container validation found and fixed private hostname rejection, architecture selection, and converted shard read permissions. Backend image now excludes `.env*`; collectstatic uses non-secret build-only settings. Test container removed; existing production services unchanged.
- Model scoring correction: knowledge argument cases must be unscored independently of prediction. Original outputs preserved; `summary-scoring-v2.1.json` records base 54/104 tool, 27/100 arguments, 68/104 schema. These targets remain unmet.

- PARTIALLY IMPLEMENTED: tuned v2 held-out77.88%tools /47%arguments /97.12%schema. Training materially improved the base but targets remain unmet; adapter not accepted. Server runtime profile measured54.05decode tokens/s, excluding prompt prefill.

## English/French scope verification
- IMPLEMENTED: only `fr`/`en` advertised and accepted for generated clarifications; current-message inference normalizes accents and handles English/French switches without a selector. Validated interface context reaches knowledge fallback/prompts.
- Verified275 affected backend regressions and101 assistant frontend tests. Active v3 contains76train/18validation/52held-out English/French rows. Historical data/results preserved.
- New trainer/evaluator/performance entry points reject out-of-scope datasets. English/French-only server run started as chat-ai-training-v3-en-fr-20261008:192steps,14threads,CPU quota1440%,30GiB ceiling,10%spare-memory guard. Dataset hashes verified on server. IN PROGRESS; no successful result claimed.

## Release authorization and current regression check
- User explicitly requested completion, testing, pushing to all three remotes and production testing. This supersedes the previous no-deployment authorization status; Phase 2 remains out of scope.
- IMPLEMENTED: all 582 backend tests passed in 34.01 seconds after English/French updates (`backend-en-fr-full.log`). No final model accepted yet.

## Authorized release validation and broader training
- IMPLEMENTED: v3 English/French-only CPU training completed on server:192steps,1312.50seconds, validation loss0.145492→0.093479, peak process RSS12,552,432KiB. Export and Colibri conversion completed. Base/tuned52-case evaluation is running; no acceptance score claimed yet.
- IN PROGRESS: v4 server-only training uses410 independently authored training examples and86 validation examples with all17tools, scoped capability schemas and multi-turn histories; separate80-case English/French acceptance set frozen before model use.
- IMPLEMENTED: backend Linux image build passed; isolated PostgreSQL container check, fresh migrations, migration-state check and12-document knowledge synchronization passed. Validation containers/network removed. Image sha256:4a885c2525fb6465be272ab4726f44fa19d13dd1da78e21b96b549293c511fef. Later source corrections still require final release rebuild.
- IMPLEMENTED: daily03:20 native Celery expiry cleanup, including feature-disabled cleanup, preserves confirmed mutation actor audits.
- IN PROGRESS: native/assistant delivery deletion stock reversal and confirmation-history persistence fixes found during independent release reviews.
- Authorization: source-context upload was initially rejected by automatic review; user explicitly approved the exact682-file2MBarchive/server destination. Upload and isolated image checks then succeeded.

## Final release regression pass
- IMPLEMENTED: 816 assistant/stock/delivery backend tests passed in47.44seconds; migration generation check reports no changes.
- IMPLEMENTED: whole frontend run covered251suites/2452tests; five obsolete assertions identified (four browser-back expectations, two newly existing logistics endpoints absent from endpoint coverage). Corrected affected suites passed167tests in16.53seconds; TypeScript, ESLint and production build passed. A further retry route-context regression is being fixed before release.
- IMPLEMENTED: authorized lexical knowledge development recall20/20top-three;15accent/plural variants top-one;43retrieval tests plus16confirmation-history tests passed. This is development retrieval evidence, not held-out model answer accuracy.
- IMPLEMENTED: independent80-case base0.8B evaluation completed:44/80tool selection,18/76arguments,61/80valid structure. Temporary base inference service stopped to release CPU for v4training. Performance was under concurrent training load; no dedicated latency claim.
- PARTIALLY IMPLEMENTED: v4training is advancing through baseline validation. Profiling identified CPU/OpenMP contention, not deadlock or memory exhaustion. No completed v4training or accepted adapter is claimed.
