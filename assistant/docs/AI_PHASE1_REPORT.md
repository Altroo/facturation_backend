# Phase 1 implementation report — Chat AI Assistant

Date: 2026-10-08. Scope: **facturation only**. No Phase 2 integration was started. Source changes were made locally and delivered through Git. Production deployment/testing was explicitly authorized separately from Phase 2.

**Overall status: PARTIALLY IMPLEMENTED against the complete acceptance specification.** The implemented application features and security regressions are verified; broad model-quality targets are not met. Successful training and selected workflows do not establish full production readiness.

## Functionality and architecture

The reusable Python package lives in the central chat_ai_assistant workspace and is packaged as a pinned wheel plus a reviewable source snapshot in Facturation's backend. Django's chat_ai adapter reuses existing authentication, membership/role permissions, business calculations, serializers and history. The existing authenticated Next.js dashboard layout mounts one floating assistant. No new login, unrestricted database tool or separate application AI backend was introduced.

Implemented features include company-tab context with an authorized picker fallback; English/French conversation switching; invoice/client/product/date search; quotes, pro formas, credit notes, delivery notes, clients, articles, payments, staff-user lookup, stock and logistics reads; financial summaries; validated navigation and PDF actions; persistent company/user-scoped history; typed progress and message streaming; cancellation/retry; and a backend-permission-filtered slash catalogue for all currently supported modules. The detail-page list button resolves its correct list route rather than using browser history.

17 registered tools have strict schemas, filtered capability descriptions, fresh authorization, bounded results and audits. Specific tool coverage is in AI_TOOLS.md. Company IDs, role claims, prompts, retrieved text and stored references cannot grant authority. Financial cards use native application aggregates, including their existing status/date/currency rules. Unsupported profit/expense/conversion metrics are not invented.

Supported document/client metadata edits and deletions require a separate exact-target confirmation, fresh native permission, an unexpired fingerprint and atomic execution. Existing record history and a durable assistant audit identify the instructing user. Stock reversal for accepted delivery deletion uses the shared native service with locking and ownership checks. Financial line/price/payment changes, account administration and stock/logistics lifecycle writes remain outside assistant action coverage.

## User interface

The 56 px FAB is fixed at the bottom-right of authenticated dashboard pages, with safe-area/mobile positioning and collision handling for logistics controls. The responsive panel reuses the existing MUI/theme/buttons/modals rather than a separate visual system. User and assistant message boxes, clear New conversation/History controls, company scope, suggestions, slash descriptions and human form labels are implemented. Native modal layering, route preservation and the desktop-to-mobile drawer issue were tested and corrected.

Local actual-browser flows verified invoice/quote/article search, company switching, history, card-to-detail-to-list navigation, bilingual workflow delivery, exact positional follow-ups, financial queries and confirmed dummy metadata edits. Physical-device keyboard and comprehensive assistive-technology certification remain unperformed.

## Knowledge and data handling

12 reviewed bilingual documents cover real workflows, field labels and financial meanings. PostgreSQL stores versioned, capability/company-filtered knowledge; lexical ranking operates only after authorization. pgvector availability was evaluated, but embeddings are not installed for this small corpus. The sync command validates sources, detects changes, updates only affected records and removes obsolete global documents. Revocation and source-version changes invalidate saved explanations.

Verified general workflow questions retrieve reviewed current-language answers verbatim. Specific business searches use the local model. Exact ordinal follow-ups resolve saved authorized references through the same tool executor. These trusted handlers are not counted as raw-model successes. No production database records or private conversations were used for fine-tuning.

## Model and executed training

Selected for the authorized basic-workflow deployment: Qwen3.5-0.8B, Apache-2.0, server-tuned v4, quantized for the Colibri CPU engine. Immutable serving identifier: chat-ai-facturation-qwen08-v4-en-fr-20261008. Existing development, translation and grammar model services were not replaced.

Training actually ran on the Linux server: 410 steps, 593,920 trainable LoRA parameters, rank 8 on the last four layers, 14 CPU threads, validation loss 0.117782 to 0.068355. Total 4,339.35 seconds includes documented contention and a diagnostic pause; peak training RSS 11.16 GiB. Training checked the requested free-memory reserve. Adapter export, merge, Colibri conversion and artifact hashes were verified. No local training ran.

The synthetic v4 dataset has 410 training and 86 validation examples with separated families, capability-filtered tools and multi-turn scenarios. The independent evaluation was frozen before inference and kept out of training. Reproducible scripts/configurations, dataset checks, dependency pins, manifests, checkpoints and rollback are documented in AI_FINE_TUNING.md.

## Frozen model comparison

| Metric | Base | Tuned v4 | Target |
| --- | ---: | ---: | ---: |
| Tool selection | 44/80 (55%) | 50/80 (62.5%) | 95% |
| Exact arguments | 18/76 (23.68%) | 24/76 (31.58%) | 95% |
| Structured validity | 61/80 (76.25%) | 73/80 (91.25%) | 99% |

All three targets remain **UNMET**. The 80 cases are 40 English/French pairs across four capability profiles. Four knowledge paraphrase queries were excluded from exact-argument scoring a priori. Labels and scoring were not changed after predictions. Wrong operations, omitted filters/limits, changed values and malformed calls remain documented failures. Do not equate a schema-valid call with correct intent. Base quality-run timings overlapped training and are not a controlled speed comparison.

The local French status workflow initially produced a repetitive truncated call. Its failure is preserved; verified-help routing then passed exact retry in 0.826 s and fresh English workflow in 1.337 s. This fixes that application workflow without changing the frozen model score.

## Security and automated testing

The complete backend run passed 2,272 tests plus 30 subtests. Subsequent assistant changes passed 765 tests, followed by 52 focused review regressions after narrowing help routing. Four Docker/static-asset guards passed. Frontend final native navigation/chat checks passed 75 tests, TypeScript, ESLint and production build. Earlier wider suite outcomes and corrected expectations are recorded in AI_TESTING.md; a partial rerun is not mislabeled as a fresh full-suite run.

Security coverage includes anonymous access, role impersonation, cross-company IDs, restricted tools/counts/aggregations, invalid fields, prompt-like business text, permission revocation, source revocation, history isolation, stale references, unsafe navigation, cache/stream reauthorization and single-use confirmed writes. No known unresolved critical authorization bypass was found in this coverage. Permission decisions are tested in backend code, independently of model refusals. Confirmed changes were tested only against controlled local dummy records; production verification performs no business edit/delete.

Public-repository review found no real credentials or private business artifacts in the release payload. Runtime secrets, weights, adapters, browser authentication, screenshots, raw evaluations and backups are ignored. Runtime credential hashes matched no tracked source. Only reviewed examples, synthetic datasets and curated measurements are published.

## Measured server performance

Final isolated serving sample: 8/8 requests completed; four sequential requests and four with concurrency 2. Sequential mean 8.34 s, p95(maximum of 4) 9.74 s. Concurrency 2 mean 12.29 s, p95(maximum of 4) 17.66 s. Runtime decode 56.94 tokens/s excludes prefill. Peak process RSS 2.58 GiB with about four busy CPU cores. This small sample is not sustained production capacity certification.

Serving configuration: 4 threads / 4 CPUs, 6 GiB memory ceiling, 8,192 context, 512 output tokens, no-thinking, temperature 0, one KV slot and bounded queue. The lightweight assistant profile is separate from coding-model reasoning settings. Application inference leases, rate limits, deadlines, cancellation and history retention bound resource usage.

## Production verification

The authorized deployment has passed its infrastructure and core workflow checks; the prepared authenticated browser checklist passed 12 of 12 checks. Backend Git release b3fe974 passed checks, five migrations, 12-document synchronization and health. Private Colibri passed no-key 401, invalid-host 403, immutable-model identity and backend connectivity checks. Its network is internal, joins only Facturation, runs as non-root with a read-only model/root filesystem and publishes no host port. Public anonymous capabilities access returns 401. The frontend Linux build and health check passed. Authenticated browser verification has passed the dashboard FAB, bare-command help, natural invoice search, explicit detail-to-list navigation, English/French workflow explanations, collected-payment equality against native calculations, history, company isolation and article lookup. Mobile panel/composer fit at 390×844 and isolated public-login assistant absence also passed. Individual timings and the scope are recorded in the sanitized browser report. A later user-reported logistics-access question reproduced a model-path failure; the new trusted module-capability handler and expanded slash catalogue passed local regression tests. Their release verification is recorded separately.

## Files and operational handover

[implementation-files.json](implementation-files.json) inventories created/modified backend and frontend files against their release baselines. The generated backend assistant/SOURCE_MANIFEST.json records every centralized source/runtime/report file and hash. The wheel manifest records core hashes; model/training manifests separately identify private artifacts. No other application's source or integration was modified.

See AI_APPLICATION_DISCOVERY.md, AI_ARCHITECTURE.md, AI_SECURITY.md, AI_TOOLS.md, AI_KNOWLEDGE.md, AI_FINE_TUNING.md, AI_FRONTEND.md, AI_API.md, AI_AUDIT_HISTORY.md, AI_TESTING.md and AI_DEPLOYMENT.md. Deployment configuration includes private inference, resource limits, health/restart policies, a feature flag, retention scheduling and scoped Git hooks. Database backup was checked and prior application images/hooks/runtime environments retained for rollback. Rollback preserves durable actor histories.

## Remaining acceptance work and rollout gate

- Broad model tool/argument/schema quality remains below targets. Stronger CPU-compatible candidates and independently evaluated training are potential improvements, not completed results.
- Every supported module lacks an exhaustive real-model production workflow pass; complex filters can be omitted even when output is valid.
- Full physical-device, accessibility and sustained concurrency/load certification remain incomplete.
- Context automatically identifies an invoice detail; every possible selected resource is not automatically inferred.
- Supported writes cover the documented subset; the feedback API has no frontend feedback control. PDF downloads currently use native French endpoints.

Do not declare full Phase 1 acceptance or begin Phase 2 from this report. Request the user's review after actual production checks; explicit Phase 2 approval remains mandatory.
