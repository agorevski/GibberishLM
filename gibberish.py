"""Generate fabricated thinking and prose for the API, plus demo commands."""

from __future__ import annotations

import random
from typing import List

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
