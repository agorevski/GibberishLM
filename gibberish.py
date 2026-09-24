"""Gibberish content engine.

Generates fake, deterministic-feeling-yet-random "agent" sessions that
imitate the structure of a Claude Code CLI interaction: reasoning
("thinking"), tool calls (bash commands), tool results, and a final
assistant message. Every byte produced here is nonsense by design.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Iterator, List

LOREM_WORDS: List[str] = (
    "lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod "
    "tempor incididunt ut labore et dolore magna aliqua enim ad minim veniam "
    "quis nostrud exercitation ullamco laboris nisi aliquip ex ea commodo "
    "consequat duis aute irure reprehenderit voluptate velit esse cillum "
    "fugiat nulla pariatur excepteur sint occaecat cupidatat non proident "
    "sunt culpa qui officia deserunt mollit anim id est laborum"
).split()

THINKING_OPENERS: List[str] = [
    "Let me work through what the user is asking",
    "I should break this down into a few steps",
    "First, let me consider the structure of the problem",
    "The user wants something specific here, so",
    "Let me reason about the best approach",
    "I need to figure out which files are involved",
    "Considering the trade-offs here",
]

FAKE_COMMANDS: List[str] = [
    'echo "hello world"',
    'echo "Gibberish online"',
    "ls -la",
    "pwd",
    'printf "%s\\n" lorem ipsum dolor',
    "cat /dev/null",
    "uname -a",
    'echo "all systems nominal"',
    "whoami",
    "date",
]

FAKE_COMMAND_OUTPUTS = {
    'echo "hello world"': "hello world",
    'echo "Gibberish online"': "Gibberish online",
    "ls -la": (
        "total 8\n"
        "drwxr-xr-x  2 lorem ipsum 4096 Jan  1 00:00 .\n"
        "drwxr-xr-x 42 lorem ipsum 4096 Jan  1 00:00 ..\n"
        "-rw-r--r--  1 lorem ipsum  217 Jan  1 00:00 dolor.txt"
    ),
    "pwd": "/home/lorem/ipsum",
    'printf "%s\\n" lorem ipsum dolor': "lorem\nipsum\ndolor",
    "cat /dev/null": "",
    "uname -a": "Gibberish 4.8.0-fake #1 SMP PREEMPT x86_64 GNU/Lorem",
    'echo "all systems nominal"': "all systems nominal",
    "whoami": "ipsum",
    "date": "Mon Jan  1 00:00:00 UTC 2024",
}


@dataclass
class Token:
    """A single streamed event in a fake session."""

    type: str       # thinking | text | tool_call | tool_result | status | done
    content: str = ""
    meta: dict | None = None


def _sentence(min_words: int = 6, max_words: int = 18) -> str:
    n = random.randint(min_words, max_words)
    words = random.choices(LOREM_WORDS, k=n)
    words[0] = words[0].capitalize()
    return " ".join(words) + random.choice([".", ".", ".", "!", "?"])


def _paragraph(min_sentences: int = 2, max_sentences: int = 5) -> str:
    n = random.randint(min_sentences, max_sentences)
    return " ".join(_sentence() for _ in range(n))


def _thinking_block() -> str:
    opener = random.choice(THINKING_OPENERS)
    return f"{opener}. " + _paragraph(2, 4)


def thinking_text(approx_words: int) -> str:
    """Generate reasoning-style gibberish of roughly ``approx_words`` words.

    Used to size the "thinking" phase so its streaming duration matches a
    sampled time budget (see ``timing.RequestTiming``).
    """
    if approx_words <= 0:
        return _thinking_block()
    opener = random.choice(THINKING_OPENERS) + "."
    parts = [opener]
    count = len(opener.split())
    while count < approx_words:
        sentence = _sentence(6, 16)
        parts.append(sentence)
        count += len(sentence.split())
    return " ".join(parts)


def build_session(prompt: str, think_words: int | None = None) -> Iterator[Token]:
    """Yield a sequence of Tokens describing a fake agent session.

    The prompt is intentionally ignored for content (everything is
    gibberish) but is echoed back so the experience feels responsive.

    ``think_words`` controls how much reasoning text is produced for each
    thinking block, so the caller can pace it to a sampled time budget.
    """

    yield Token("status", "Pondering")

    # A single, budget-sized thinking block.
    yield Token("thinking", thinking_text(think_words) if think_words
                else _thinking_block())

    # A short intro line.
    yield Token("text", _sentence(8, 14) + "\n\n")

    # One to three fake tool calls.
    for _ in range(random.randint(1, 3)):
        command = random.choice(FAKE_COMMANDS)
        yield Token("tool_call", command, meta={"tool": "bash"})
        output = FAKE_COMMAND_OUTPUTS.get(command, _sentence(3, 8))
        yield Token("tool_result", output, meta={"tool": "bash"})

        # Sometimes a shorter follow-up thought after a tool result.
        if random.random() < 0.5:
            follow = max(0, (think_words or 0) // 3)
            yield Token("thinking", thinking_text(follow) if follow
                        else _thinking_block())

    # Final assistant message: one or two paragraphs.
    for i in range(random.randint(1, 2)):
        suffix = "\n\n" if i == 0 else ""
        yield Token("text", _paragraph(2, 4) + suffix)

    yield Token("status", "Done")
    yield Token("done", "")


def stream_tokens(token: Token, chunk_words: int = 2) -> Iterator[str]:
    """Split a token's content into small chunks for realistic streaming."""
    if token.type in ("thinking", "text", "tool_result"):
        words = token.content.split(" ")
        for i in range(0, len(words), chunk_words):
            yield " ".join(words[i : i + chunk_words]) + (
                " " if i + chunk_words < len(words) else ""
            )
    else:
        yield token.content
