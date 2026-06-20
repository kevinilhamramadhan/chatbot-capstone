"""Request-scoped context shared with LangChain tools.

Tools receive only their declared arguments, but they also need to know which
customer is talking and a place to queue side-effects (e.g. "send this product
image"). We pass that through context variables set for the duration of one
incoming message.
"""

from contextvars import ContextVar
from dataclasses import dataclass, field


@dataclass
class OutboundMedia:
    image_url: str
    caption: str | None = None


@dataclass
class TurnContext:
    wa_number: str
    media: list[OutboundMedia] = field(default_factory=list)
    # A tool may request a hard state transition handled by the orchestrator.
    next_state: str | None = None


_current: ContextVar[TurnContext | None] = ContextVar("turn_context", default=None)


def set_turn_context(ctx: TurnContext) -> None:
    _current.set(ctx)


def get_turn_context() -> TurnContext:
    ctx = _current.get()
    if ctx is None:
        raise RuntimeError("No TurnContext set for this turn")
    return ctx
