import re
from typing import Dict, List, Optional, Tuple
from .sheets import sheets_client

_WORDS_RE = re.compile(r"[^\w\u0400-\u04FF]+", flags=re.UNICODE)

def _norm(s: str) -> str:
    s = (s or "").lower().strip()
    s = s.replace("і", "и").replace("ї", "и").replace("є", "е").replace("ґ", "г")
    s = _WORDS_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _split_triggers(raw: str) -> List[str]:
    return [t.strip() for t in (raw or "").split(",") if t.strip()]

class RuleEngine:
    def __init__(self) -> None:
        self._objections: List[Tuple[str, str, str]] = []
        self._viewing_kw: List[str] = []
        self._more_kw: List[str] = []
        self._new_search_kw: List[str] = []
        self._skip_kw: List[str] = []
        self._continue_kw: List[str] = []

    def reload(self) -> None:
        self._load_objections()
        self._load_keywords()

    def _load_objections(self) -> None:
        rows = sheets_client.fetch_records("objections")
        items: List[Tuple[str, str, str]] = []
        for r in rows:
            raw_tr = str(r.get("trigger") or "")
            resp = str(r.get("response") or "")
            key = str(r.get("key") or "").strip().lower()
            for trig in _split_triggers(raw_tr):
                nt = _norm(trig)
                if nt:
                    items.append((nt, resp, key))
        self._objections = items

    def _load_keywords(self) -> None:
        try:
            rows = sheets_client.fetch_records("keywords")
            viewing_vals = ""
            more_vals = ""
            new_search_vals = ""
            skip_filter_vals = ""
            continue_vals = ""
            for r in rows:
                t = str(r.get("type") or "").strip().lower()
                v = str(r.get("values") or "")
                if t == "viewing":
                    viewing_vals = v
                elif t == "more":
                    more_vals = v
                elif t == "new_search":
                    new_search_vals = v
                elif t == "skip_filter":
                    skip_filter_vals = v
                elif t == "continue":
                    continue_vals = v
            self._viewing_kw = [_norm(x) for x in viewing_vals.split(",") if x.strip()]
            self._more_kw = [_norm(x) for x in more_vals.split(",") if x.strip()]
            self._new_search_kw = [_norm(x) for x in new_search_vals.split(",") if x.strip()]
            self._skip_kw = [_norm(x) for x in skip_filter_vals.split(",") if x.strip()]
            self._continue_kw = [_norm(x) for x in continue_vals.split(",") if x.strip()]
        except Exception:
            self._viewing_kw = []
            self._more_kw = []
            self._new_search_kw = []
            self._skip_kw = []
            self._continue_kw = []

    def is_continue(self, text: str) -> bool:
        q = _norm(text or "")
        wrap = f" {q} "
        return any(f" {kw} " in wrap for kw in self._continue_kw)

    def is_skip(self, text: str) -> bool:
        q = _norm(text or "")
        wrap = f" {q} "
        return any(f" {kw} " in wrap for kw in self._skip_kw)

    def match_objection(self, text: str) -> Optional[Dict[str, str]]:
        q = _norm(text or "")
        if not q:
            return None
        wrap = f" {q} "
        for trig, resp, key in self._objections:
            if f" {trig} " in wrap:
                return {"response": resp, "key": key}
        return None

    def is_viewing(self, text: str) -> bool:
        q = _norm(text or "")
        wrap = f" {q} "
        return any(f" {kw} " in wrap for kw in self._viewing_kw)

    def is_more(self, text: str) -> bool:
        q = _norm(text or "")
        wrap = f" {q} "
        return any(f" {kw} " in wrap for kw in self._more_kw)

    def is_new_search(self, text: str) -> bool:
        q = _norm(text or "")
        wrap = f" {q} "
        return any(f" {kw} " in wrap for kw in self._new_search_kw)

rule_engine = RuleEngine()
