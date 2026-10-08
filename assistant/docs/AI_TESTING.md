# Verification and acceptance record

All application tests use controlled fixtures in the isolated local PostgreSQL database. No destructive test ran against production business data. Model selection metrics are separate from backend authorization tests.

## Backend

The latest assistant/stock/delivery suite passed **816 tests** in `backend-final-ai-stock.log` (47.44seconds), including native stock reversal, confirmation history and permission-filtered knowledge retrieval. The complete backend suite then passed **2,272 tests and 30 subtests** in78.67seconds after the final routing and bilingual-knowledge fixes. Seven initial async-task failures came from the demo settings overriding eager mode; restoring the inherited isolated-test behavior fixed them. The static-asset guard was updated for build-only non-secret environment assignments. Standalone vendored Colibri command-line diagnostics are explicitly excluded from Django pytest discovery.

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

## Final model measurements and acceptance

Server-only v4 training, conversion, the frozen 80-case comparison and dedicated performance measurements are complete. Tool selection improved from44/80 to50/80; exact arguments from18/76 to24/76; structured output from61/80 to73/80. The95/95/99% targets remain unmet. Failure examples and immutable methodology are in AI_FINE_TUNING.md and curated training/reports; no labels or scoring were changed after inference.

The separate final server sample completed8/8requests: sequential mean8.34s, p95(maximum of4)9.74s; concurrency2 mean12.29s, p95(maximum of4)17.66s; runtime decode56.94tokens/s excluding prefill, peak process RSS2.58GiB, approximately4busy CPU cores. This small sample is not broad load certification.

Approved bilingual retrieval replaces unreliable generated workflow prose. Development retrieval regressions passed20/20top-three and15accent/plural variants top-one. Physical-device virtual-keyboard and assistive-technology certification remain unperformed. Broad model acceptance is explicitly incomplete.

## Additional real checks
- Human-labelled payment-terms shortcut: real API preview uses **Termes de paiement**; raw database key absent. No additional edit was confirmed during this check.
- Real local model article search returned AI-E2E with existing field labels. Card → article detail → explicit article list preserved company and chat state.
- Real local model stock question failed intent selection: returned an inventory instead of quantities. This remains a recorded E2E failure.
- Frontend production build passed. Isolated Linux Colibri Docker image passed authenticated private-host/auth-denial checks as non-root, read-only, no published ports; container removed. `docker-validation.json` records image hash and the corrected initial shard-permission failure.

Latest scope correction: English/French only.275 affected backend tests and101 chat frontend tests passed after runtime schema/fallback/context changes. Language detection checks cover both switch directions and validated interface fallback. Completed language-scope model results are recorded in AI_FINE_TUNING.md; v4 training/evaluation is complete and remains below acceptance targets.

Final dummy UI confirmation replay was verified before and after execution. The invoice remark, native history actor and durable AI actor ID match the authenticated `ai-editor@example.invalid`. Production business mutations are excluded from smoke testing.


Final local browser retests passed invoice/client-and-product search, quote search, invoice/quote detail-to-list navigation, history restoration, company switching without old-scope content, and verified English workflow followed by French status explanations. Confirmed dummy edit replay preserves its native/durable actor history. V4 retests passed explicit collected-payment summaries in both languages and exact positional follow-ups. The original failures remain in raw evidence; no blanket model acceptance is claimed.


Exact English/French positional follow-ups now resolve through stored conversation references and the same authorized `previous_results` tool. Twenty-eight new tests cover normal positions, negation, extra conditions, mismatched resource names, foreign records, expired state, revoked membership and out-of-range indexes. The complete assistant suite passed747tests after this change. This is application-side reference resolution; it does not change frozen raw-model evaluation scores.


## Final regression sequence

After the full2,272-test backend run, the assistant suite passed765tests (39.13seconds). The final independent review then narrowed help routing to avoid overriding specific-record and compound requests;52focused reference/help tests passed after that change. Four Docker/static-asset tests passed after excluding additional runtime secret patterns. The frontend's last native-navigation/chat run passed75tests, TypeScript, ESLint and production build. Actual MCP desktop-to-mobile resizing, drawer Escape/roundtrip, single FAB and chat accessibility passed.

The local v4 French status explanation initially failed with a truncated repetitive model call. That failure is retained in final-local-v4-ui-review.json. Exact retry after verified-help dispatch passed in0.826s; a fresh English workflow passed in1.337s. These trusted application handlers are excluded from raw-model accuracy figures.


## Module catalogue regression — 2026-10-08

The full assistant/backend suite passed **819 tests in 44.16 seconds** after the permission-derived module catalogue and exact capability-question handlers. Chat UI/client tests passed **112 tests in 7.73 seconds**; TypeScript and changed-file ESLint passed. Tests cover every bare module's existing tool mapping, usage examples, filter-preserving planner hints, native staff-only users, stock-only superusers without membership, denied write shortcuts, localized capabilities and the exact English logistics-access question without model inference or business queries. Raw logs remain ignored.

The prepared authenticated production checklist separately passed **12/12 checks**: one dashboard FAB, current company, bare help, natural invoice lookup, safe detail/list navigation, English/French workflows, verified collected-payment equality, history, company isolation, article lookup, mobile fit and anonymous-login absence. These selected application workflows do not replace the frozen model benchmark. Additional module-shortcut deployment verification is recorded after release.
