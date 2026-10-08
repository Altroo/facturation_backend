# Verification and acceptance record

All application tests use controlled fixtures in the isolated local PostgreSQL database. No destructive test ran against production business data. Model selection metrics are separate from backend authorization tests.

## Backend

The latest assistant/stock/delivery suite passed **816 tests** in `backend-final-ai-stock.log` (47.44seconds), including native stock reversal, confirmation history and permission-filtered knowledge retrieval. The complete backend suite then passed **2,217 tests and 30 subtests** in76.04seconds. Seven initial async-task failures came from the demo settings overriding eager mode; restoring the inherited isolated-test behavior fixed them. The static-asset guard was updated for build-only non-secret environment assignments. Standalone vendored Colibri command-line diagnostics are explicitly excluded from Django pytest discovery.

Coverage includes anonymous/disabled access, existing roles, company and related-record consistency, global staff-user lookup, native stock-only superuser access, unsupported schemas, bounded search/detail/navigation, read-only stock/logistics services, financial calculations, revoked permissions, stale references, JSON/SSE/cached history delivery, prompt-like record data, knowledge-source revocation, split-token human labels, and single-use confirmed mutation with durable actor audit.

Run from `facturation_backend`:

```sh
.venv-mac/bin/python -m pytest chat_ai/tests.py chat_ai/test_*.py \
  --ds=facturation_backend.settings_ai_test --reuse-db -q
```

Use pytest, not Django's unittest runner: these tests are pytest functions. Do not run concurrent test processes against the same reused database.

## Frontend

The whole-project run covered251suites/2452tests, with five stale expectations corrected (explicit list navigation and existing logistics endpoint coverage). The affected167tests then passed. The final retry-context pass added four regressions and passed62chat tests; TypeScript, ESLint and the assistant-enabled production build passed. Retry retains original invoice/language context after route changes.

Set `NEXT_PUBLIC_DOMAIN_URL_PREFIX=''` when running local route tests; the actual app reads this configured prefix. Do not change production route constants to compensate for a missing test environment variable.

```sh
NEXT_PUBLIC_DOMAIN_URL_PREFIX='' bun x jest src/components/chat-ai \
  src/components/pages/dashboard/shared/company-documents-list/companyDocumentsWrapperList.test.tsx \
  src/components/pages/dashboard/shared/company-documents-view/companyDocumentsWrapperView.test.tsx --runInBand
NEXT_PUBLIC_DOMAIN_URL_PREFIX='' bun x tsc --noEmit --incremental false
```

## Real browser checks completed

MCP Playwright uses the dedicated QA tab with a real local Next/Daphne/Colibri setup and guarded synthetic application records.

- Desktop/mobile placeholder center measured exactly equal to input-container and send-button centers.
- Approved theme blue and white icons; decorative/redundant controls removed.
- Bare `/voir` returns usage and an example in an assistant message box.
- AI result → invoice detail → explicit invoice list preserves company context, rather than browser history.
- Company switch clears old scope; history previews and exact-row deletion were checked.
- At a 390×360 short viewport the composer remained reachable; no horizontal overflow. This is not a physical-device virtual-keyboard test.
- Confirmed a dummy invoice note edit through the actual preview/modal/API. UI displayed **Remarque**. Database verification found `AI Test editor` in the durable AI audit, a request instruction identifier, and `ai-editor@example.invalid` in the native document history. Evidence: `confirmed-form-labels.png`.

The latest added module cards have passing renderer/permission tests; complete real-model browser flows for every module are still pending. Do not describe mocked-provider security tests as actual model E2E accuracy.

## Model and operational acceptance still open

V2 has 104 held-out multilingual cases. The historical base/tuned v2 runs completed below acceptance. English/French v3 completed below target; expanded v4 training is active. Compare actual base/tuned results under identical frozen inputs. CPU decode speed is not available from buffered Colibri tool streams; end-to-end tokens/time is reported instead.

Still required: v4 held-out scores and failure analysis, model knowledge factuality, dedicated final model CPU/RAM/concurrency/P95 measurements, production acceptance and final report. Isolated Linux application-image build, fresh PostgreSQL migrations and12-document synchronization passed; later changes require the release image rebuild. Lexical retrieval development checks passed20/20top-three and15accent/plural variants top-one. Background development activity can affect local latency; dedicated server measurements must decide deployment limits. Physical mobile keyboard/assistive-technology testing remains an explicit limitation.

## Additional real checks
- Human-labelled payment-terms shortcut: real API preview uses **Termes de paiement**; raw database key absent. No additional edit was confirmed during this check.
- Real local model article search returned AI-E2E with existing field labels. Card → article detail → explicit article list preserved company and chat state.
- Real local model stock question failed intent selection: returned an inventory instead of quantities. This remains a recorded E2E failure.
- Frontend production build passed. Isolated Linux Colibri Docker image passed authenticated private-host/auth-denial checks as non-root, read-only, no published ports; container removed. `docker-validation.json` records image hash and the corrected initial shard-permission failure.

Latest scope correction: English/French only.275 affected backend tests and101 chat frontend tests passed after runtime schema/fallback/context changes. Language detection checks cover both switch directions and validated interface fallback. Completed language-scope model results are recorded in AI_FINE_TUNING.md; v4 remains unfinished.

Final dummy UI confirmation replay was verified before and after execution. The invoice remark, native history actor and durable AI actor ID match the authenticated `ai-editor@example.invalid`. Production business mutations are excluded from smoke testing.
