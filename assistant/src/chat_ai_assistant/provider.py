"""Private OpenAI-compatible transport; no hosted API or automatic fallback."""
from dataclasses import dataclass
import ipaddress
import json
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from .contracts import ChatAIError
from .clarifications import CLARIFICATION_SCHEMA, clarification_message


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ChatAIError("APPLICATION_UNAVAILABLE")


@dataclass(frozen=True)
class ModelConfig:
    base_url: str
    model: str
    api_key: str = ""
    timeout: int = 90
    max_tokens: int = 512
    mode: str = "json_schema"
    thinking: bool = False


class ChatAIModelService:
    def __init__(self, config: ModelConfig):
        self.config = config
        parsed = urllib.parse.urlparse(config.base_url)
        if parsed.scheme not in ("http", "https") or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ChatAIError("APPLICATION_UNAVAILABLE")
        if not parsed.hostname:
            raise ChatAIError("APPLICATION_UNAVAILABLE")
        # Operator configuration only. Reject public addresses, metadata endpoints and redirects.
        try:
            addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 80, type=socket.SOCK_STREAM)
            if not addresses or any(not (ipaddress.ip_address(x[4][0]).is_private or ipaddress.ip_address(x[4][0]).is_loopback) or ipaddress.ip_address(x[4][0]).is_link_local for x in addresses):
                raise ChatAIError("APPLICATION_UNAVAILABLE")
        except OSError as exc:
            raise ChatAIError("APPLICATION_UNAVAILABLE") from exc

    def stream(self, messages, *, schema=None, tools=None, cancel=None):
        cfg = self.config
        payload = {"model": cfg.model, "messages": messages, "stream": True,
                   "stream_options": {"include_usage": True}, "temperature": 0,
                   "max_tokens": cfg.max_tokens,
                   "enable_thinking": cfg.thinking, "chat_template_kwargs": {"enable_thinking": cfg.thinking}}
        if schema is not None:
            payload["response_format"] = {"type": "json_schema", "json_schema": {"name": "action", "strict": True, "schema": schema}}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        encoded = json.dumps(payload).encode()
        if len(encoded) > 48000:
            raise ChatAIError("CONTEXT_LIMIT")
        headers = {"Content-Type": "application/json"}
        if cfg.api_key:
            headers["Authorization"] = "Bearer " + cfg.api_key
        request = urllib.request.Request(cfg.base_url.rstrip('/') + '/chat/completions', data=encoded, headers=headers)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        started = time.monotonic()
        size = 0
        finished = False
        try:
            with opener.open(request, timeout=min(cfg.timeout, 30)) as response:
                for line in response:
                    if cancel and cancel.is_set():
                        raise ChatAIError("CANCELLED")
                    if time.monotonic() - started > cfg.timeout:
                        raise ChatAIError("MODEL_TIMEOUT")
                    size += len(line)
                    if size > 500000:
                        raise ChatAIError("INVALID_MODEL_OUTPUT")
                    if not line.startswith(b'data: '):
                        continue
                    raw = line[6:].strip()
                    if raw == b'[DONE]':
                        if not finished:
                            raise ChatAIError("INCOMPLETE_RESPONSE")
                        return
                    event = json.loads(raw)
                    if 'error' in event:
                        raise ChatAIError("APPLICATION_UNAVAILABLE")
                    if event.get('usage'):
                        yield {"usage": event['usage']}
                    for choice in event.get('choices', []):
                        reason = choice.get('finish_reason')
                        if reason:
                            if reason not in ('stop', 'tool_calls'):
                                raise ChatAIError("INCOMPLETE_RESPONSE")
                            finished = True
                        yield choice.get('delta', {})
                if not finished:
                    raise ChatAIError("INCOMPLETE_RESPONSE")
        except ChatAIError:
            raise
        except (TimeoutError, socket.timeout) as exc:
            raise ChatAIError("MODEL_TIMEOUT") from exc
        except (OSError, ValueError, urllib.error.URLError) as exc:
            raise ChatAIError("APPLICATION_UNAVAILABLE") from exc

    def choose(self, messages, tools, cancel=None):
        branches = [{"type": "object", "properties": {"tool": {"const": t.name}, "arguments": t.input_schema},
                     "required": ["tool", "arguments"], "additionalProperties": False} for t in tools]
        branches.append({"type": "object", "properties": {"tool": {"const": "clarify"},
                         "arguments": CLARIFICATION_SCHEMA},
                         "required": ["tool", "arguments"], "additionalProperties": False})
        schema = {"oneOf": branches}
        content, calls = '', {}
        usage = {}
        for delta in self.stream(messages, schema=schema if self.config.mode == 'json_schema' else None,
                                 tools=([t.schema() for t in tools] + [{"type":"function","function":{"name":"clarify","description":"Ask for missing details, clarify an ambiguous metric, or explain unsupported requests. Choose the current user message language; the backend writes the response.","parameters":CLARIFICATION_SCHEMA}}]) if self.config.mode == 'native' else None, cancel=cancel):
            content += delta.get('content') or ''
            usage.update(delta.get('usage', {}))
            for call in delta.get('tool_calls', []):
                part = calls.setdefault(call['index'], {'name': '', 'arguments': ''})
                part['name'] += call.get('function', {}).get('name', '')
                part['arguments'] += call.get('function', {}).get('arguments', '')
        try:
            from jsonschema import validate
            if self.config.mode == 'native':
                # Planner text is never a business answer. Exactly one registered,
                # schema-valid function is required even for a clarification.
                if len(calls) != 1:
                    raise ValueError('Invalid call count')
                call = next(iter(calls.values()))
                action = {'tool': call['name'], 'arguments': json.loads(call['arguments'])}
            else:
                action = json.loads(content)
            validate(action, schema)
            if action['tool'] == 'clarify':
                return {'tool': 'clarify', 'message': clarification_message(**action['arguments'])}, usage
            return action, usage
        except Exception as exc:
            raise ChatAIError("INVALID_MODEL_OUTPUT") from exc
