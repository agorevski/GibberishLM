"""Response-timing model for Gibberish.

Emulates the latency profile of an expensive, high-end frontier model:

  * a noticeable, variable *time-to-first-token* (the model "spinning up"),
  * a variable *thinking* phase whose duration is sampled per request,
  * steady-but-jittery token streaming at a realistic tokens/second rate,
  * variable tool-execution latency.

Every request samples its own :class:`RequestTiming` profile, so two identical
prompts take noticeably different — but always plausible — amounts of time.

All timings are configurable via environment variables (see the constants
below). Set ``GIBBERISH_SPEED`` to globally scale every delay (e.g. ``0.2`` for
fast demos, ``2.0`` for an extra-sluggish "thinking really hard" feel).
"""

from __future__ import annotations

import os
import random


def _f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return float(default)


# Streaming output rates, in tokens/second (a premium model is deliberate).
TEXT_TPS = _f("GIBBERISH_TEXT_TPS", 38.0)
THINK_TPS = _f("GIBBERISH_THINK_TPS", 48.0)
TOOL_TPS = _f("GIBBERISH_TOOL_TPS", 85.0)

# Time-to-first-token (seconds): latency before any output appears.
TTFT_MIN = _f("GIBBERISH_TTFT_MIN", 1.0)
TTFT_MAX = _f("GIBBERISH_TTFT_MAX", 4.0)

# Thinking-phase budget (seconds), sampled per request.
THINK_MIN = _f("GIBBERISH_THINK_MIN", 2.5)
THINK_MAX = _f("GIBBERISH_THINK_MAX", 12.0)

# When the client did NOT request visible thinking, the model still
# "deliberates" silently before answering. This caps that hidden pause (s).
HIDDEN_THINK_CAP = _f("GIBBERISH_HIDDEN_THINK_CAP", 6.0)

# Tool (bash) execution latency (seconds).
TOOL_EXEC_MIN = _f("GIBBERISH_TOOL_EXEC_MIN", 0.4)
TOOL_EXEC_MAX = _f("GIBBERISH_TOOL_EXEC_MAX", 2.5)

# Global multiplier applied to every delay. 1.0 = realistic.
SPEED = _f("GIBBERISH_SPEED", 1.0)

# Rough words-per-token factor used to size/pace generated content.
TOKENS_PER_WORD = 1.3

# Per-chunk pacing jitter (multiplicative).
_JITTER_LO = 0.7
_JITTER_HI = 1.35


class RequestTiming:
    """A per-request latency profile.

    Parameters
    ----------
    want_thinking:
        Whether the client asked for a visible extended-thinking phase.
    """

    def __init__(self, want_thinking: bool) -> None:
        self.want_thinking = want_thinking
        # Per-request speed multiplier: some responses are snappy, some
        # sluggish. Log-normal keeps it centred near 1 with a modest tail.
        self.factor = random.lognormvariate(0.0, 0.22)
        # Nominal thinking budget for this request (seconds), always sampled so
        # that even non-thinking requests have a realistic deliberation pause.
        self.think_budget = random.uniform(THINK_MIN, THINK_MAX)

    # -- sizing -----------------------------------------------------------
    def think_words(self) -> int:
        """Number of reasoning words to generate to fill the think budget."""
        tokens = self.think_budget * THINK_TPS
        return max(0, int(tokens / TOKENS_PER_WORD))

    # -- delays -----------------------------------------------------------
    def initial_delay(self, visible_thinking: bool) -> float:
        """Latency before the first output token of the response."""
        delay = random.uniform(TTFT_MIN, TTFT_MAX)
        if not visible_thinking:
            # Fold a (capped) slice of the think budget into a silent pause.
            hidden = min(self.think_budget, HIDDEN_THINK_CAP)
            delay += hidden * random.uniform(0.5, 1.0)
        return delay * self.factor * SPEED

    def think_delay(self, words_in_chunk: int) -> float:
        base = (words_in_chunk * TOKENS_PER_WORD) / THINK_TPS
        delay = base * random.uniform(_JITTER_LO, _JITTER_HI)
        # Occasional longer "pondering" pause mid-thought.
        if random.random() < 0.025:
            delay += random.uniform(0.3, 1.1)
        return delay * self.factor * SPEED

    def text_delay(self, words_in_chunk: int) -> float:
        base = (words_in_chunk * TOKENS_PER_WORD) / TEXT_TPS
        return base * random.uniform(_JITTER_LO, _JITTER_HI) * self.factor * SPEED

    def tool_delay(self, words_in_chunk: int) -> float:
        base = (words_in_chunk * TOKENS_PER_WORD) / TOOL_TPS
        return base * random.uniform(0.7, 1.4) * self.factor * SPEED

    def tool_exec_latency(self) -> float:
        """Simulated time for a (fake) bash command to run."""
        return random.uniform(TOOL_EXEC_MIN, TOOL_EXEC_MAX) * self.factor * SPEED
