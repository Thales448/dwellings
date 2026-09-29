from functools import lru_cache
from pathlib import Path


@lru_cache
def breached_passwords() -> frozenset[str]:
    path = Path(__file__).with_name("breached_top100k.txt")
    words: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        word = line.strip()
        if not word or word.startswith("#"):
            continue
        words.add(word)
        words.add(word.lower())
    return frozenset(words)


def is_breached(password: str) -> bool:
    words = breached_passwords()
    return password in words or password.lower() in words
