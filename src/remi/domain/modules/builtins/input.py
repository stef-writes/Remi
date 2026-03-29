"""UserInput module — injects external parameters into a graph run as a conversation thread."""

from __future__ import annotations

from typing import Any

from remi.domain.modules.base import BaseModule, Message, ModuleOutput
from remi.runtime.context.runtime_context import RuntimeContext


class UserInputModule(BaseModule):
    """Emits run-time parameters as the first message in a conversation thread.

    The caller supplies ``params`` via ``RuntimeContext.extras["run_params"]``
    or via the module's own config (static defaults).  Run-time params win.

    If ``run_params["thread"]`` is a list, it is treated as a pre-built
    conversation thread (list of message dicts) and passed through directly.
    This supports multi-turn chat where the full conversation history is
    provided by the caller.
    """

    kind = "user_input"

    async def run(self, inputs: dict[str, Any], context: RuntimeContext) -> ModuleOutput:
        static_defaults = dict(self.config)
        run_params: dict[str, Any] = context.extras.get("run_params", {})

        merged = {**static_defaults, **run_params}

        pre_built_thread = merged.get("thread")
        if isinstance(pre_built_thread, list):
            return ModuleOutput(
                value=pre_built_thread,
                contract="conversation",
                metadata={"source": "pre_built_thread"},
            )

        thread = [Message(role="user", content=merged).model_dump()]

        return ModuleOutput(
            value=thread,
            contract="conversation",
            metadata={"source": "run_params" if run_params else "config"},
        )
