"""Google Gemini adapter for the LLM provider port.

Translates REMI-neutral Message/ToolDefinition types into
Google's Generative AI wire format internally.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import TYPE_CHECKING, Any

from remi.infrastructure.llm.ports import LLMProvider, LLMResponse, ToolCallRequest

if TYPE_CHECKING:
    from remi.domain.modules.base import Message
    from remi.domain.tools.ports import ToolDefinition


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("GOOGLE_API_KEY", "")

    # -- wire-format translation (REMI → Gemini) -----------------------------

    @staticmethod
    def _as_str(content: Any) -> str:
        return content if isinstance(content, str) else json.dumps(content, default=str)

    @classmethod
    def _messages_to_gemini(
        cls,
        messages: list[Message],
    ) -> tuple[str | None, list[dict[str, Any]]]:
        """Gemini uses ``system_instruction`` for system messages and a
        ``contents`` list of ``{"role": "user"|"model", "parts": [...]}``."""
        system_parts: list[str] = []
        contents: list[dict[str, Any]] = []

        for msg in messages:
            if msg.role == "system":
                system_parts.append(cls._as_str(msg.content))
                continue

            role = "model" if msg.role == "assistant" else "user"

            if msg.role == "tool":
                contents.append({
                    "role": "user",
                    "parts": [{
                        "function_response": {
                            "name": msg.name or "unknown",
                            "response": {
                                "result": cls._as_str(msg.content),
                            },
                        }
                    }],
                })
                continue

            contents.append({
                "role": role,
                "parts": [{"text": cls._as_str(msg.content)}],
            })

        system_instruction = (
            "\n\n".join(system_parts) if system_parts else None
        )
        return system_instruction, contents

    @staticmethod
    def _tools_to_gemini(tools: list[ToolDefinition]) -> list[dict[str, Any]]:
        declarations = []
        for defn in tools:
            decl: dict[str, Any] = {
                "name": defn.name,
                "description": defn.description,
            }
            schema = defn.to_json_schema()
            if schema.get("properties"):
                decl["parameters"] = schema
            declarations.append(decl)
        return [{"function_declarations": declarations}]

    # -- LLMProvider interface ------------------------------------------------

    async def complete(
        self,
        *,
        model: str,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int = 1024,
        tools: list[ToolDefinition] | None = None,
    ) -> LLMResponse:
        try:
            import google.generativeai as genai
        except ImportError as exc:
            raise RuntimeError(
                "Gemini provider requires the 'google-generativeai' package: "
                "pip install google-generativeai"
            ) from exc

        genai.configure(api_key=self._api_key)

        system_instruction, contents = self._messages_to_gemini(messages)

        gen_config = genai.GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )

        model_kwargs: dict[str, Any] = {"model_name": model, "generation_config": gen_config}
        if system_instruction:
            model_kwargs["system_instruction"] = system_instruction
        if tools:
            model_kwargs["tools"] = self._tools_to_gemini(tools)

        gen_model = genai.GenerativeModel(**model_kwargs)
        resp = await gen_model.generate_content_async(contents)

        content_text: str | None = None
        tool_calls: list[ToolCallRequest] = []

        for candidate in resp.candidates:
            for part in candidate.content.parts:
                if hasattr(part, "text") and part.text:
                    content_text = part.text
                if hasattr(part, "function_call") and part.function_call:
                    fc = part.function_call
                    tool_calls.append(
                        ToolCallRequest(
                            id=uuid.uuid4().hex,
                            name=fc.name,
                            arguments=dict(fc.args) if fc.args else {},
                        )
                    )

        usage: dict[str, int] = {}
        if hasattr(resp, "usage_metadata") and resp.usage_metadata:
            um = resp.usage_metadata
            usage = {
                "prompt_tokens": getattr(um, "prompt_token_count", 0),
                "completion_tokens": getattr(um, "candidates_token_count", 0),
                "total_tokens": getattr(um, "total_token_count", 0),
            }

        return LLMResponse(
            content=content_text,
            model=model,
            usage=usage,
            tool_calls=tool_calls,
        )
