# Chat AI Assistant

Self-hosted AI assistant for business applications, with a reusable Python engine, local CPU inference, application tools, conversation history, knowledge retrieval, and a reproducible model fine-tuning pipeline.

The current integration is Facturation. It connects natural-language requests to existing billing workflows while preserving authenticated user access, company scope, native business calculations, and audit history. The interface supports French and English.

## What It Shows

- AI integration around an existing business application and its permission system.
- Local model serving with Colibri and CPU-compatible quantized inference.
- Typed tool calling with backend validation, bounded results, and scoped access.
- Application knowledge retrieval, conversation context, and verified navigation.
- Server-side LoRA training with synthetic datasets and measured baseline comparisons.
- Automated backend, frontend, and security checks for the application integration.

## Main Components

- `src/chat_ai_assistant`: model provider, orchestrator, tool contracts, and response validation.
- `knowledge`: reviewed application workflows and terminology.
- `training`: synthetic datasets, training configurations, export scripts, evaluations, and curated results.
- `runtime/colibri`: pinned inference runtime source and upstream license notices.
- `deploy`: configurable deployment templates.
- `docs`: architecture, API, tools, security, testing, and operating documentation.

## Key Capabilities

- Invoice, quote, customer, product, and other supported record searches using natural descriptions.
- Financial summaries calculated through the existing application services.
- Permission-aware result cards, document actions, and navigation to existing application pages.
- Documented workflow explanations and visible form labels in French and English.
- User/company-scoped conversations, history, follow-up references, streaming, and cancellation.
- Supported edit/delete previews with explicit confirmation and attribution to the requesting user.
- Floating chat interface integrated into Facturation's authenticated layout using its existing UI components.

## Stack

- Python 3.12+, JSON Schema
- Colibri, quantized Qwen3.5 CPU inference
- PyTorch, Transformers, PEFT/LoRA for model training
- Django, Django REST Framework, PostgreSQL for the Facturation adapter
- Next.js, React, TypeScript, MUI for the Facturation interface
- pytest, Jest, Testing Library, and MCP Playwright for integration verification

## Related Repositories

- Backend API and Facturation adapter: [Altroo/facturation_backend](https://github.com/Altroo/facturation_backend)
- Frontend and chat interface: [Altroo/facturation_frontend](https://github.com/Altroo/facturation_frontend)

## Local Setup

Install the reusable Python package in a local environment:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

On Windows, activate with `.venv\Scripts\activate`.

The complete assistant uses the existing Facturation backend and frontend. Follow their setup instructions and the [deployment guide](docs/AI_DEPLOYMENT.md) for application integration and private model configuration. Keep environment files and credentials outside source control.

## Tests and Evaluation

Backend and frontend integration tests live in the related application repositories. The [testing guide](docs/AI_TESTING.md) describes the verified commands, security scenarios, browser checks, and known limitations.

The model training pipeline runs on Linux and uses synthetic application scenarios. See the [fine-tuning guide](docs/AI_FINE_TUNING.md) for dataset validation, training, export, evaluation, and rollback.

The current fine-tuned model improves on the base model but remains below the broad tool-selection and argument-extraction targets. Actual scores and performance measurements are in the [model comparison](training/reports/qwen08-v4-independent-en-fr/COMPARISON.md). Passing application tests does not imply that every model request is interpreted correctly.

## Documentation

- [Architecture](docs/AI_ARCHITECTURE.md)
- [Application discovery](docs/AI_APPLICATION_DISCOVERY.md)
- [API contract](docs/AI_API.md)
- [Tools and supported actions](docs/AI_TOOLS.md)
- [Security and permissions](docs/AI_SECURITY.md)
- [Application knowledge](docs/AI_KNOWLEDGE.md)
- [Frontend integration](docs/AI_FRONTEND.md)
- [Implementation status](docs/AI_PROGRESS.md)

## Portfolio Note

The repository is public for portfolio review. It contains source code, synthetic datasets, and reviewed technical results. Production credentials, connection details, financial records, model weights, private conversations, and browser authentication artifacts are excluded.

Colibri's upstream license and third-party notices are preserved. Model license information and pinned revisions are documented in the fine-tuning guide.
