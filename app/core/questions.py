import logging
from typing import Any, Dict, List, Optional
from .sheets import sheets_client

logger = logging.getLogger(__name__)


class QuestionFlow:

    def __init__(self):
        self._questions: List[Dict[str, Any]] = []
        self._questions_by_key: Dict[str, str] = {}
        self.reload()

    def reload(self) -> None:
        try:
            rows = sheets_client.fetch_records("questions")
            sorted_rows = sorted(rows, key=lambda r: int(r.get("order", 999)))

            self._questions = []
            self._questions_by_key = {}

            for row in sorted_rows:
                key = str(row.get("question_key", "")).strip().lower()
                question = str(row.get("question_text", "")).strip()

                if key and question:
                    self._questions.append({"key": key, "question": question})
                    self._questions_by_key[key] = question

            logger.info(f"[QUESTIONS] Loaded {len(self._questions)} questions")
        except Exception as e:
            logger.error(f"[QUESTIONS] Failed to load: {e}", exc_info=True)
            self._questions = []
            self._questions_by_key = {}

    def _key_mapping(self, table_key: str) -> List[str]:
        mapping = {
            "name": [],
            "district": ["district_id", "microarea_id", "street_id"],
            "rooms": ["rooms_in"],
            "state": ["condition_in"],
            "budget": ["price_min", "price_max"],
            "section": ["section"],
            "area": ["area_min", "area_max"],
            "floor": ["floor_min", "floor_max"]
        }
        return mapping.get(table_key, [])

    def get_missing_filters(self, filters: Dict[str, Any]) -> List[str]:
        missing = []

        for question_data in self._questions:
            key = question_data["key"]

            if key == "name":
                continue

            filter_keys = self._key_mapping(key)

            if not filter_keys:
                continue

            has_any = False
            for fk in filter_keys:
                if filters.get(fk):
                    has_any = True
                    break

            if not has_any:
                missing.append(key)

        return missing

    def get_next_question(self, filters: Dict[str, Any], asked: Optional[List[str]] = None) -> Optional[Dict[str, str]]:
        if asked is None:
            asked = []

        missing = self.get_missing_filters(filters)

        if not missing:
            return None

        for question_data in self._questions:
            if question_data["key"] in missing and question_data["key"] not in asked:
                return question_data

        return None

    def is_complete(self, filters: Dict[str, Any]) -> bool:
        return len(self.get_missing_filters(filters)) == 0


question_flow = QuestionFlow()