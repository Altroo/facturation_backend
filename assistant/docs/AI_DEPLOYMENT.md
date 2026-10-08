# Facturation deployment and verification

The user has explicitly authorized completion, testing, pushes to all three remotes, deployment and production verification. Release remains gated on resolving critical test failures; Phase 2 is not authorized. Existing development, translation and grammar model services have not been changed. The assistant would be the fifth installed model and fourth normal active model according to the user's inventory; isolated training/evaluation processes are not a production rollout.

## Build artifacts

- Reusable package: run `scripts/package_core.py --backend /path/to/facturation_backend` in a packaging environment with setuptools installed. It builds the wheel in backend `vendor/` and records source/wheel hashes.
- Backend `requirements.txt` references that wheel; its Dockerfile copies `vendor/` before dependency installation. Django `chat_ai` is integrated behind a disabled-by-default feature flag.
- `deploy/Dockerfile.colibri` builds only the pinned Qwen CPU engine from `runtime/colibri`; use the reviewed runtime revision. It intentionally excludes model weights from the image.
- `deploy/compose.assistant.yml` prepares a non-root, read-only inference container with bounded queue/context/output/resources, restart policy and health check. No host port is published.
- `deploy/facturation.override.yml` joins only the existing backend `web` service to the dedicated internal network, keeping its current backend/gateway networks. Do not apply this override to other applications.

The Colibri Linux image build and isolated startup were executed successfully: dedicated UID 10001, read-only root/model mount, network none, no published ports. Private hostname + key returned 200; no key returned 401; invalid hostname returned 403. See `training/evaluations/docker-validation.json`. The validation container was removed. Model acceptance and full application deployment acceptance remain incomplete.

## Authorized release sequence

1. Confirm accepted model/dataset/runtime hashes, backups and rollback artifacts; inspect free server resources again.
2. Build/package reviewed backend and frontend revisions. Set the frontend `NEXT_PUBLIC_CHAT_AI_ASSISTANT_ENABLED` flag at build time. Keep backend flag false until checks pass.
3. Mount the accepted converted model read-only. The converter sets artifact files to 0644/directories 0755 so the dedicated container UID can read them. Generate a dedicated random assistant inference key through normal secret management; use the same value for Colibri and Django. Set the same immutable `CHAT_AI_MODEL_ID` in both so tool audit events identify the actual model release. Never put it in source control, browser configuration or logs.
4. Start the private model network/container and verify `/health` plus one authenticated structured call from the backend network. Reject unauthenticated inference.
5. Apply only the five `chat_ai` migrations after reviewing a database backup. Run `sync_ai_knowledge` with approved sources.
6. Enable only Facturation's backend/frontend flags. Verify real login, company switching, invoice search/navigation, denied reads, one approved controlled action and actor history, cancellation, streaming and model unavailability.
7. The existing Celery Beat schedule invokes `chat_ai.purge_history` daily at03:20 in the application timezone. It calls `purge_ai_history`, including when inference is disabled; confirmed write audit events are retained independently.

Use `deploy/example.env` for variable names only. Its placeholder key is not a deployable secret. Private inference URL is `http://chat-ai-model:18090/v1`; the model endpoint must not be routed through public Nginx. Existing reverse proxy must pass streaming responses without buffering; verify the actual deployed location before changing it.

## Operating limits and monitoring

Default proposal: 4 CPU threads/4 CPUs, 6 GiB memory ceiling, one application inference lease, two runtime queue slots, 8192 context, 512 output tokens, 120-second backend timeout, 30-day conversation retention. These are adjustable deployment defaults; final server benchmarks must determine accepted values. The user's 90% allowance applies to isolated training, not a claim that normal business applications can be starved by inference.

Watch model health, latency/P95, queue/BUSY rates, invalid tool calls, timeouts, process RSS/CPU, denied operations and audit durations. Colibri metrics require authentication. Do not log prompts, raw business results or inference keys.

## Rollback

Disable both feature flags, stop only the new assistant inference service, restore the previous reviewed backend/frontend images and accepted model directory. The current feature remains isolated from the other five applications. Preserve conversation and audit tables unless a separately reviewed migration rollback is required; never discard actor history as part of a UI rollback. Existing dev/translation/grammar services remain untouched.

Build safety: `.env` and `.env.*` are excluded from the backend build context. Static collection uses synthetic build-only configuration, never production secrets. The model Dockerfile uses architecture-appropriate CPU flags, explicitly allows only the private service hostname, and has a restricted Docker build context excluding training datasets and model weights.

## Service-scoped release hooks
Reviewed hooks in `deploy/hooks/` build images before service replacement, fail on errors, and verify health. The backend hook migrates and synchronizes approved knowledge before replacing web/workers. The frontend hook replaces only its web service and gracefully reloads the existing proxy to refresh upstream DNS. Neither runs `compose down` or recreates shared Nginx. Both hooks were backed up and installed on2026-10-08; their SHA256 values match the reviewed files. The database backup (7,218,880bytes) passed pg_restore listing, and previous application images have explicit rollback tags. No application containers have been replaced yet.


## Public repository boundary

Application source and the non-secret docker-compose.assistant.yml override are maintained locally and reach the server through Git pushes. Secrets remain in ignored runtime environment files and the restricted release directory. Model weights, adapters, raw browser/API evidence and DB backups are not Git inputs. The model-release environment file is0600 and never appears in source or tool output. No shared application source is edited directly on the server.

V4 broad model targets are unmet; the authorized release is being verified against the bounded basic workflows described in AI_PROGRESS.md. Production verification must not be presented as certification of broad model accuracy.
