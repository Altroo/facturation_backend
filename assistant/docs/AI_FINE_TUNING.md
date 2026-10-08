# Model training and evaluation

Training is restricted to the approved Linux server. `train_cpu.py` refuses non-Linux execution or an absent `CHAT_AI_TRAINING_SERVER=1` guard. No local fine-tuning has run. Local Colibri inference is used for development/evaluation only.


## Current language scope — English/French only

User correction on2026-10-08 supersedes the original four-language specification. Active runtime prompts, clarification schemas, capability responses and fallback messages now support **English and French only**, automatically following each current message. No manual language selector.

`build_dataset_v3.py` creates the language-scope baseline: **76 training,18 validation,52 held-out rows**. Server-only training completed192steps in1,312.50seconds; validation loss0.145492→0.093479. Same-server, same-frozen52-case results: base31/52tools,15/50arguments,36/52valid; tuned42/52tools,27/50arguments,51/52valid. These remain below95/95/99targets. Measurements overlapped other server work, so they are not dedicated performance acceptance.

The current development dataset is `facturation-v4-en-fr`: **410training/86validation examples**, all17registered tools plus clarification, capability-filtered schemas and multi-turn cases. Split families are separated and labels validated; no private business data. V4 server training is IN PROGRESS, not deployed. An independently authored, frozen80-case English/French evaluation set covers40 paired scenarios and four capability profiles; no test rows are provided to training. Its base0.8B result is44/80tools,18/76exact arguments,61/80valid structure. Four knowledge-query paraphrases are excluded from argument scoring. Base inference stopped after evaluation to avoid training contention. Versioned evidence is curated under `training/reports/`.

The earlier results below are historical four-language runs. Do not use their aggregate scores as the new two-language acceptance result.

## Candidates and runtime

Qwen3.5-0.8B and Qwen3.5-2B are Apache-2.0 open-weight candidates; pinned revisions and source file manifests are in `training/evaluations/model-manifest.json`. Converted models use the checked-out Colibri Qwen CPU engine, eight-bit conversion and dense int8 runtime loading. The conversion helper losslessly materializes tied output embeddings required by this runtime. It does not change application authorization.

Pilot local load measurements: 0.8B about 1.92 GiB RSS; 2B about 3.58 GiB; tuned v1 about 1.94 GiB and 2.9 seconds load. These are local M4 CPU measurements, not production-server figures. No model is accepted for deployment yet.

## Completed pilot v1

Server-only LoRA optimized 593,920 parameters in the last four language layers, rank 8/alpha 16, CPU bfloat16, 14 threads. It ran 96 steps in 611.8 seconds, peak RSS 6.60 GiB. Validation loss changed from 0.20077 to 0.12091. This demonstrates executed training, not improved held-out behavior.

The adapter and merged/converted export exist. All 26 transferred weight shards matched the server SHA-256 manifest. Twenty-two unchanged base shards were reused only after hash equality; the four changed layers were transferred. See `tuned-transfer-verification.json`.

Historical v1 baseline (48 synthetic cases):

| Model | Tool accuracy | Exact arguments | Schema validity | Mean latency | P95 |
|---|---:|---:|---:|---:|---:|
| 0.8B base | 54.17% | 25% | 83.33% | 10.424 s | 13.511 s |
| 2B base | 79.17% | 52.08% | 100% | 22.591 s | 23.871 s |

Both missed the 95/95/99 targets. The old contract predates stricter clarifications and expanded tools; these numbers cannot be compared directly with a new-contract tuned run.

## Historical v2 work

`build_dataset_v2.py` creates 152 train, 36 validation and 104 held-out cases in English, French, Arabic and Darija. All translations of a scenario stay in one split. Cases use synthetic names/values; no private business rows or conversations. Structured labels are validated against the frozen actual tool schema. A failed router-coverage preflight is retained separately; the current manifest has zero omitted expected tools.

This is a small synthetic pilot. Structural overlap among supported operations is intentional; it is not proof of population-level accuracy or linguistic diversity. Additional independent user phrasing and adversarial evaluation is still required. Held-out examples are never passed to the trainer.

V2 server run: `/var/www/chat-ai-assistant-training/adapters/facturation-qwen08-v2`, 192 requested steps, same LoRA method, max sequence 8192, CPU quota 1440% on 16 logical CPUs, MemoryHigh 26 GiB/MemoryMax 30 GiB/no swap. The job checks at least 10% system memory availability each step. **Training executed successfully**: 192 steps in 1,586.21 seconds; peak RSS 12.45 GiB; validation loss 0.17204 → 0.13786. Export/Colibri conversion completed on the server. This is training success only; held-out acceptance completed below target (see the results below).

`evaluate_v2.py` records exact dataset/schema/provider/evaluator hashes, per-case calls/errors/usage and per-language/category scores. Future runs require an immutable model/runtime manifest and timeout in their identity. The current run started before that addition; a separate inference attestation records its uninterrupted server process and artifact hashes. Original run/output files are preserved. Tool schemas are frozen per run; business tools are never executed by this evaluator. Knowledge query paraphrases are unscored for argument accuracy and need human review. Native tool calls are buffered: first visible event is not the first generated token, and reported tokens/second are output tokens divided by total request time.

## Reproduction and acceptance

1. Export the actual permitted schema into a new dataset version; validate synthetic source inputs and labels.
2. Freeze prompts, splits, router and schema before running models. Do not copy failed held-out examples into training.
3. Run the base baseline, then server-only training with `train_cpu.py`. The locked server dependencies are in `training/configs/server-requirements.lock`.
4. Export with `export_adapter.py` on the server; convert using `scripts/convert_colibri.py` and verify hashes.
5. Evaluate base and tuned candidates on the same frozen cases/settings. Test actual tools/permissions separately with controlled fixtures.
6. Measure server latency, memory, CPU and concurrency separately after training completes. Retain failures and do not relabel a miss as a pass.
7. Promote only after tool/argument/schema/security targets and practical UI latency are accepted. Production activation requires explicit approval. Rollback selects the previous immutable model directory and model ID; no training job changes the serving model.

## Independent evaluation review
The 104 held-out rows are 26 scenarios translated into four languages, not 104 independent business scenarios. Training contains no actual multi-turn histories, and this pilot does not cover `get_record` or all permission-filtered schema variants. Application permission tests remain separate.

A scoring defect counted wrong knowledge selections in the argument denominator while excluding correct ones. Fixed scoring excludes all four knowledge-argument rows regardless of prediction. The original base predictions are preserved; `qwen08-base-v2/summary-scoring-v2.1.json` records **54/104 tool (51.92%), 27/100 exact arguments (27.00%), 68/104 schema (65.38%)**. Tool and schema scores did not change. No test labels or model predictions were altered.

Completed v2 training predates full provenance capture. `server-training-0.8b-v2-provenance.json` explicitly records its retrospective configuration/dependency evidence and missing pre-run base weight hashes. Future `train_cpu.py` writes script/model/tokenizer/config/dataset/dependency hashes and complete hyperparameters before optimization.

Qwen's selected Colibri engine currently rejects grammar-constrained response formats (`openai_server.py`, family capability check). A validation-only JSON-schema probe confirmed the request is unsupported. Native calls remain strictly validated after generation; no grammar enforcement is claimed.

## Completed v2 held-out result

| Same frozen104 cases | Tool selection | Exact arguments (100 scored) | Structured validity |
|---|---:|---:|---:|
| Base0.8B | 54/104 (51.92%) | 27/100 (27.00%) | 68/104 (65.38%) |
| Server-tuned0.8B | 81/104 (77.88%) | 47/100 (47.00%) | 101/104 (97.12%) |

Tuning improved this planning pilot but **does not meet95/95/99 targets**. Darija exact arguments:5/25 (20%); English14/25 (56%), French15/25 (60%), Arabic13/25 (52%). Missing requested filters and wrong operations remain; the adapter is not accepted for production.

Server tuned inference mean10.948s, P9525.826s, four CPU threads. Runtime decode-only rate54.05tokens/s from the exact104 Colibri profile turns; prompt prefill is excluded from that rate. End-to-end throughput is much lower because tool schemas/prompt prefill dominate. Baseline ran on localM4, so baseline/tuned latency must not be presented as a hardware-controlled speed comparison. Isolated image build overlapped a few server cases; the dedicated performance probe is recorded separately.

Next quality work: expand independently written compositional/multi-turn training scenarios and permission-filtered schema variants, evaluate on a newly held-out scenario set, then compare a small stronger candidate if the0.8B capability ceiling remains. Do not copy these held-out failures into training or deploy based on training loss.
