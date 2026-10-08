# V4 English/French model evaluation

**Status: training executed; broad model acceptance targets UNMET.** Basic application workflows and trusted backend handlers require their separate UI/security evidence. This report does not claim full Phase 1 or production readiness.

The unchanged frozen set contains 80 cases (40 semantic scenarios in English and French). It evaluates the raw planner without executing business operations.

| Metric | Base | V4 | Target |
|---|---:|---:|---:|
| Correct tool |44/80 (55%)|50/80 (62.5%)|95%|
| Exact arguments |18/76 (23.68%)|24/76 (31.58%)|95%|
| Valid structured output |61/80 (76.25%)|73/80 (91.25%)|99%|

Knowledge-query paraphrases are excluded from exact argument scoring. No cases, expected answers, frozen offered schemas, or scoring rules were changed after evaluation.

V4 language results: English 25/40 tools, 14/38 exact arguments, 36/40 schema; French 25/40 tools, 10/38 exact arguments, 37/40 schema.

Failure categories (tags may overlap; no rescoring):

- Alternative search field choices: 3.
- Changed requested values: 7.
- Incorrect clarification reason or language: 2.
- Explicit argument or filter omissions: 12.
- No valid structured action: 7.
- Requested result limit or offset missed: 2.
- Unrequested extra arguments: 4.
- Wrong operation: 23.

Examples include omitting a requested three-result limit, dropping customer/product filters from a payment search, omitting an inactive-user filter, and using a generic query where the frozen expectation specified a product field. An alternative field is not presumed equivalent. Full synthetic case details are in `failure-analysis.json`.

Training completed 410 finite optimization steps with 593,920 trainable LoRA parameters. Validation loss changed from 0.117782 to 0.068355. The 72.3-minute recorded duration includes contention and a diagnostic pause; it is not an uncontended throughput measurement.

Separate CPU probe: four synthetic validation prompts, repeated sequentially and with two concurrent requests; 8/8 requests completed without errors.

| Measurement | Result |
|---|---:|
| Sequential mean / sample P95 |8.34s / 9.74s|
| Concurrency 2 mean / sample P95 |12.29s / 17.66s|
| Weighted decode rate |56.94 tokens/s|
| Average busy CPU cores |4.00|
| Peak summed process RSS |2.58 GiB|

Decode rate excludes prefill. Tool-call output is buffered, so first visible event is not the first generated token. With only four requests per group, sample P95 is the observed maximum; this is a small performance probe, not a capacity guarantee. The concurrent pass may benefit from warm caches.

Serving configuration: Colibri CPU int8, 4 threads, 8192 context tokens, 512 maximum output tokens, thinking off, temperature 0, one decoder slot. Runtime fingerprints match the base comparison.

Model ID: `chat-ai-facturation-qwen08-v4-en-fr-20261008`. Full immutable inference-manifest SHA-256: `c6fafe827bd25b7c8fa495ed358f7a215082d9c88001672ef36d07c3432c9ba3`. Public manifest retains artifact hashes while omitting infrastructure identifiers.
