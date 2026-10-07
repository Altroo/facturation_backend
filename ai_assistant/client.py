"""Signed calls to the existing self-hosted AI gateway; no external provider."""

import hashlib
import hmac
import json
import socket
import time
from uuid import uuid4
from urllib import error, request

from django.conf import settings
from rest_framework.exceptions import Throttled
from .exceptions import (
    AssistantDisabled,
    InvalidModelResponse,
    ModelTimeout,
    ModelUnavailable,
)


class AiAssistantClient:
    def _post(self, endpoint, payload):
        if (
            not getattr(settings, "AI_ASSISTANT_ENABLED", False)
            or not settings.AI_ASSISTANT_SERVICE_SECRET
        ):
            raise AssistantDisabled()
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        timestamp = str(int(time.time()))
        request_id = uuid4().hex
        service = settings.AI_ASSISTANT_SERVICE_NAME
        canonical = (
            f"{timestamp}\n{service}\n{request_id}\n{hashlib.sha256(body).hexdigest()}"
        )
        signature = hmac.new(
            settings.AI_ASSISTANT_SERVICE_SECRET.encode(),
            canonical.encode(),
            hashlib.sha256,
        ).hexdigest()
        http_request = request.Request(
            f"{settings.AI_ASSISTANT_GATEWAY_URL.rstrip('/')}/v1/{endpoint}",
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-AI-Service": service,
                "X-AI-Timestamp": timestamp,
                "X-AI-Request-ID": request_id,
                "X-AI-Signature": signature,
            },
            method="POST",
        )
        try:
            with request.urlopen(
                http_request, timeout=settings.AI_ASSISTANT_TIMEOUT_SECONDS
            ) as response:
                payload = json.loads(response.read(1024 * 1024).decode("utf-8"))
        except (TimeoutError, socket.timeout) as exc:
            raise ModelTimeout() from exc
        except error.HTTPError as exc:
            if exc.code == 429:
                raise Throttled(
                    wait=60, detail="L’assistant est occupé. Réessayez dans une minute."
                ) from exc
            if exc.code in (408, 504):
                raise ModelTimeout() from exc
            raise ModelUnavailable() from exc
        except (error.URLError, ConnectionError, OSError) as exc:
            raise ModelUnavailable() from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InvalidModelResponse() from exc
        if not isinstance(payload, dict):
            raise InvalidModelResponse()
        return payload

    def assist(
        self,
        *,
        action,
        text,
        source_language="auto",
        target_language=None,
        context="other",
        protected_terms=(),
    ):
        payload = {
            "action": action,
            "text": text,
            "source_language": source_language,
            "context": context,
            "protected_terms": list(protected_terms),
        }
        if target_language:
            payload["target_language"] = target_language
        result = self._post("assist", payload)
        if (
            not isinstance(result.get("suggested_text"), str)
            or not result["suggested_text"].strip()
        ):
            raise InvalidModelResponse()
        return {**result, "original_text": text}

    def translate_many(
        self, texts, *, target_language, protected_terms=(), context="document"
    ):
        unique = list(
            dict.fromkeys(
                text for text in texts if isinstance(text, str) and text.strip()
            )
        )
        result = {}
        batch = []
        size = 0

        def translate_batch(values):
            payload = {
                "texts": values,
                "target_language": target_language,
                "context": context,
                "protected_terms": list(protected_terms)[:100],
            }
            try:
                response = self._post("translate", payload)
            except Throttled as exc:
                time.sleep(float(exc.wait or 60) + 0.1)
                response = self._post("translate", payload)
            translated = response.get("translations")
            if (
                not isinstance(translated, list)
                or len(translated) != len(values)
                or any(not isinstance(v, str) or not v.strip() for v in translated)
            ):
                raise InvalidModelResponse()
            result.update(zip(values, translated))

        for text in unique:
            if len(text) > 5000:
                # Split at whitespace without dropping or duplicating content.
                parts = []
                remaining = text
                while len(remaining) > 4500:
                    split_at = remaining.rfind(" ", 0, 4500)
                    if split_at < 1:
                        split_at = 4500
                    parts.append(remaining[:split_at])
                    remaining = remaining[split_at:]
                parts.append(remaining)
                translated_parts = self.translate_many(
                    parts,
                    target_language=target_language,
                    protected_terms=protected_terms,
                    context=context,
                )
                result[text] = "".join(
                    (
                        part
                        if not part.strip()
                        else part[: len(part) - len(part.lstrip())]
                        + translated_parts.get(part, part).strip()
                        + part[len(part.rstrip()) :]
                    )
                    for part in parts
                )
                continue
            if batch and (len(batch) >= 15 or size + len(text) > 6000):
                translate_batch(batch)
                batch, size = [], 0
            batch.append(text)
            size += len(text)
        if batch:
            translate_batch(batch)
        return result
