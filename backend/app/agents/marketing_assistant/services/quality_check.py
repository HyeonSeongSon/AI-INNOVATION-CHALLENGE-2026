"""
메시지 품질 검사 서비스

3단계 품질 검증:
1. Rule-based Check (동기, 비용 0)
2. Semantic Similarity Check (비동기, OpenSearch KNN, 비용 0)
3. LLM-as-a-Judge (비동기, LLM 1회 호출)
"""

# 직접 실행 지원 (python quality_check.py)
# 상대 임포트가 작동하려면 __package__ 설정이 상대 임포트보다 먼저 와야 함
import sys as _sys
from pathlib import Path as _Path

if __name__ == "__main__":
    _proj_root = str(_Path(__file__).resolve().parents[5])
    if _proj_root not in _sys.path:
        _sys.path.insert(0, _proj_root)
    __package__ = "backend.app.agents.marketing_assistant.services"

import re
import os
import json
import asyncio
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
from pydantic import BaseModel, Field
from langchain_core.language_models import BaseChatModel
from dotenv import load_dotenv
import httpx
from ..prompts.quality_check_prompt import build_quality_check_prompt
from ....core.logging import get_logger
from ....core.langsmith_config import traced
from ....config.settings import settings
from .product_client import ProductClient
import yaml

# .env 파일 로드
load_dotenv(os.path.join(os.path.dirname(__file__), "../../../.env"))

logger = get_logger("quality_check")
_product_client = ProductClient()

# ============================================================
# LLM 구조화 출력 모델
# ============================================================

class LLMJudgeOutput(BaseModel):
    """LLM-as-a-Judge 구조화된 출력"""
    accuracy: int = Field(..., ge=1, le=5, description="정확성: 상품 정보가 정확하게 반영되었는지 (1-5)")
    tone: int = Field(..., ge=1, le=5, description="톤: 브랜드 톤에 부합하는지 (1-5)")
    personalization: int = Field(..., ge=1, le=5, description="개인화: 페르소나에 맞춤화되었는지 (1-5)")
    naturalness: int = Field(..., ge=1, le=5, description="자연스러움: 문장이 자연스럽고 읽기 좋은지 (1-5)")
    safety: int = Field(..., ge=1, le=5, description="안전성: 금지 표현이 없고 과장이 없는지 (1-5)")
    passed: bool = Field(..., description="전체 통과 여부 (모든 항목 3점 이상이면 True)")
    feedback: str = Field(..., description="종합 피드백 (한글, 2-3문장)")


# ============================================================
# 품질 검사 서비스 클래스
# ============================================================

class QualityChecker:
    """마케팅 메시지 품질 검사 서비스"""

    def __init__(self):
        """초기화: brand_tone YAML, forbidden_keyword JSON 로드"""
        # brand_tone YAML 로드
        if os.environ.get("APP_ROOT"):
            root_dir = Path(os.environ.get("APP_ROOT"))
            data_path = root_dir / "agents" / "crm_agent" / "prompts" / "brand_tone.yaml"
        else:
            root_dir = Path(__file__).resolve().parents[1]
            data_path = root_dir / "prompts" / "brand_tone.yaml"

        self.brand_tones = self._load_yaml(data_path)

        # forbidden_keyword.json 로드
        if os.environ.get("APP_ROOT"):
            forbidden_path = root_dir / "agents" / "crm_agent" / "data" / "forbidden_keyword.json"
        else:
            forbidden_path = root_dir / "data" / "forbidden_keyword.json"
        self.forbidden_keywords = self._load_json(forbidden_path)

        logger.info("quality_checker_initialized")

    # 병합 시 DB에서 제외할 필드
    # - 내부 필드: 메시지 생성에 불필요
    # - 중복 필드: 벡터 DB의 한국어 키와 값이 동일한 영문 키
    _DB_EXCLUDE_KEYS = {
        # 내부 필드
        "vectordb_id", "product_created_at",
        # 벡터 DB 한국어 키와 중복 (상품명, 브랜드, 태그, 피부타입, 선호/기피성분, 선호향, 가치관, 선호포인트색상, 전용제품)
        "product_name", "brand", "product_tag",
        "skin_type", "preferred_ingredients", "avoided_ingredients",
        "preferred_scents", "values", "preferred_colors", "exclusive_product",
    }

    def _merge_product_data(self, db_product: Dict[str, Any], vector_product: Dict[str, Any]) -> Dict[str, Any]:
        """
        벡터 DB 데이터를 기반으로 DB의 비중복 필드를 추가해 병합

        - 벡터 DB: 전체 포함 (_vector 필드, URL 필드 제외)
        - DB: 벡터 DB에 없는 키만 추가 (내부 필드, URL 필드 제외)
        """
        def _is_url_field(key: str) -> bool:
            return "url" in key.lower() or key == "상품이미지"

        vector_clean = {
            k: v for k, v in vector_product.items()
            if "_vector" not in k and not _is_url_field(k)
        }
        db_extra = {
            k: v for k, v in db_product.items()
            if k not in vector_clean and k not in self._DB_EXCLUDE_KEYS and not _is_url_field(k)
        }
        return {**vector_clean, **db_extra}

    def _load_yaml(self, file_path) -> Dict[str, Any]:
        """YAML 파일 로드"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error("yaml_load_failed", file_path=str(file_path), error=str(e), exc_info=True)
            return {}

    def _load_json(self, file_path) -> Dict[str, Any]:
        """JSON 파일 로드"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error("json_load_failed", file_path=str(file_path), error=str(e), exc_info=True)
            return {}

# ============================================================
# Public: 3단계 품질 검사 오케스트레이션
# ============================================================

    @traced(name="quality_check", run_type="chain")
    async def check_quality(
        self,
        message: Dict[str, Any],
        product_id: str,
        purpose: str,
        llm: Optional[BaseChatModel] = None,
    ) -> Dict[str, Any]:
        """
        메시지 품질 검사 (3단계 순차 실행, 실패 시 단락)

        Returns:
            QualityCheckResult dict
        """
        title = message.get("title", "")
        message_text = message.get("message", "")

        vector_products, db_products = await asyncio.gather(
            _product_client.get_products_by_ids([product_id]),
            _product_client.get_products_detail_from_db([product_id]),
        )
        vector_product = vector_products[0] if vector_products else {}
        db_product = db_products[0] if db_products else {}

        product = self._merge_product_data(db_product, vector_product)
        print(product)
        product_name = db_product.get("product_name", "")
        brand_name = db_product.get("brand", "")

        result = {
            "passed": False,
            "failed_stage": None,
            "failure_reason": None,
            "rule_check_passed": False,
            "rule_check_issues": [],
            "semantic_check_passed": False,
            "semantic_check_results": [],
            "llm_judge_passed": False,
            "llm_judge_scores": None,
        }

        # Stage 1: Rule-based Check
        logger.info("stage1_rule_check_started")
        passed, issues = self._run_rule_check(title, message_text)
        result["rule_check_passed"] = passed
        result["rule_check_issues"] = issues
        if not passed:
            result["failed_stage"] = "rule_check"
            result["failure_reason"] = f"규칙 기반 검사 실패: {'; '.join(issues)}"
            logger.warning("stage1_failed", issues=issues)
            return result
        logger.info("stage1_passed")

        # Stage 2: Semantic Similarity Check
        logger.info("stage2_semantic_check_started")
        passed, similar_results = await self._run_semantic_similarity_check(title, message_text)
        result["semantic_check_passed"] = passed
        result["semantic_check_results"] = similar_results
        if not passed:
            result["failed_stage"] = "semantic_check"
            triggered_details = "; ".join([
                f"'{r['query_sentence'][:40]}' → {r['source'].get('label', '금지표현')} (유사도 {r['score']:.2f})"
                for r in similar_results[:2]
            ])
            result["failure_reason"] = f"금지 표현 유사 문장 감지: {triggered_details}"
            logger.warning("stage2_semantic_failed", triggered=similar_results)
            return result
        logger.info("stage2_semantic_passed")

        # Stage 3: LLM-as-a-Judge
        logger.info("stage3_llm_judge_started")
        passed, scores = await self._run_llm_judge(
            title, message_text, product_name, product, purpose, brand_name, llm
        )
        result["llm_judge_passed"] = passed
        result["llm_judge_scores"] = scores
        if not passed:
            result["failed_stage"] = "llm_judge"
            result["failure_reason"] = f"LLM 평가 미통과: {scores.get('feedback', '') if scores else '평가 실패'}"
            logger.warning("stage3_failed", scores=scores)
            return result
        logger.info("stage3_passed", scores=scores)

        # 전체 통과
        result["passed"] = True
        logger.info("quality_check_all_passed")
        return result

# ============================================================
# Stage 1: Rule-based Check
# ============================================================

    def _run_rule_check(
        self,
        title: str,
        message: str,
    ) -> Tuple[bool, List[str]]:
        """
        규칙 기반 품질 검사

        검사 항목:
        - 제목/본문 존재 및 길이 검증
        - 상품명/브랜드명 포함 여부
        - 금지 표현 키워드 매칭
        """
        issues = []

        full_text = f"{title} {message}"

        # 1. 포맷 검증
        if not title:
            issues.append("제목이 비어있습니다")
        if not message:
            issues.append("메시지 본문이 비어있습니다")

        # 2. 길이 검증
        if title and len(title) < 5:
            issues.append(f"제목이 너무 짧습니다 ({len(title)}자, 최소 5자)")
        if title and len(title) > 40:
            issues.append(f"제목이 너무 깁니다 ({len(title)}자, 최대 40자)")
        if message and len(message) < 20:
            issues.append(f"메시지가 너무 짧습니다 ({len(message)}자, 최소 20자)")
        if message and len(message) > 350:
            issues.append(f"메시지가 너무 깁니다 ({len(message)}자, 최대 350자)")

        # 3. 금지 표현 검사
        forbidden = self._extract_forbidden_expressions()
        for expr in forbidden:
            expr_stripped = expr.strip()
            if expr_stripped and expr_stripped in full_text:
                issues.append(f"금지 표현 감지: '{expr_stripped}'")

        passed = len(issues) == 0
        return passed, issues

    def _extract_forbidden_expressions(self) -> List[str]:
        """
        forbidden_keyword.json에서 전체 금지 키워드 목록 추출

        Returns:
            금지 표현 키워드 리스트
        """
        categories = self.forbidden_keywords.get("categories", {})
        keywords = []
        for category in categories.values():
            keywords.extend(category.get("keywords", []))
        return keywords

# ============================================================
# Stage 2: Semantic Similarity Check
# ============================================================

    _SEMANTIC_THRESHOLD = 0.85
    _SEMANTIC_INDEX = "forbidden_sentences"
    _SEMANTIC_TOP_K = 3

    @traced(name="semantic_similarity_check", run_type="chain")
    async def _run_semantic_similarity_check(
        self,
        title: str,
        message: str,
    ) -> Tuple[bool, List[Dict[str, Any]]]:
        """
        생성된 메시지를 문장 단위로 분리 후 각 문장을
        /api/search/similar-sentences 엔드포인트로 유사도 검색.

        모든 문장의 top-K 결과를 하나의 리스트에 누적하여
        임계값(SEMANTIC_THRESHOLD) 초과 score가 하나라도 있으면 실패.

        Returns:
            (passed: bool, triggered_results: List[dict])
            - passed=True  → 금지 표현 없음
            - passed=False → 임계값 초과 결과 목록 반환
        """
        endpoint = f"{settings.opensearch_api_url}/api/search/similar-sentences"

        full_text = f"{title} {message}".strip()

        # 문장 단위 분리: ., !, ? 기준 (빈 문장 제거)
        sentences = [
            s.strip()
            for s in re.split(r"[.!?。！？]+", full_text)
            if s.strip()
        ]

        if not sentences:
            return True, []

        # 각 문장을 병렬로 유사도 검색
        async def search_sentence(sentence: str) -> List[Dict[str, Any]]:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(
                        endpoint,
                        json={
                            "index_name": self._SEMANTIC_INDEX,
                            "query": sentence,
                            "top_k": self._SEMANTIC_TOP_K,
                        },
                    )
                    response.raise_for_status()
                    data = response.json()
                    return [
                        {
                            "query_sentence": sentence,
                            "matched_sentence": r.get("sentence"),
                            "score": r.get("score", 0.0),
                            "source": r.get("source", {}),
                        }
                        for r in data.get("results", [])
                    ]
            except Exception as e:
                logger.warning(
                    "semantic_search_request_failed",
                    sentence=sentence,
                    error=str(e),
                )
                return []

        all_results: List[Dict[str, Any]] = []
        search_tasks = [search_sentence(s) for s in sentences]
        results_per_sentence = await asyncio.gather(*search_tasks)
        for results in results_per_sentence:
            all_results.extend(results)

        # 문장별 최고점 1개만 추출 후 score 내림차순 상위 3개 로깅
        top_per_sentence: Dict[str, Dict] = {}
        for r in all_results:
            q = r["query_sentence"]
            if q not in top_per_sentence or r["score"] > top_per_sentence[q]["score"]:
                top_per_sentence[q] = r
        top3 = sorted(top_per_sentence.values(), key=lambda r: r["score"], reverse=True)[:3]
        logger.info(
            "semantic_check_top3",
            top3=[
                {"query": r["query_sentence"], "matched": r["matched_sentence"], "score": r["score"]}
                for r in top3
            ],
        )

        # 임계값 초과 결과 필터
        triggered = [r for r in all_results if r["score"] > self._SEMANTIC_THRESHOLD]

        if triggered:
            logger.info(
                "semantic_check_triggered",
                threshold=self._SEMANTIC_THRESHOLD,
                triggered_count=len(triggered),
            )
            return False, triggered

        return True, []

# ============================================================
# Stage 3: LLM-as-a-Judge
# ============================================================

    @traced(name="llm_judge", run_type="llm")
    async def _run_llm_judge(
        self,
        title: str,
        message: str,
        product_name: str,
        product: Dict[str, Any],
        purpose: str,
        brand_name: str,
        llm: Optional[BaseChatModel] = None,
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        LLM-as-a-Judge 평가

        with_structured_output(LLMJudgeOutput) 사용
        통과 기준: 모든 항목 3점 이상
        """
        try:
            brand_tone = self._get_brand_tone(brand_name)

            prompt_messages = build_quality_check_prompt(
                brand_name=brand_name,
                product_name=product_name,
                product_info=product,
                purpose=purpose,
                brand_tone=brand_tone,
                title=title,
                message=message,
            )

            judge = llm.with_structured_output(LLMJudgeOutput)
            result: LLMJudgeOutput = await judge.ainvoke(prompt_messages)

            scores = {
                "accuracy": result.accuracy,
                "tone": result.tone,
                "personalization": result.personalization,
                "naturalness": result.naturalness,
                "safety": result.safety,
                "overall": round(
                    (result.accuracy + result.tone + result.personalization
                     + result.naturalness + result.safety) / 5.0, 2
                ),
                "feedback": result.feedback,
            }

            return result.passed, scores

        except Exception as e:
            logger.error("llm_judge_failed", error=str(e), exc_info=True)
            return False, {"feedback": f"LLM 평가 중 오류: {str(e)}"}

    def _get_brand_tone(self, brand_name: str) -> str:
        """브랜드톤 가져오기"""
        brand_tones = self.brand_tones.get("brand_ton_prompt", {})

        if brand_name in brand_tones:
            return brand_tones[brand_name]

        for key, value in brand_tones.items():
            if key.lower() == brand_name.lower():
                return value

        logger.warning("brand_tone_not_found", brand_name=brand_name)
        return "친근하면서도 전문적이고 신뢰감 있는 어조"


if __name__ == "__main__":
    checker = QualityChecker()
    from ....core.llm_factory import get_llm

    test_message = {
        "title": "가려움 걱정 없는 하루, 보타닉센스와 함께",
        "message": "온데칸 특허 성분이 히스타민 분비를 줄여 가려움을 완화하고, 인체적용시험으로 즉각적인 보습 개선을 돕는 올인원 로션입니다. 가벼운 로션 제형이 끈적임 없이 스며들어 온 가족이 매일 사용하기 좋습니다.",
    }
    llm = get_llm(model_name="gpt-5-mini", temperature=0.7)
    result = asyncio.run(
        checker.check_quality(
            message=test_message,
            product_id="A20251200289",
            purpose="베스트셀러 제품 소개",
            llm=llm
        )
    )
    print(result)