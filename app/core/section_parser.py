import re
from typing import Optional
from .sheets import sheets_client

_WORDS_RE = re.compile(r"[^\w\u0400-\u04FF]+", flags=re.UNICODE)


def _norm(s: str) -> str:
    s = (s or "").lower().strip()
    s = s.replace("і", "и").replace("ї", "и").replace("є", "е").replace("ґ", "г")
    s = _WORDS_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _stem(word: str) -> str:
    if len(word) <= 3:
        return word

    endings = [
        'ого', 'ому', 'ими', 'ыми', 'ому', 'ого', 'ой', 'ый', 'ий', 'ас', 'яс', 'ое', 'ее',
        'ом', 'ою', 'ам', 'ами', 'ах', 'ів', 'ов', 'ей', 'ям', 'ями', 'ях',
        'а', 'у', 'ю', 'о', 'е', 'і', 'и', 'ь', 'ї'
    ]

    for ending in sorted(endings, key=len, reverse=True):
        if word.endswith(ending) and len(word) - len(ending) >= 3:
            return word[:-len(ending)]

    return word


_SECTION_KEYWORDS = {}


def reload_sections():
    global _SECTION_KEYWORDS
    _SECTION_KEYWORDS = {}
    try:
        rows = sheets_client.sections()
        for row in rows:
            keywords_str = str(row.get("keyword", "")).strip()
            section = str(row.get("section_value", "")).strip()
            if keywords_str and section:
                for kw in keywords_str.split(","):
                    kw_normalized = _norm(kw.strip())
                    if kw_normalized:
                        kw_stemmed = _stem(kw_normalized)
                        _SECTION_KEYWORDS[kw_stemmed] = section
    except Exception:
        pass


reload_sections()


def detect_section(text: str) -> Optional[str]:
    normalized = _norm(text)
    words = normalized.split()

    for word in words:
        stemmed = _stem(word)
        if stemmed in _SECTION_KEYWORDS:
            return _SECTION_KEYWORDS[stemmed]

    return None