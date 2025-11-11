from typing import Optional
from .sheets import sheets_client

class RuleMatcher:
    def __init__(self) -> None:
        self._objections = sheets_client.objections
        self._reactions = sheets_client.reactions

    def reload(self) -> None:
        self._objections = sheets_client.objections
        self._reactions = sheets_client.reactions

    def match_objection(self, text: str) -> Optional[str]:
        normalized = text.lower()
        for key, value in self._objections().items():
            if key in normalized:
                return value
        return None

    def match_reaction(self, text: str) -> Optional[str]:
        normalized = text.lower()
        for key, value in self._reactions().items():
            if key in normalized:
                return value
        return None

rule_matcher = RuleMatcher()
