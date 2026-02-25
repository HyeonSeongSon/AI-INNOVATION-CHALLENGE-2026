"""
메시지 품질 검사 서비스

3단계 품질 검증:
1. Rule-based Check (동기, 비용 0)
2. Semantic Similarity Check (비동기, OpenSearch KNN, 비용 0)
3. LLM-as-a-Judge (비동기, LLM 1회 호출)
"""

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
import yaml

# .env 파일 로드
load_dotenv(os.path.join(os.path.dirname(__file__), "../../../.env"))

logger = get_logger("quality_check")


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
        product: Dict[str, Any],
        persona_info: Dict[str, Any],
        purpose: str,
        brand_name: str,
        product_document_summary: Optional[str] = None,
        llm: Optional[BaseChatModel] = None,
    ) -> Dict[str, Any]:
        """
        메시지 품질 검사 (3단계 순차 실행, 실패 시 단락)

        Returns:
            QualityCheckResult dict
        """
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
        passed, issues = self._run_rule_check(message)
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
        passed, similar_results = await self._run_semantic_similarity_check(message)
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
            message, product, persona_info, purpose, brand_name, product_document_summary, llm
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
        message: Dict[str, Any],
    ) -> Tuple[bool, List[str]]:
        """
        규칙 기반 품질 검사

        검사 항목:
        - 제목/본문 존재 및 길이 검증
        - 상품명/브랜드명 포함 여부
        - 금지 표현 키워드 매칭
        """
        issues = []
        title = message.get("title", "")
        msg_body = message.get("message", "")
        product_name = message.get("product_name", "")
        brand = message.get("brand", "")

        full_text = f"{title} {msg_body}"

        # 1. 포맷 검증
        if not title:
            issues.append("제목이 비어있습니다")
        if not msg_body:
            issues.append("메시지 본문이 비어있습니다")

        # 2. 길이 검증
        if title and len(title) < 5:
            issues.append(f"제목이 너무 짧습니다 ({len(title)}자, 최소 5자)")
        if title and len(title) > 40:
            issues.append(f"제목이 너무 깁니다 ({len(title)}자, 최대 40자)")
        if msg_body and len(msg_body) < 20:
            issues.append(f"메시지가 너무 짧습니다 ({len(msg_body)}자, 최소 20자)")
        if msg_body and len(msg_body) > 350:
            issues.append(f"메시지가 너무 깁니다 ({len(msg_body)}자, 최대 350자)")

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
        message: Dict[str, Any],
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
        opensearch_api_url = os.getenv("OPENSEARCH_API_URL")
        if not opensearch_api_url:
            raise ValueError("OPENSEARCH_API_URL이 .env 파일에 설정되어 있지 않습니다.")
        endpoint = f"{opensearch_api_url}/api/search/similar-sentences"

        title = message.get("title", "")
        msg_body = message.get("message", "")
        full_text = f"{title} {msg_body}".strip()

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

        # score 내림차순 상위 3개 로깅 (통과/실패 공통)
        top3 = sorted(all_results, key=lambda r: r["score"], reverse=True)[:3]
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
        message: Dict[str, Any],
        product: Dict[str, Any],
        persona_info: Dict[str, Any],
        purpose: str,
        brand_name: str,
        product_document_summary: Optional[str] = None,
        llm: Optional[BaseChatModel] = None,
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        LLM-as-a-Judge 평가

        with_structured_output(LLMJudgeOutput) 사용
        통과 기준: 모든 항목 3점 이상
        """
        try:
            brand_tone = self._get_brand_tone(brand_name)
            product_text = self._format_product_info(product)
            persona_text = self._format_persona_info(persona_info)

            prompt_messages = build_quality_check_prompt(
                brand_name=brand_name,
                product_name=message.get("product_name", ""),
                product_info=product_text,
                product_document_summary=product_document_summary or "",
                persona_info=persona_text,
                purpose=purpose,
                brand_tone=brand_tone,
                title=message.get("title", ""),
                message=message.get("message", ""),
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

    def _format_product_info(self, product: Dict[str, Any]) -> str:
        """상품 정보를 텍스트로 포맷팅"""
        sections = []

        if product.get("product_name"):
            sections.append(f"상품명: {product['product_name']}")
        if product.get("brand"):
            sections.append(f"브랜드: {product['brand']}")
        if product.get("product_tag"):
            sections.append(f"카테고리: {product['product_tag']}")
        if product.get("sale_price"):
            sections.append(f"가격: {product['sale_price']:,}원")
        if product.get("skin_type"):
            skin_types = product["skin_type"]
            if isinstance(skin_types, list):
                sections.append(f"적합 피부타입: {', '.join(skin_types)}")
        if product.get("skin_concerns"):
            concerns = product["skin_concerns"]
            if isinstance(concerns, list):
                sections.append(f"타겟 고민: {', '.join(concerns)}")
        if product.get("preferred_ingredients"):
            ingredients = product["preferred_ingredients"]
            if isinstance(ingredients, list):
                sections.append(f"주요 성분: {', '.join(ingredients)}")

        return "\n".join(sections)

    def _format_persona_info(self, persona_info: Dict[str, Any]) -> str:
        """페르소나 정보를 텍스트로 포맷팅"""
        sections = []

        if persona_info.get("이름"):
            sections.append(f"이름: {persona_info['이름']}")
        if persona_info.get("나이"):
            sections.append(f"나이: {persona_info['나이']}세")
        if persona_info.get("성별"):
            sections.append(f"성별: {persona_info['성별']}")
        if persona_info.get("피부타입"):
            skin_type = persona_info["피부타입"]
            if isinstance(skin_type, list):
                sections.append(f"피부타입: {', '.join(skin_type)}")
        if persona_info.get("고민_키워드"):
            concerns = persona_info["고민_키워드"]
            if isinstance(concerns, list):
                sections.append(f"피부 고민: {', '.join(concerns)}")
        if persona_info.get("선호_성분"):
            ingredients = persona_info["선호_성분"]
            if isinstance(ingredients, list):
                sections.append(f"선호 성분: {', '.join(ingredients)}")
        if persona_info.get("기피_성분"):
            avoided = persona_info["기피_성분"]
            if isinstance(avoided, list):
                sections.append(f"기피 성분: {', '.join(avoided)}")
        if persona_info.get("가치관"):
            values = persona_info["가치관"]
            if isinstance(values, list):
                sections.append(f"가치관: {', '.join(values)}")

        return "\n".join(sections)


# ============================================================
# 싱글톤 패턴
# ============================================================

_checker_instance = None


def get_quality_checker() -> QualityChecker:
    """QualityChecker 인스턴스를 가져오거나 생성 (싱글톤 패턴)"""
    global _checker_instance
    if _checker_instance is None:
        _checker_instance = QualityChecker()
    return _checker_instance
