"""
정적 데이터 파일 싱글턴 로더.

brand_tone.yaml, forbidden_keyword.json, categories.json을 최초 1회만 로드하고
이후에는 캐시된 값을 반환합니다.
"""

import json
import yaml
from pathlib import Path
from typing import Any, Dict, List

from .logging import get_logger

logger = get_logger("data_loader")

# ── 경로 상수 ──────────────────────────────────────────────────────────────────
_APP_DIR = Path(__file__).resolve().parents[1]               # backend/app/
_PROJECT_ROOT = _APP_DIR.parents[1]                          # project root

# ── 모듈 레벨 캐시 ─────────────────────────────────────────────────────────────
_brand_tones: Dict[str, Any] | None = None
_forbidden_keywords: Dict[str, Any] | None = None
_categories: List[str] | None = None


def get_brand_tones() -> Dict[str, Any]:
    """brand_tone.yaml을 1회 로드 후 캐시된 dict 반환."""
    global _brand_tones
    if _brand_tones is None:
        path = _APP_DIR / "agents" / "generate_message_agent" / "prompts" / "brand_tone.yaml"
        try:
            with open(path, "r", encoding="utf-8") as f:
                _brand_tones = yaml.safe_load(f) or {}
            logger.info("brand_tones_loaded", path=str(path))
        except Exception as e:
            logger.error("brand_tones_load_failed", path=str(path), error=str(e))
            _brand_tones = {}
    return _brand_tones


def get_forbidden_keywords() -> Dict[str, Any]:
    """forbidden_keyword.json을 1회 로드 후 캐시된 dict 반환."""
    global _forbidden_keywords
    if _forbidden_keywords is None:
        path = _APP_DIR / "agents" / "generate_message_agent" / "data" / "forbidden_keyword.json"
        try:
            with open(path, "r", encoding="utf-8") as f:
                _forbidden_keywords = json.load(f)
            logger.info("forbidden_keywords_loaded", path=str(path))
        except Exception as e:
            logger.error("forbidden_keywords_load_failed", path=str(path), error=str(e))
            _forbidden_keywords = {}
    return _forbidden_keywords


_DEFAULT_BRAND_TONE = "친근하면서도 전문적이고 신뢰감 있는 어조"


def get_brand_tone(brand_name: str) -> str:
    """브랜드명으로 톤 가이드 조회. 없으면 기본값 반환."""
    brand_tones = get_brand_tones().get("brand_ton_prompt", {})
    if brand_name in brand_tones:
        return brand_tones[brand_name]
    for key, value in brand_tones.items():
        if key.lower() == brand_name.lower():
            return value
    logger.warning("brand_tone_not_found", brand_name=brand_name)
    return _DEFAULT_BRAND_TONE


def get_categories() -> List[str]:
    """category.json에서 카테고리 목록을 1회 로드 후 캐시된 리스트 반환."""
    global _categories
    if _categories is None:
        docker_path = Path("/app/data/category.json")
        local_path = _PROJECT_ROOT / "data" / "category.json"
        path = docker_path if docker_path.exists() else local_path
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            _categories = data["sub_tags"]
            logger.info("categories_loaded", path=str(path), count=len(_categories))
        except Exception as e:
            logger.error("categories_load_failed", path=str(path), error=str(e))
            _categories = []
    return _categories
