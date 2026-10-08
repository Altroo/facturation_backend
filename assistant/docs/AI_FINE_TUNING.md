# Model training and evaluation

The active Facturation assistant supports **English and French only**. It follows the current message automatically, including language changes within a conversation. There is no language selector. Runtime prompts, clarification schemas, API capabilities, the current training dataset and the independent evaluation set all use this scope.

## Selected model and serving runtime

The deployed model is the server-tuned **Qwen3.5-0.8B**, served by **Colibri** with CPU int8 weights. Its immutable model ID is `chat-ai-facturation-qwen08-v4-en-fr-20261008`. The upstream model license is Apache-2.0. Pinned source and runtime fingerprints are recorded in [the model manifest](../training/reports/qwen08-v4-en-fr-manifest.json).

Serving settings: four CPU threads, 8192 context tokens, 512 maximum output tokens, temperature zero, thinking disabled and one decoder slot. The selected Colibri engine does not support grammar-constrained response formats. Native tool calls are strictly validated after generation; grammar enforcement is not claimed. Backend authorization remains independent of model behavior.

## Current datasets

`training/datasets/facturation-v4-en-fr/` contains **410 training and 86 validation examples** covering all 17 registered tools plus clarification, four permission-filtered capability profiles and actual multi-turn histories. Examples use synthetic entities and values, verified tool definitions and supported application behavior. No live customer records or private conversations are training inputs.

Scenario families are separated between training and validation. Sensitive-data checks, schema validation and token-budget checks are part of dataset construction. The manifest records the language scope, versions and hashes.

`training/datasets/facturation-acceptance-en-fr/` is the independently authored, frozen **80-case** evaluation set: 40 semantic scenarios in English and French. Test rows are never supplied to the trainer. Paired translations are not 80 independent business scenarios. Four knowledge-query paraphrases are excluded from exact argument scoring regardless of the predicted tool.

## Executed server training

Training ran on the approved Linux server, not on the developer computer. `train_cpu.py` requires Linux and `CHAT_AI_TRAINING_SERVER=1`, rejects manifests outside the English/French scope and checks that at least 10% system memory remains available at each step.

V4 completed **410 optimization steps**, using CPU bfloat16, 14 threads, batch size one and assistant-only cross-entropy loss. LoRA uses rank 8, alpha 16 and the last four language layers, with **593,920 trainable parameters**. Checkpoints are written every 24 steps. The reproducible configuration and pinned dependency versions are recorded in [the server training report](../training/reports/server-training-0.8b-v4-en-fr.json) and `training/configs/server-requirements.lock`.

Validation loss changed from **0.117782 to 0.068355**. Recorded wall time was **4339.35 seconds** and peak training RSS **11.16 GiB**. Wall time includes contention and a diagnostic pause; it is not an uncontended training-throughput benchmark.

The adapter was exported, safely merged and converted to Colibri int8 on the server. Artifact hashes were verified. Training and export do not automatically change the serving model.

## Independent base versus tuned evaluation

Both models were scored against the same frozen English/French cases, offered tool schemas and scoring rules. Business operations are not executed by this planner evaluator.

| Metric | Base 0.8B | Server-tuned V4 | Target |
|---|---:|---:|---:|
| Correct tool | 44/80 (55%) | 50/80 (62.5%) | 95% |
| Exact arguments | 18/76 (23.68%) | 24/76 (31.58%) | 95% |
| Valid structured output | 61/80 (76.25%) | 73/80 (91.25%) | 99% |

| V4 language | Correct tool | Exact arguments | Valid structure |
|---|---:|---:|---:|
| English | 25/40 | 14/38 | 36/40 |
| French | 25/40 | 10/38 | 37/40 |

**All three broad model acceptance targets remain unmet.** Training executed successfully, but this does not establish reliable unrestricted application interaction. Failures include wrong operations, dropped filters or result limits, changed values, extra arguments and malformed output. The unchanged predictions and failure categories are documented in [the independent comparison](../training/reports/qwen08-v4-independent-en-fr/COMPARISON.md).

Approved workflow help, slash usage, permission-derived module access answers and exact positional references use trusted application handlers. Their application-test passes are not counted as raw-model benchmark successes. UI and security evidence remains separate from this model evaluation.

## Measured CPU inference performance

A separate server probe completed eight synthetic requests without errors: four sequentially and four at concurrency two.

| Measurement | Result |
|---|---:|
| Sequential mean / sample P95 | 8.34 s / 9.74 s |
| Concurrency two mean / sample P95 | 12.29 s / 17.66 s |
| Weighted decode throughput | 56.94 tokens/s |
| Average busy CPU cores | 4.00 |
| Peak summed process RSS | 2.58 GiB |

Decode throughput excludes prompt prefill. Tool calls are buffered, so the first visible event is not the first generated token. With four requests per group, sample P95 is the observed maximum. This is a small probe, not sustained-load certification. See [the performance report](../training/reports/server-performance-v4-en-fr-4threads.json).

## Reproduction, evaluation and rollback

1. Build a new version from approved metadata using `build_dataset_v4.py` or its versioned successor. Validate labels, language scope, secrets, split families and context budgets.
2. Freeze a separately authored evaluation set before training. Never copy held-out failures into training or change expected answers to improve scores.
3. On the approved Linux server, install the locked dependencies and run `train_cpu.py` with the pinned base model, dataset directory, output directory, 410 steps, 14 threads and maximum sequence length 8192. Script, dependency, model, tokenizer, configuration and dataset hashes are captured before optimization.
4. Export with `export_adapter.py`, convert with `scripts/convert_colibri.py` and verify artifact hashes. Keep adapters, weights, checkpoints, environment configuration and raw private evidence outside public Git.
5. Run `evaluate_v2.py` against the same frozen English/French set for base and tuned models. Despite its legacy filename, the evaluator uses the supplied dataset manifest and capability-filtered schemas. Record the model/runtime manifest, settings, errors and per-language scores.
6. Test actual tool authorization, confirmation history, company isolation and UI workflows separately with controlled fixtures. Measure latency, CPU, memory and concurrency after training completes.
7. Promote only with explicit authorization and an accurate statement of remaining quality gaps. Rollback restores the previous immutable model directory and ID; a training job never activates its own output.

Older superseded experiments are retained as historical evidence, outside this current-scope guide. Their results are not current acceptance scores. The next model-quality work requires new diverse compositional training examples and an independent evaluation; no unrun experiment is claimed successful.
