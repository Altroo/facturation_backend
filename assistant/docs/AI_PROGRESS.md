# Phase 1 progress — facturation

Current step: corrected starter-question release deployed and verified; Phase 1 implementation report remains available for user review. Other applications remain untouched. Broad model-quality acceptance is incomplete; do not interpret successful basic workflows as a 95% accuracy result.

## IMPLEMENTED and verified
- Reusable Python provider/orchestrator/registry, Django integration,17 typed tools, native permissions, company/object checks, bounded read results, safe navigation and financial calculations reused from Facturation.
- Supported document/client edits and deletion require exact-target confirmation and fresh native permissions. Native history and durable AI audit identify the requesting user. Stock reversal for delivery deletion uses the shared native service.
- Authenticated root FAB, native theme/components, responsive chat, company-tab scope, history, cancellation, retries, slash help, human form labels and explicit detail-to-list navigation.
-12 reviewed bilingual knowledge documents, incremental synchronization, permission filtering before ranking, exact-version history protection. General help delivers verified procedures; specific business questions use the local model. Exact positional follow-ups use authorized saved references.
- Server-only v4 LoRA training completed410steps; validation loss0.117782→0.068355. No private business records used. Colibri CPU export and artifact hashes verified.
- Current production: all three repositories released through local commits/Git; all nine remote heads verified. Backend and frontend native HTTP routes return 200; private model remains healthy with the same model identity and start time.
- Latest module-shortcut changes: 819 assistant/backend tests and 112 chat frontend tests passed; TypeScript, ESLint and the assistant-enabled production build passed.
- Full backend2,272tests+30subtests passed; final assistant765tests passed, then52 focused help/reference regressions after review. Four Docker/static-asset tests passed. Frontend75 final native/chat tests, TypeScript, ESLint and production build passed.
- Real local v4 checks passed invoice/client/product search, quote/article search, EN/FR collected-payment summaries, unpaid/ordinal follow-ups, navigation/list return and reviewed EN/FR workflow answers. Original model failures remain recorded separately.
- Public-repository audit found no actual credentials or private business artifacts in release commits. Runtime environments, keys, browser state, raw reports, weights and checkpoints are ignored. Application code is edited locally and released via Git pushes.

## Suggestion-button update — 2026-10-09
- IMPLEMENTED: complete permission-filtered English/French starter questions, immediate sending on click, active-company isolation and explicit click-to-send instructions. Slash-menu entries remain editable drafts.
- Validation: 831 assistant backend/security tests and 115 chat frontend tests passed; TypeScript, ESLint, production frontend build and source/wheel checks passed. The single reviewer found no unresolved code issues.
- Initial production UI release: each of the five questions sent exactly once in the active company. Unpaid invoices, recent quotes, stock and invoice workflow completed safely; desktop/mobile fit, native English metadata and slash drafting passed.
- Preserved failures: original logistics wording returned INVALID_MODEL_OUTPUT; its clearer French/English replacement completed successfully as separate normal chat requests. An English fresh-conversation unpaid search incorrectly selected the previous-results tool; audit confirmed CONTEXT_EXPIRED from that unavailable tool, with unchanged user authorization. The corrected catalogue omits this tool until a nonempty result set exists. A private provider probe then selected the correct unpaid-invoice search. The stock probe confirmed the native minimum-status filter; empty production cards alone were not treated as filter evidence.
- Final corrected release: 10/10 actual production button-click checks passed (five French, five English), with one exact request per click and correct company scope. Both final stock questions independently selected the native minimum-status filter in private provider probes. Source heads and installed wheel were verified, services healthy, model unchanged. Observed production stock lists were empty; no live threshold values were inferred. Evidence: [sanitized starter checks](../training/reports/production-starter-suggestions-checks.json).
- These targeted checks do not replace the held-out model evaluation, whose last recorded scores remain below target. The catalogue correction has not been rescored against that dataset.

## Measured model limits
Frozen independent80 cases: tool selection50/80 (62.5%); exact arguments24/76 (31.58%); schema73/80 (91.25%). Base:44/80,18/76,61/80. Targets95/95/99 are UNMET. Complex filters, limits, operation choice and malformed calls remain weaknesses. The application's deterministic help/reference handlers are not credited as model accuracy.

Dedicated server8-request sample: sequential mean8.34s, p95(maximum of4)9.74s; concurrency2 mean12.29s, p95(maximum of4)17.66s. Decode56.94tokens/s excludes prefill; peak process RSS2.58GiB and about4busy CPU cores. This small sample is not a load-capacity certification.

## Production verification
- Prepared production checklist: 12/12 passed, including dashboard FAB, invoice/article search, financial equality, company/history isolation, bilingual workflows, navigation, mobile fit and public-login absence. The new module release passed nine additional production checks: permitted catalogue, English/French capability answers, stock/logistics/article reads, described article search and desktop/mobile menu fit.

## PARTIALLY IMPLEMENTED
- Overall model acceptance remains below target, despite passing the tested basic application workflows.

## Remaining limitations
- Complex model requests may omit filters or ask for clarification; inspect returned record details before selecting an action. Exact-target confirmation is mandatory for supported writes.
- Stock, logistics, account and payment adapters are read-only. Supported writes are bounded document/client actions, not all operations in every module.
- Full physical-device keyboard and assistive-technology certification remains unperformed.
- No Phase2 integration or approval is implied.

Historical work log: [AI_PROGRESS_HISTORY.md](AI_PROGRESS_HISTORY.md). Detailed evidence: [AI_TESTING.md](AI_TESTING.md), [AI_FINE_TUNING.md](AI_FINE_TUNING.md), and training/reports.
