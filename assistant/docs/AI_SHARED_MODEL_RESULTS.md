# Shared English/French model: executed results

One existing Qwen3.5-0.8B checkpoint is retained for all approved integrations, with Colibri CPU inference. No per-application foundation model was downloaded. The balanced v2 candidate was trained and exported on the approved Linux server; it has not replaced production weights.

## Training

614 synthetic training examples and 112 validation examples retain Facturation (410/86), Management Projet (82/10) and add authorized Design Workflow specialization (122/16). Independent held-out sets remain outside optimization and validation. All examples fit the measured 8K token budget without truncation: maximum 4,744 training and 4,977 validation tokens. The dataset generators prohibit business database queries and validate schemas, secrets and exact normalized split duplication; exhaustive semantic near-duplicate exclusion is not claimed.

Training executed 366 optimization steps, with 122 exposures per application. Distinct examples used: Facturation 122, Management Projet 82, Design Workflow 122. Last-eight-layer LoRA uses rank 8/alpha 16, learning rate 0.0001, seed 17, 10 CPU threads and 1,187,840 trainable parameters. Validation loss changed from 0.092866 to 0.075527; peak RSS was 16.82 GiB. Recorded wall time of 3,970.35 seconds includes the requested pause. Loss improvement is not model acceptance. Resource guards leave at least 10% host memory free; training was server-only.

## Frozen baseline versus candidate

Both sides use the same held-out cases for each application, native tool calling, temperature zero, 8K context, maximum 512 output tokens and thinking disabled. No business operations are executed by this evaluator.

| Application | Correct tool: existing v4 → shared v2 | Exact arguments: existing v4 → shared v2 | Valid structure: existing v4 → shared v2 |
|---|---|---|---|
| management_projet | 44/60 (73.33%) → 44/60 (73.33%) | 25/50 (50.0%) → 27/50 (54.0%) | 60/60 → 60/60 |
| design_workflow | 38/60 (63.33%) → 41/60 (68.33%) | 19/48 (39.58%) → 23/48 (47.92%) | 57/60 → 60/60 |
| facturation | 50/80 (62.5%) → 55/80 (68.75%) | 24/66 (36.36%) → 29/66 (43.94%) | 73/80 → 76/80 |

**The 95% tool, 95% exact-argument and 99% structure targets remain unmet.** The candidate improves several measurements but is not accepted for production replacement. Failures include wrong resource/metric, lost filters or dates, missing current-context identifiers, inappropriate clarification and malformed output. Sanitized per-language/category counts, dataset/evaluator hashes and six unchanged synthetic failure examples per application are in [the comparison](../training/reports/shared-v2-en-fr-comparison.json).

Exact arguments exclude knowledge and clarification and normalize declared optional defaults. Knowledge wording is accepted only when nonempty/schema-valid; retrieval factuality is tested separately. Clarification reason and language are checked strictly. Historical Facturation evaluation excluded knowledge only (76 eligible cases); the frozen current protocol has 66 eligible cases. The changed denominator is explicitly reported, not counted as a training improvement. Design Workflow context-ID equivalence remains a documented strict-scoring limitation.

## Actual CPU probe

Eight synthetic requests completed without errors. Four sequential requests averaged 8.108 seconds (sample P95 8.555 seconds); concurrency two averaged 11.857 seconds (sample P95 16.112 seconds). The process averaged 3.996 busy CPU cores on the measured 16-logical-CPU host and peaked at 2.63 GiB RSS. Decode rate was 56.59 tokens/second, excluding prompt prefill. Native tool calls buffer their first visible event, so it is not token TTFT. One KV slot serializes decoding. This small warm-cache probe is not capacity certification or an application concurrency guarantee. Runtime profile attribution matched all eight requests; pre/post artifact hashes and the same process were verified. See [sanitized performance evidence](../training/reports/shared-v2-en-fr-performance.json).

## Application fixes and release boundary

Management Projet greetings now persist a localized welcome without invoking the model or business tools. Narrow full-sentence received/spent amount requests use existing authorized financial calculations. Unmatched and qualified queries keep the model's registered catalog. Application-specific clarification wording follows the current English/French message and trusted native interface fallback; it does not claim unsupported Facturation metrics or grant permissions. These trusted handler tests are not credited as raw-model benchmark successes.

Real local browser failures are retained as findings: “hello” originally selected an expense; a monthly spending question originally selected a record list. Native regression tests and MCP Playwright verified both fixes. Named return controls use verified lists. Production data is never used for training or destructive tests. Source publication and additive assistant migrations are separately approved; feature/model activation and real-account acceptance remain unperformed.
