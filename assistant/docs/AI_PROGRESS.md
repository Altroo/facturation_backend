# Phase 1 progress — facturation

## Current shared-model and rollout status — 2026-10-11

IMPLEMENTED: V5r4 server training completed all 1,713 updates with complete application coverage and finite losses; isolated Colibri export succeeded. Training plus validation took 43,667.51 seconds (12 h 7 min 48 s); peak process RSS was 7.27 GiB. Weighted validation loss increased from 0.108923 to 0.113955; unweighted loss increased from 0.050710 to 0.054139. This does not establish an improvement. [Training evidence](../training/reports/shared-v5r4-en-fr-training.json).

PARTIALLY IMPLEMENTED: all 438 frozen cases completed freshly on the exported V5r4 candidate. Tool selection is 390/438 (89.04%), eligible exact arguments 284/334 (85.03%), and valid structure 434/438 (99.09%). Baseline values were 386/438 (88.13%), 277/334 (82.93%) and 425/438 (97.03%). Overall and per-set acceptance remain unmet, including clarification/target-selection failures. The original inputs, labels, evaluator and scores are preserved. Production inference and disabled-feature settings remain unchanged; no next application training has started. [Full evaluation](../training/reports/shared-v5r4-en-fr-evaluation.json).

IMPLEMENTED: the isolated eight-request warm performance sample completed without errors. Sequential mean 7.92 seconds, p95 8.09 seconds; concurrency-two mean 11.87 seconds, p95 16.16 seconds. Raw decode throughput 54.52 tokens/second excludes prefill/queueing. Peak process RSS 2.66 GiB; approximately four busy CPU cores. With four requests per group, p95 is the observed maximum; this is not a load-capacity certification. [Performance evidence](../training/reports/shared-v5r4-en-fr-performance.json).

IMPLEMENTED locally and reviewed: Contracts, Gestion Magasin and Réservation now validate the complete saved selection before planning, provide identifiers in display order, and preserve selected-card retry/page binding. Missing or expired results clear the whole selection instead of shifting ordinals. Réservation also rejects an incomplete list if a record disappears during planning. Native permissions, separate exact-target confirmation and actor history remain authoritative. Native assistant suites passed: Contracts 84 plus 10 subtests, Gestion Magasin 84 plus 6 subtests, Réservation 70 plus 6 subtests; one Réservation tenant-move case is inapplicable because the native app has no such tenant partition.

Source publication: the reviewed backend commits are published to company and personal repositories: Contracts `d2347ff8f402`, Gestion Magasin `f83393f6352e`, Réservation `9f977d592709`, Management Projet `215837e0f9b9`. Production publication of this backend batch is pending explicit approval after automatic approval review rejected its multi-application service restarts. No production push from this batch has occurred. Existing production model and disabled-feature settings remain unchanged.

PARTIALLY IMPLEMENTED: the next cumulative preparations retain exact predecessor training/validation bytes and add one application at a time. Contracts V6r4: 1,866 training / 319 validation / 516 held-out cases. Gestion Magasin V7r4: 2,064 / 362 / 606. Réservation V8r4: 2,244 / 402 / 690. Original questions, expected actions and split membership are preserved; updated envelopes use reviewed native schemas, current-message language, calendar context and explicitly synthetic ordered references. Neutral-history variants are not independent scenarios.

All 2,646 V8r4 training/validation examples and 690 held-out cases passed server-matching tokenizer, Colibri-template/parser, loss-boundary and semantic-weight alignment checks locally without loading weights. Maximum training length is 7,648 tokens; evaluation reserves 512 output tokens within 8,192. Exact source/dependency hashes and full predecessor manifests are pinned. Shared and training-integrity suites pass 48 tests plus 74 subtests. [Metadata evidence](../training/reports/shared-v8r4-en-fr-metadata-preflight.json).

IMPLEMENTED and verified locally: the completed-candidate comparison helper binds frozen datasets, per-set coverage, driver/provider evidence and captured Colibri process/artifact identity. It requires every set to pass, reports application/language breakdowns, and cannot activate a model. Shared/training verification passed 52 tests and 95 subtests; one reviewer found no remaining issues. V5r4 training, export and evaluation are complete; the measured acceptance failure is recorded above.

IMPLEMENTED and verified on the server: all 2,646 cumulative V8r4 training/validation rows passed the frozen tokenizer, Colibri parser, template-prefix, loss-boundary and semantic-weight checks without truncation. Maximum lengths are 7,648 training and 7,496 validation tokens within 8,192. V6r4 and V7r4 remain exact validated prefixes. Peak memory was 592,674,816 bytes; the metadata job used a 0.25-core CPU quota and a 2 GiB memory limit, reserving the remaining active-training allowance plus 10% system RAM. Production inference and the active training process were unchanged. This is a formatting check, not model accuracy. Each future stage still requires predecessor acceptance, a frozen baseline and capacity checks. [Server evidence](../training/reports/shared-v8r4-en-fr-server-preflight.json).

No future-stage optimization has started. Each stage still requires acceptance of its exact predecessor, a frozen baseline, server preflight and capacity checks. Model accuracy is not inferred from metadata or backend tests. Colibri PR work remains deferred until the user resumes it.


Current step: corrected starter-question release deployed and verified; Phase 1 implementation report remains available for user review. The user subsequently authorized the Management Projet integration and shared-model Design Workflow training; their separate progress documents describe that work. Broad model-quality acceptance is incomplete; do not interpret successful basic workflows as a 95% accuracy result.

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
Frozen independent80 cases: tool selection50/80 (62.5%); exact arguments24/76 (31.58%); schema73/80 (91.25%). Base: 44/80,18/76,61/80. Targets95/95/99 are UNMET. Complex filters, limits, operation choice and malformed calls remain weaknesses. The application's deterministic help/reference handlers are not credited as model accuracy.

Dedicated server8-request sample: sequential mean8.34s, p95(maximum of4)9.74s; concurrency2 mean12.29s, p95(maximum of4)17.66s. Decode56.94tokens/s excludes prefill; peak process RSS2.58GiB and about4busy CPU cores. This small sample is not a load-capacity certification.

## Production verification
- Prepared production checklist: 12/12 passed, including dashboard FAB, invoice/article search, financial equality, company/history isolation, bilingual workflows, navigation, mobile fit and public-login absence. The new module release passed nine additional production checks: permitted catalogue, English/French capability answers, stock/logistics/article reads, described article search and desktop/mobile menu fit.

## PARTIALLY IMPLEMENTED
- Overall model acceptance remains below target, despite passing the tested basic application workflows.

## Remaining limitations
- Complex model requests may omit filters or ask for clarification; inspect returned record details before selecting an action. Exact-target confirmation is mandatory for supported writes.
- Stock, logistics, account and payment adapters are read-only. Supported writes are bounded document/client actions, not all operations in every module.
- Full physical-device keyboard and assistive-technology certification remains unperformed.
- Phase 2 is explicitly authorized for Management Projet. Design Workflow shared-model training is also authorized; its application release is separate. The user subsequently authorized the remaining named applications; their integrations remain planned and must reuse the shared model.

Historical work log: [AI_PROGRESS_HISTORY.md](AI_PROGRESS_HISTORY.md). Detailed evidence: [AI_TESTING.md](AI_TESTING.md), [AI_FINE_TUNING.md](AI_FINE_TUNING.md), and training/reports.

## Shared UI revision — 2026-10-10

IMPLEMENTED locally: canonical Design Workflow-based MUI interface, identical Facturation and Management Projet copies, local SVG robot/icons, scoped palette, optional company row, bold author labels, meaningful immediate suggestions, accessible shortcuts, draft-safe command switching, bare-slash help and mobile input sizing. Existing business handlers and permissions remain authoritative. Management Projet production activation is still disabled.

Verified with local synthetic logins: 24 actual screenshots covering reference/Facturation/Management Projet × light/dark × empty/populated × shortcuts closed/open, eight side-by-side comparisons, mobile 390×844 and 390×420, six-line input, Escape/focus wrapping, draft preservation, company switching, AI detail-to-list navigation, native confirmation priority and cancellation. No API responses were replaced for these browser checks. Physical-device keyboard and assistive-technology certification remain unperformed.

Automated validation: Facturation 125 assistant frontend tests; Management Projet 55; Facturation 12 focused backend tests; Management Projet 3 focused backend tests (including English/French subcases); 190 existing Facturation form tests. TypeScript, assistant ESLint and both production frontend builds passed. Design Workflow’s requested bold labels passed its 26 assistant tests and production build. One reviewer completed the review with no remaining blocker after fixes.

IMPLEMENTED: reviewed source published to company, personal and production for the central repository, Facturation frontend/backend, Management Projet frontend/backend and Design Workflow frontend. All 18 remote heads matched. Three frontend production builds, deployed-source comparisons, container health and anonymous HTTPS login checks passed. No backend migration was needed. The eleven Facturation form return fixes are published. Management Projet’s effective production AI setting remains false; the shared inference process and training unit were not restarted.

PLANNED: remaining shared UI integrations. The six-app navigation follow-up is recorded below. Shared V5 server training continues; no V5 accuracy score is available yet. Colibri upstream PRs remain explicitly deferred.


## Six-app return navigation — 2026-10-10

IMPLEMENTED and verified locally: all remaining history-based return controls removed from facturation, management_projet, design_workflow, contracts, gestion_magasin and reservation. The Holding portal is excluded. Contracts has four corrected list/form destinations, Gestion Magasin 22 and Reservation ten. Six not-found pages keep their explicit Home/dashboard action instead of a history-dependent Return button.

Gestion Magasin returns preserve the applicable store for articles, stock, inventory, sales, expenses and attendance. List selection accepts the URL hint only when the store belongs to a visible active membership. Cross-store lists keep their existing destinations. Manual store changes synchronize an existing store hint without undoing the native pagination reset or discarding sorting and anchor parameters. The stock-detail destination still follows its stock/store-stock label.

Validation: 297 focused frontend tests passed across the six apps; the broader Magasin/pagination run passed 69 tests (overlapping coverage, not an additional unique count). Scoped ESLint, TypeScript and all six production builds passed. Regressions cover authorized deep links, invalid/unknown store hints, revoked membership, restricted store visibility, tab changes and pagination preservation. One reviewer completed the final review with no remaining findings. Local browser checks confirmed explicit 404-to-dashboard navigation in Facturation, Management Projet and Design Workflow. Source scans found no remaining history navigation calls. Sensitive-added-content checks passed.

Publication: IMPLEMENTED. All six reviewed frontend commits are published to company, personal and production; all 18 remote heads matched. Deployed source matches the reviewed files in each app, all six frontend containers are healthy and all six login routes return HTTP 200. Production browser verification confirmed Facturation’s 404 Home navigation; the other checked apps reached their expected sign-in pages without active browser sessions. Authenticated navigation for those apps was verified locally where available, not claimed as a complete production business-flow test. No backend, database, model, permission or training configuration changes were included. The training process retained its original process identity; the shared inference service remained healthy with its original start time.

## Serial training and Contracts preparation — 2026-10-10

PARTIALLY IMPLEMENTED: Contracts (`contrat`) native adapter and shared UI are under local validation. See [discovery](AI_CONTRACTS_DISCOVERY.md), [actual checks and remaining gates](AI_CONTRACTS_PROGRESS.md), and the [single-job training queue](AI_TRAINING_QUEUE.md). The current shared V5 run continues; no Contracts training or model accuracy is claimed.

The user's additional login-theme request is limited to Contracts and Réservation, with Facturation as the reference. Local desktop/mobile screenshots confirm matching dark canvas, transparent outlined fields, heading size and a theme toggle 16px from the top/right. Theme switching preserves typed input and persists across reload. IMPLEMENTED: the two theme fixes are published to company, personal and production; all six remote heads matched. Exact-source production builds and 26 existing auth/theme tests per app passed. Live Contracts desktop and Réservation mobile login checks confirmed the palette, outlined fields and top-right toggle; both containers are healthy. The training process retained its original PID.

## Contracts adapter preparation — 2026-10-10

PARTIALLY IMPLEMENTED: native permission/company tools, confirmed writes with actor history, EN/FR knowledge, history and canonical MUI UI are verified locally. Final checks: 576 backend tests plus 4 subtests; 60 final assistant/form frontend tests, TypeScript, ESLint and production build passed. Local dummy browser checks include scope isolation, read-only denial, actual PDF, confirmed deletion/audit, history and eight-state visual comparison. See [Contracts progress](AI_CONTRACTS_PROGRESS.md). The shared next-stage dataset passed tokenizer/Colibri preflight; Contracts model training/accuracy and activation are still incomplete. Shared V5 remains the only active training job.

Contracts source is now published disabled: backend `00503a910cda`, frontend `875524520cc0`, six remote heads verified; additive migration/knowledge sync and native health checks passed with existing business row counts unchanged. Gestion Magasin now has the locally tested adapter and prepared dataset documented below; Réservation local implementation and dataset preparation are recorded below.

## Gestion Magasin local preparation — 2026-10-10

PARTIALLY IMPLEMENTED: native store/role tools, controlled actor-attributed writes, history/RAG and canonical MUI UI are locally tested. Full backend run: 448 tests; final assistant subset: 56. Frontend: 40 focused tests; dummy browser scope, native PDF, confirmed deletion and read-only/history checks passed. Eight reference comparisons have no visual blocker. Synthetic EN/FR data is prepared, not trained; no model accuracy is claimed. See [details and remaining gates](AI_GESTION_MAGASIN_PROGRESS.md). Current shared V5 remains the only training job; its frozen inputs are unchanged.

Gestion Magasin source release: backend `a7acaefa4891`, frontend `ee6ffbaf750e`, all six remote heads verified. Additive migration and twelve knowledge documents applied with all sixty business-table counts unchanged; services healthy. Assistant remains disabled, shared production model and current training unchanged.

## Réservation local preparation — 2026-10-10

PARTIALLY IMPLEMENTED: native permissions (including independent Hilton access), seven bounded tools, actor-attributed confirmations, owner-scoped history/RAG and canonical MUI UI pass local checks. Final backend: 514 tests, including 43 assistant tests; frontend: 26 assistant tests, TypeScript, ESLint and production build pass. Native dummy-login browser checks cover search/navigation/list return, confirmed deletion/history, logout/read-only access and EN/FR responses. Eight side-by-side chat comparisons and two mobile sizes pass. See [details](AI_RESERVATION_PROGRESS.md).

Synthetic EN/FR data is prepared, not trained: 150/30/84 Réservation train/validation/held-out cases. The six-app shared-v8 preparation retains earlier curricula; current V5 frozen inputs remain unchanged. Model accuracy, server benchmarks and activation remain incomplete.

Réservation source is published disabled: backend `105cc4e24c90`, frontend `3c09a4d8a103`, six remote heads and 37 deployed backend file hashes verified. Assistant migration/knowledge sync succeeded; all 26 business-table counts are unchanged. Services and live login are healthy, anonymous assistant access returns 401, and the shared production model/current training process are unchanged.

The prepared cumulative six-app dataset passed exact server tokenizer/Colibri preflight: 2,014 rows, maximum 4,977 tokens, no truncation. This was metadata-only validation and started no new training job. That metadata check started no optimization; V5 has subsequently completed.


## Shared V5 status update — 2026-10-10

IMPLEMENTED: training, isolated export, 328 frozen evaluations, warm performance probe and artifact/process verification completed. Model acceptance remains PARTIALLY IMPLEMENTED: all eight evaluation sets miss at least one required gate. The native tokenizer check passed 328/328 prompt-ID comparisons; runtime diagnostics are now complete (see the later update). No further optimization job has started. Contracts, Gestion Magasin and Réservation source is published disabled with datasets prepared; serial model training and acceptance remain pending. Production model unchanged. See [measured scores and limitations](AI_MODEL_ACCURACY.md#shared-v5-measured-results--2026-10-10).

## Shared V5r2 preparation — 2026-10-10

IMPLEMENTED: failure diagnostics distinguish learned mistakes from export problems; all three native refinement generators pass schema validation with database access forbidden. Existing rows and frozen benchmarks are retained. The single reviewer found no native-label or permission/target issues. Fifteen training/acceptance regression tests pass.

PARTIALLY IMPLEMENTED: the 1,454/186 shared refinement dataset and 34 independent cases are prepared. The sequential server capacity comparison passed with checkpointing enabled (two finite updates across all 24 layers; peak RSS 5.39 GiB). Disabling it reached the isolated 18 GiB memory limit before completing a step. Keep checkpointing enabled; no model was saved or activated. Exact server preflight passed all 1,640 rows (maximum 5,135 tokens). All 34 new frozen baseline cases were measured before optimization; their failed acceptance is documented. Reviewer-requested validation deduplication preserved every training and held-out row. The revised exact server preflight passed all 1,640 rows again. The isolated V5r2 continuation has started (1,454 steps, 14 CPU threads, 24 text layers, rank 16, checkpointing enabled). Guarded export and all 362 frozen cases are queued automatically. Optimization completion and full acceptance remain pending. Production model unchanged.

V5r2 reviewed preparation source is published as `c7fbddfda2eba43503dbf0e803f61d881b03b313`; all three remote heads and all 35 deployed file hashes were verified. The production inference service remained healthy with unchanged start time.

## Serial runner preparation — 2026-10-10

IMPLEMENTED locally: separately versioned future-stage runner and strict cumulative application validation, with all 22 training integrity/acceptance/scope tests passing. The active V5r2 trainer, helper scripts, dataset and evaluator remain unchanged. No later-stage optimization has started. The single reviewer verified that obsolete mixtures, altered predecessor files and missing retained rows are rejected, with no remaining findings. The serial runner still requires its own server preflight and launch gates before use; model acceptance remains incomplete.

The serial runner source was published as `3ee7b7d9f242bf26e6f6be686c0303fd711967cc`; all three remote heads and six deployed file hashes matched. Its 22 tests also passed on the server without loading weights or optimizing. The revised V8r2 cumulative dataset then passed the server tokenizer/template/parser/loss-boundary preflight for all 2,168 rows, with matching metadata/script hashes and no truncation. V6r2/V7r2 remain exact validated prefixes. [Server preflight evidence](../training/reports/shared-v8r2-en-fr-server-preflight.json). The current V5r2 training continues; no later-stage optimization or production model replacement has started.

## Shared candidate and metadata follow-up — 2026-10-11

PARTIALLY IMPLEMENTED: V5r2 completed 1,454 server optimization steps and isolated Colibri export. Its 362-case frozen evaluation is complete and acceptance failed; no model activation or replacement is authorized by training completion. Follow-up local tool descriptions clarify supported filters, native status labels, budget rows versus totals, and editable form labels. Backend suites and one independent review passed; the source is not deployed and the separate description-only diagnostic is not measured. See [the serial queue](AI_TRAINING_QUEUE.md) for exact validation counts and remaining gates.

V5r2 measured totals: 344/362 correct tools (95.03%), 254/280 eligible exact arguments (90.71%), 358/362 valid structures (98.90%). The matched V5 baseline was 322/362, 226/280 and 352/362. Only one of 11 sets passes every gate; aggregate gains do not erase critical-case failures. The isolated eight-request warm probe measured 7.805 s sequential mean, 11.699 s at concurrency two, 54.73 decode tokens/s excluding prefill, 2.60 GiB peak RSS and zero errors. [Full measured results](AI_MODEL_ACCURACY.md#shared-v5r2-measured-results--2026-10-11).

## Shared model diagnostics and adapter corrections — 2026-10-11

The description-only V5r2 comparison completed all 362 cases on the same pinned candidate, provider and runtime. Tool selection increased from 344/362 to 346/362 (95.58%); exact arguments increased from 254/280 to 257/280 (91.79%); structured validity decreased from 358/362 to 356/362 (98.34%). Three of eleven sets passed all gates. Overall acceptance still FAILS; production was not changed. This is regression evidence, not an unseen certification. [Measured report](../training/reports/shared-metadata-v1-en-fr-comparison.json).

IMPLEMENTED and verified locally, not released: Management Projet now sends freshly authorized saved result IDs in display order to the planner. Expired, malformed or incomplete selections clear entirely, without shifting ordinals. Exact-target confirmation and native actor history remain unchanged. Shared calendar anchors derive from the application's trusted local date; they do not calculate business amounts or infer missing years. Facturation's search descriptions distinguish customer/product fields, native statuses, inclusive date bounds and requested result limits. Native registry checks confirmed unchanged validation and permission metadata.

Verification after these changes: Facturation 856 assistant tests passed; Management Projet 84 tests and 130 subtests passed; Design Workflow 88 tests passed. Five shared calendar tests cover leap years, year rollover, invalid dates, unchanged caller data and actual planner context. The single reviewer found no unresolved issues.

PARTIALLY IMPLEMENTED: a separate `shared-adapter-v2-en-fr` diagnostic contains the original 362 user prompts/labels bound to current native planner inputs plus 28 new English/French saved-result cases. Historical capability metadata recovery and synthetic ordinal fixtures are explicit in its manifests. All 390 cases passed exact server-matching tokenizer/template/parser/loss-boundary checks; maximum prompt 7,228 tokens plus 512 reserved output tokens fits 8,192. No local model inference or training ran. The server evaluation completed all 390 cases against the unchanged V5r2 candidate. On the matched 362 cases: 346/362 correct tools (95.58%), 255/280 exact arguments (91.07%), and 357/362 valid structures (98.62%). The separate 28 new follow-up cases scored 12/28 tools, 9/20 exact arguments, and 25/28 valid structures. Across all 390: 358/390 tools (91.79%), 264/300 exact arguments (88.00%), and 382/390 valid structures (97.95%). Only three of twelve sets passed all gates; acceptance FAILS. All temporary workers were stopped after artifact and process verification. [Measured comparison](../training/reports/shared-adapter-v2-en-fr-comparison.json). This run changes adapter instructions, tool descriptions and calendar context together and cannot isolate each contribution.

Training status: the 1,454-step V5r2 optimization is complete; the 390-case adapter evaluation is complete and failed acceptance. Failure diagnosis and adapter correction continue; no new sustained training job has started. Contracts, Gestion Magasin and Réservation training remain queued one at a time behind acceptance. The shared model and production feature activation remain unchanged.

### Saved-result target validation follow-up

IMPLEMENTED locally and reviewed: exact ordinal-target validation now exists across all six native adapters. See the V5r3 preparation section below for verified tests and publication status. This safeguard was motivated by an isolated diagnostic selecting the wrong in-set ID; no business operation was executed by that diagnostic. Model scores are unchanged by backend safeguards.

The eight malformed calls were replayed separately with the same pinned provider and candidate process: four invented an unsupported supplier filter for financial summaries, two used field names absent from Management Projet, one omitted the required operation, and one requested an unavailable previous-result deletion operation. Provider/schema validation rejected them; the diagnostic executed no business tool and did not replace benchmark results. [Failure analysis](../training/reports/shared-adapter-v2-malformed-calls.json).

## Reviewed V5r3 preparation — 2026-10-11

PARTIALLY IMPLEMENTED: `shared-v5r3-en-fr` preserves the reviewed current-metadata curriculum and adds 122 diverse English/French training examples plus 36 validation examples. Totals: 1,576 training and 222 validation rows. The existing 390 diagnostic cases remain unchanged; 48 newly authored cases are frozen separately, making 438 evaluation cases. They are authored by the implementation team, not a blind external certification. Failure categories informed training; exact normalized split overlap is rejected, while semantic-independence limitations remain explicit.

All 1,798 SFT/validation rows and the 48 new evaluation cases passed tokenizer/template/Colibri-parser/loss-boundary checks against server-matching metadata. Maximum training length is 7,648 tokens; maximum new evaluation prompt is 3,224 plus 512 output tokens. No local model weights were loaded. [Metadata preflight](../training/reports/shared-v5r3-en-fr-metadata-preflight.json). New-case baseline measurement is running on the unchanged isolated V5r2 candidate. No V5r3 optimization has started. A server capacity check at the revised longest example remains required.

The two-update precision comparison on the earlier 5,135-token example passed for both modes: BF16 averaged 104.06 seconds/update with 5.38 GiB peak RSS; FP32 averaged 113.55 seconds with 6.59 GiB. BF16 is retained based on those measured costs. This saved no adapter and measured no accuracy. [Precision report](../training/reports/cpu-training-precision-v1.json).

IMPLEMENTED and verified locally: the six native adapters use a shared safeguard for explicit EN/FR ordinal mutation targets. A recognized request for the third saved result cannot propose the first saved result, even if both are authorized or the first is the current page. Expired/malformed selections, conflicting explicit IDs and wrong resource types reject; quoted or recognized replacement values do not become targets. This is bounded syntax, not a general natural-language intent parser. Native authorization and separate exact-target confirmation still apply.

Validation: 14 shared context tests and 22 training-integrity tests pass. Final native assistant suites: Facturation 860, Management Projet 86 plus 130 subtests, Design Workflow 90, Contracts 58 plus 4 subtests, Gestion Magasin 58, Réservation 45. The single reviewer found no unresolved code or final-dataset issues. Native adapter publication and packaged-wheel synchronization remain pending; no backend/model deployment or feature activation is claimed. Contracts, Gestion Magasin and Réservation optimization remain queued, one at a time, behind shared-model acceptance.


## Conversation framing and V5r4 preparation — 2026-10-11

The 48 new frozen V5r3 baseline cases completed against the unchanged V5r2 candidate: 14/48 correct tools, 0/34 eligible exact arguments, 48/48 valid structures. Acceptance fails. [Measured baseline](../training/reports/shared-refinement-v2-en-fr-baseline.json). V5r3 remains an untrained, preserved dataset; its multi-turn failures prompted a separate input-format investigation before sustained optimization.

A nine-request server diagnostic compared original separate user turns, removal of history, and clearly labelled history inside the current user turn. Facturation article-reference search and Design Workflow person/project/status search became correct with either alternative; Management Projet's VAT edit still produced invalid arguments. This is a small diagnostic, not model acceptance or proof of a runtime defect. Original frozen results remain unchanged.

IMPLEMENTED and verified locally: the shared planner labels earlier user messages as background and preserves the current request separately for native clarification localization. It does not parse user-provided labels to recover trusted current text. System/assistant history is excluded; native authorization remains independent. Both French-to-English and English-to-French follow-ups pass in the four affected native providers. Shared/dataset tests: 23 passed, 41 subtests. Native assistant suites: Facturation 860, Management Projet 87 plus 136 subtests, Design Workflow 90, Contracts 59 plus 10 subtests, Gestion Magasin 59 plus 6 subtests, Réservation 46 plus 6 subtests. One reviewer found no remaining issues.

PARTIALLY IMPLEMENTED: `shared-dialogue-v1-en-fr` preserves all 438 logical evaluation cases and expected labels; only 78 contain reformatted history and require fresh baseline measurement. Reuse of the other 360 results requires identical input hashes and the same pinned provider/candidate. This diagnostic is running. Combined reused results are not performance measurements.

`shared-v5r4-en-fr` retains all 1,576/222 V5r3 training/validation examples in their original splits, reformats existing histories, and adds 137/53 bounded neutral greeting/thanks variants. Totals: 1,713 training and 275 validation rows. Variants are not independent examples; no held-out targets enter SFT. The generator, production framing helper and source manifests are hashed. All 1,988 training/validation rows and all 438 evaluation cases passed tokenizer/template/parser/loss-boundary checks, with 7,648 maximum training tokens and 7,235 maximum evaluation prompt tokens plus 512 reserved output. [Preflight](../training/reports/shared-v5r4-en-fr-metadata-preflight.json). No local model weights were loaded.

No V5r4 sustained optimization has started. Server preflight, capacity validation, packaged native wheel synchronization and publication remain pending. Production model and feature flags are unchanged. Contracts, Gestion Magasin and Réservation training remain sequential behind acceptance; Colibri PR work stays deferred.


## Shared V5r4 training started — 2026-10-11

IMPLEMENTED: the complete baseline comparison is measured. Across 438 unchanged logical scenarios, conversation framing changes tool selection from 372/438 (84.93%) to 386/438 (88.13%), eligible exact arguments from 264/334 (79.04%) to 277/334 (82.93%), and valid structure from 430/438 (98.17%) to 425/438 (97.03%). All acceptance gates still fail. The 78 changed histories were measured freshly; 360 identical inputs reuse prior measurements with the same pinned candidate/provider. No combined latency claim is made. [Full comparison](../training/reports/shared-dialogue-v1-en-fr-baseline.json).

IMPLEMENTED: exact server preflight passed 1,713 training and 275 validation rows. Two unsaved capacity updates on the longest 7,648-token example passed across all 24 layers; peak RSS 6.33 GiB, update times 182.43 and 172.04 seconds using ten threads while the four-thread diagnostic ran. The initial 18 GiB job allowance was rejected by the resource gate before any job started; the revised 15 GiB limit preserved the 10% reserve plus additional headroom. [Preflight](../training/reports/shared-v5r4-en-fr-server-preflight.json), [capacity](../training/reports/shared-v5r4-en-fr-capacity.json).

PARTIALLY IMPLEMENTED: the reviewed single server continuation has started from the existing V5r2 merged checkpoint. One complete epoch covers 1,713 examples (557 Facturation, 760 Management Projet, 396 Design Workflow), rank 16/alpha 32 across 24 text layers, BF16 CPU SDPA, semantic loss weight 4 and learning rate 0.00005. Limits: 14 of 16 CPU threads, 15 GiB memory, no job swap. The shared source release `f619d6714bbd` is verified on all three remotes. Existing production inference remains healthy and unchanged.

The launcher binds the exact baseline, capacity, data, scripts, base and runtime artifacts; guarded export waits for successful complete coverage. A monitor will evaluate all 438 frozen scenarios afresh after successful isolated export. Completion, accuracy and activation are not claimed. Contracts, Gestion Magasin and Réservation remain sequential future stages.

IMPLEMENTED locally: the identical shared core 0.2.1 wheel is packaged for all six backends with source-content hashes verified. Tests against that actual wheel passed: Facturation 860; Management Projet 87 plus 136 subtests; Design Workflow 90; Contracts 59 plus 10 subtests; Gestion Magasin 59 plus 6 subtests; Réservation 46 plus 6 subtests. Native source publication remains pending; this source-only central push did not deploy application code or activate a model.


## Argument-rule diagnostic prepared — 2026-10-11

PARTIALLY IMPLEMENTED: a separate four-arm comparison preserves the same twelve synthetic cases and their targets, tools and permissions. Four are observed name/date failures; eight new controls cover names across languages, missing years, leap and non-leap centuries, and native status conversion. The arms use the original instructions, a literal-name rule, a complete-month/year rule, or both. This changes no application code or active frozen evaluation and performs no training.

Preparation checks passed: four integrity tests plus eight subtests; all 48 input/target combinations passed the server-matching tokenizer, Colibri parser, template and loss-boundary checks. Maximum prompt length is 2,527 tokens with 512 reserved output tokens. One reviewer found no issues. [Metadata evidence](../training/reports/planner-rules-v1-en-fr-preflight.json).

No diagnostic inference has run. It must follow the original candidate evaluation and performance measurement. Known failures are regression cases, and these controls are not independent certification. Any useful rule still requires broader regression evaluation before application changes or activation.


## Follow-up input diagnostic prepared — 2026-10-11

PARTIALLY IMPLEMENTED: the newest 48 cases expose repeated unsupported replies despite offered supported tools. A separately versioned 12-case EN/FR diagnostic includes three actionable bilingual scenarios, a business-background control, an unsupported-operation pair and a missing-year pair. Four arms preserve the original envelope, omit history diagnostically, change exact neutral greeting wording to the existing training phrasing, or put the current request first. The greeting arm is a wording intervention and preserves language; genuine task history remains byte-identical. The business-background control does not prove history dependence because trusted context already contains the selected records. Current-only is not a proposed production memory policy.

Five invariant tests plus 11 subtests pass. All 48 envelopes pass tokenizer, Colibri parser/template, loss-boundary and semantic alignment checks without local weights or inference. Maximum prompt 2,962 tokens plus 512 output within 8,192. [Metadata evidence](../training/reports/planner-history-v1-en-fr-preflight.json). Server measurement is queued behind the original argument-rule diagnostic and malformed-call replay. This small selected diagnostic cannot replace acceptance; no held-out targets enter training.

IMPLEMENTED locally and reviewed: shared core 0.2.2 and all six native adapters bind recognized explicit resource/ID pairs before accepting an unrelated current or saved record. Quoted values and recognized replacement clauses, including bilingual field-colon/equality forms, do not supply targets. Longest overlapping resource phrases preserve French invoice labels; separate conflicting targets reject. The ordinal guard still rejects incorrect, expired or out-of-range references. This bounded syntax is not a general intent parser or authorization mechanism; native permissions and exact-target confirmation remain mandatory. No model schema-narrowing experiment or backend deployment is claimed.

Package verification: identical 0.2.2 wheel in all six backends; SHA-256 cb7683557d82a0a91c39bdc8e50a01d2708b2808c3aa54208a8234ae22b8eaa8. Shared/training suite: 68 tests plus 154 subtests. Native suites against the actual wheel: Facturation 863; Management Projet 90 plus 140 subtests; Design Workflow 93; Contracts 87 plus 14 subtests; Gestion Magasin 87 plus 10 subtests; Réservation 73 plus 10 subtests, with one inapplicable tenant-move case skipped. Single reviewer found no remaining issues.


## Argument-rule diagnostic and malformed calls — 2026-10-11

IMPLEMENTED: all 96 isolated rule-diagnostic requests completed. For V5r4, original/names/dates/both exact arguments were respectively 4/10, 5/10, 4/10 and 5/10. Neither explicit full-month regression was fixed by any arm. Name copying improved one selected search but could worsen time-report tool choice; century-date controls still produced incorrect dates/years. No runtime prompt change is justified by these limited results. V5r2 results and all unchanged acceptance evidence remain recorded separately. [Diagnostic results](../training/reports/planner-rules-v1-en-fr-results.json).

IMPLEMENTED: four schema-rejected V5r4 calls were replayed without business execution. One used an unsupported stock-movement status, one invented a stock-write field, and two quote-number requests emitted no parsed tool call. The latter cause remains unresolved; empty provider deltas do not prove a model/runtime root cause. Original errors and scores are preserved. [Malformed-call report](../training/reports/shared-v5r4-en-fr-malformed-calls.json).

## Greeting-bias correction and V5r5 preparation — 2026-10-11

IMPLEMENTED: the 96-request history diagnostic is complete. V5r4 eligible exact arguments increased from 2/8 with the original envelope to 6/8 with current-only or longer neutral greetings, but both alternatives produced two invalid outputs. Current-first remained 2/8. No production history/prompt change is justified. The untouched full acceptance result remains 390/438 tool selections (89.04%), 284/334 exact arguments (85.03%) and 434/438 valid outputs (99.09%). [Diagnostic evidence](../training/reports/planner-history-v1-en-fr-results.json).

IMPLEMENTED locally: the curriculum audit identified all 118 original short Hello/Bonjour histories as clarification labels. V5r5 reconstructs trusted role boundaries from the pinned V5r3 sources and V5r4 augmentation manifest, then assigns neutral history using input-only hashes that exclude labels. Current questions, targets, schemas, trusted context, genuine history and split membership remain unchanged. Training now includes 282 actionable plus 56 clarification examples after Hello, and 281 actionable plus 62 clarification examples after Bonjour. Ninety training-only date variants add all months, ordinary leap/non-leap years and century controls, using verified training templates. These are correlated variants, not independent examples. Totals: 1,803 training and 275 validation; all 438 original held-out scenarios stay excluded and unchanged.

PARTIALLY IMPLEMENTED: optional periodic validation selects the checkpoint with the lowest application-macro semantic validation loss, retaining the base if none improves. Final checkpoint loss remains separately reported. This is checkpoint selection, not acceptance. Server preflight, trainer smoke test, new optimization, export and acceptance evaluation are pending. No new model has been activated.

IMPLEMENTED: the six native target-binding fixes were fetched/pulled and published normally to company and personal source remotes, with exact heads verified. Production backend deployment remains pending approval. The generated Facturation source snapshot corresponds to central commit c012a92; later training preparation is not included in that snapshot yet.

V5r5 preparation verification: 78 shared/training tests plus 164 subtests pass. All 1,803 training and 275 validation rows pass schema validation, exact Colibri parser round-trip, template parity, loss masking and semantic weighting alignment. All 438 retained evaluation cases pass the same checks. Maximum training length is 7,662 tokens; maximum evaluation prompt is 7,235 plus 512 reserved output, within 8,192. Tokenizer metadata matches the existing server candidate; no local weights or optimization were used. [Metadata report](../training/reports/shared-v5r5-en-fr-metadata-preflight.json).

## Shared V5r5 training running — 2026-10-11

PARTIALLY IMPLEMENTED: the reviewed isolated continuation started from the existing V5r2 base using source commit `3b976f8dd7d0`. One complete epoch covers 1,803 examples; 275 validation examples are checked initially, every 300 steps and at completion. The lowest application-macro validation loss selects the candidate, with the baseline retained if none improves. Learning rate 0.00002; 24 text layers; rank 16/alpha 32; semantic weight 4; 14 CPU threads; 12 GiB limit; no swap. Existing production inference remains healthy and unchanged.

IMPLEMENTED: server preflight passed 1,803/275 rows; the longest 7,662-token two-step capacity check passed at 6.43 GiB peak RSS. The real two-step trainer smoke test selected the intermediate checkpoint at step 1 after evaluating steps 0/1/2. It proves mechanics, not accuracy. [Capacity](../training/reports/shared-v5r5-en-fr-capacity.json), [smoke](../training/reports/shared-v5r5-en-fr-trainer-smoke.json).

PARTIALLY IMPLEMENTED: guarded selected-checkpoint export and all 438 unchanged acceptance cases are monitored automatically after successful training. A step-zero selection stops export. No production model activation or next-app training follows automatically from training completion.

IMPLEMENTED locally: corrected future datasets preserve exact predecessor byte prefixes and all existing new-app held-out envelopes. Contracts: 1,956/319/516 training/validation/test cases; Gestion Magasin: 2,154/362/606; Réservation: 2,334/402/690. All 2,736 training/validation rows plus 690 held-out rows pass local tokenizer/Colibri metadata preflight. No local weights were loaded. Server preflight and all future training remain pending.

Verification of the later-stage preparation: 85 shared/training tests and 168 subtests pass. The sole reviewer found no remaining issues. The complete curated-source dry-run passed secret/private-path exclusions; generated model weights and private evaluation logs remain excluded. No future optimizer has run.
