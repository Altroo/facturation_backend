# Approved application knowledge

The current source is twelve reviewed JSON documents in `facturation_backend/chat_ai/knowledge`, covering invoice procedures/statuses, clients, financial meanings, confirmations, actual form labels, articles, stock quantities, logistics and staff-user lookup. Sources are application metadata/workflows, not production customer records or raw repository dumps.

`python manage.py sync_ai_knowledge` validates approval, application ID, allowed capability names, sensitive patterns and size. It hashes each source file, updates changed documents transactionally, removes obsolete global documents, and refuses to erase the corpus when the source directory is empty. Tenant documents are preserved by global-source removal. Run `purge_ai_history` separately for expired conversations; audits are retained.

Each database record carries application, stable document ID, content version, category, sensitivity, required capabilities and optional tenant scope. Retrieval first filters these restrictions in SQL, then ranks only authorized titles/content using English/French keywords, Unicode accent folding, conservative plural normalization and authorized-corpus term weighting. It returns at most three excerpts, each bounded to 3,500 characters, from at most 200 authorized records.

## Why this index

The isolated PostgreSQL installation offers pgvector **0.8.1**, currently not installed in this database. It was evaluated before adding a separate vector store. With twelve documents, lexical retrieval avoids another model, service, vector extension migration and embedding memory footprint. PostgreSQL remains the source and index; no external vector database is introduced.

This is a small-corpus engineering choice, not a measured claim that lexical search outperforms embeddings. English/French paraphrase recall needs held-out workflow testing. If the corpus grows or measured recall is insufficient, add a commercially usable multilingual local embedder and pgvector inside PostgreSQL, applying the same SQL permission predicate before ranking. That extension is not implemented or claimed complete.

## Revocation and output

Saved explanations bind to the exact original source IDs and versions. Changing source content, capabilities, tenant or deletion invalidates old generated prose. Authorization is checked before the generation prompt, for each response chunk, before persistence, and before JSON/SSE delivery. The private source event never reaches the browser. Refreshed cards are also checked against their own current sources.

Retrieved text remains quoted untrusted data. The model cannot execute tools from a knowledge answer. Generated prose maps known technical identifiers to verified form labels; unknown underscore identifiers are rejected before delivery, including split tokens and Markdown wrappers. Empty retrieval returns a clear bounded response rather than an empty bubble. Reply language follows the current message; form-label language comes automatically from the current interface, with no language selector added to chat.

## Verification

The local synchronization reported `Updated 5; removed 0; approved 12`. Source revocation, permission filtering, history replay and split-token label handling are covered in the backend regression/integration suites. Development recall passed20/20questions in the top-three and15accent/plural variants at top-one. These are development retrieval regressions, not independent model answer accuracy. Generated explanation factuality remains separate acceptance work; passing permission tests is not a model-quality score.

Retrieval also supports a native stock-only superuser context: only documents marked `stock_read` are eligible, while membership-protected invoice/financial documents remain excluded. Tested with real document filters; titles/snippets are not handed to the model before permission filtering.
