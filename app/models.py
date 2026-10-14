"""Model adapters. The orchestrator talks to the `ModelClient` interface, not to a vendor SDK."""

from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol


@dataclass
class ToolCall:
    name: str
    args: Any


@dataclass
class ModelTurn:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: Any = None   # vendor object kept so it can be replayed (e.g. Gemini thought signatures)


class ModelClient(Protocol):
    def generate(self, system: str, history: list[dict], tools: list[dict]) -> ModelTurn: ...


class ScriptedModelClient:
    """Deterministic stand-in for the LLM, used for the offline demo and the automated tests.
    Each script step is a ModelTurn, or a callable(history) -> ModelTurn."""

    def __init__(self, script: list):
        self._script = list(script)

    def generate(self, system, history, tools) -> ModelTurn:
        if not self._script:
            return ModelTurn(text="(script exhausted)")
        step = self._script.pop(0)
        return step(history) if callable(step) else step


class GeminiModelClient:
    """Gemini function calling. Automatic function calling is DISABLED so that our executor,
    not the SDK, decides whether a requested call is allowed to run."""

    def __init__(self, model: str, api_key: str):
        from google import genai
        self._genai, self._model = genai, model
        self._client = genai.Client(api_key=api_key)

    def generate(self, system: str, history: list[dict], tools: list[dict]) -> ModelTurn:
        from google.genai import types

        declarations = [
            types.FunctionDeclaration(name=t["name"], description=t["description"],
                                      parameters_json_schema=t["input_schema"])
            for t in tools
        ]
        config = types.GenerateContentConfig(
            system_instruction=system,
            tools=[types.Tool(function_declarations=declarations)],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        response = self._client.models.generate_content(
            model=self._model, contents=self._to_contents(history, types), config=config
        )
        calls = [ToolCall(fc.name, dict(fc.args or {})) for fc in (response.function_calls or [])]
        text = "" if calls else (response.text or "")
        return ModelTurn(text=text, tool_calls=calls, raw=response.candidates[0].content)

    @staticmethod
    def _to_contents(history: list[dict], types) -> list:
        contents = []
        for m in history:
            if m["role"] == "user":
                contents.append(types.Content(role="user", parts=[types.Part.from_text(text=m["text"])]))
            elif m["role"] == "model":
                contents.append(m["raw"] if m.get("raw") is not None
                                else types.Content(role="model", parts=[types.Part.from_text(text=m["text"])]))
            elif m["role"] == "tool":
                parts = [types.Part.from_function_response(name=r["name"], response=r["response"])
                         for r in m["results"]]
                contents.append(types.Content(role="user", parts=parts))
        return contents
