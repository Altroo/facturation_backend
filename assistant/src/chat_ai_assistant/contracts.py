from dataclasses import dataclass, field
from typing import Any, Callable
import json
from jsonschema import Draft202012Validator


class ChatAIError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ChatAITool:
    name: str
    description: str
    input_schema: dict
    output_schema: dict
    handler: Callable
    application: str = "facturation"
    required_capabilities: tuple[str, ...] = ("read",)
    authorization: str = "fresh company membership and scoped records"
    classification: str = "read"
    timeout_seconds: int = 5
    audit_classification: str = "business_read"

    def schema(self):
        return {"type": "function", "function": {"name": self.name,
                "description": self.description, "parameters": self.input_schema}}


class ChatAIToolRegistry:
    def __init__(self, tools):
        self.tools = {}
        for tool in tools:
            if tool.name in self.tools or tool.classification not in ("read", "proposal"):
                raise ValueError("Duplicate or non-read tool")
            Draft202012Validator.check_schema(tool.input_schema)
            Draft202012Validator.check_schema(tool.output_schema)
            self.tools[tool.name] = tool

    def permitted(self, capabilities):
        return [t for t in self.tools.values() if set(t.required_capabilities) <= set(capabilities)]

    def get(self, name):
        if name not in self.tools:
            raise ChatAIError("PERMISSION_DENIED")
        return self.tools[name]

    def validate(self, name, arguments):
        tool = self.get(name)
        if not isinstance(arguments, dict) or len(json.dumps(arguments)) > 6000:
            raise ChatAIError("INVALID_ARGUMENTS")
        if list(Draft202012Validator(tool.input_schema).iter_errors(arguments)):
            raise ChatAIError("INVALID_ARGUMENTS")
        return tool


def object_schema(properties, required=()):
    return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}

STRING = {"type": "string", "maxLength": 120}
ID = {"type": "integer", "minimum": 1, "maximum": 2147483647}
