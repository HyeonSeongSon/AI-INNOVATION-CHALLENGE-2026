"""
메시지 품질 검사 서비스

3단계 품질 검증:
1. Rule-based Check (동기, 비용 0)
2. Semantic Similarity Check (비동기, OpenSearch KNN, 비용 0)
3. LLM-as-a-Judge (비동기, LLM 1회 호출)
"""

import re
import asyncio
from typing import Dict, Any, Optional, List, Tuple
from pydantic import BaseModel, Field
from langchain_core.language_models import BaseChatModel
import httpx
import ahocorasick
from kiwipiepy import Kiwi
from ..prompts.quality_check_prompt import build_quality_check_prompt
from ....core.logging import get_logger
from ....core.langsmith_config import traced
from ....core.data_loader import get_brand_tones, get_forbidden_keywords
from ....config.settings import settings
from .product_client import ProductClient

logger = get_logger("quality_check")
_product_client = ProductClient()

# ============================================================
# LLM 구조화 출력 모델
# ============================================================

class LLMJudgeOutput(BaseModel):
    """LLM-as-a-Judge 구조화된 출력"""
    accuracy: int = Field(..., ge=1, le=5, description="정확성: 상품 정보가 정확하게 반영되었는지 (1-5)")
    tone: int = Field(..., ge=1, le=5, description="톤: 브랜드 톤 가이드의 문체·어조가 구현되었는지 (1-5)")
    personalization: int = Field(..., ge=1, le=5, description="개인화: 타깃 고객 고민과 핵심 혜택이 메시지에 반영되었는지 (1-5)")
    naturalness: int = Field(..., ge=1, le=5, description="자연스러움: 문장이 자연스럽고 모바일 가독성에 적합한지 (1-5)")
    cta_clarity: int = Field(..., ge=1, le=5, description="CTA 명확도: 소비자가 취해야 할 다음 행동이 명확히 안내되는지 (1-5)")
    feedback: str = Field(..., description="종합 피드백 (한글, 2-4문장)")


# ============================================================
# 품질 검사 서비스 클래스
# ============================================================

class QualityChecker:
    """마케팅 메시지 품질 검사 서비스"""

    def __init__(self):
        self._forbidden_expressions: List[str] = self._extract_forbidden_expressions()
        self._kiwi = Kiwi()
        self._automaton = self._build_automaton()
        logger.info("quality_checker_initialized")


# ============================================================
# Public: 3단계 품질 검사
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
        마케팅 메시지 품질 검사를 3단계로 순차 실행합니다.

        각 단계가 실패하면 이후 단계는 건너뜁니다 (단락 평가):
            1. Rule-based Check  — 동기, 비용 0
            2. Semantic Similarity Check — 비동기, OpenSearch KNN
            3. LLM-as-a-Judge — 비동기, LLM 1회 호출

        Args:
            message:    검사할 메시지 dict. ``title`` 과 ``message`` 키를 포함해야 합니다.
            product_id: 검사 기준이 되는 상품 ID.
            purpose:    메시지 발송 목적 (예: "베스트셀러 제품 소개").
            llm:        Stage 3에서 사용할 LangChain LLM 인스턴스.
                        None이면 LLM 평가를 건너뛰고 실패 처리합니다.

        Returns:
            품질 검사 결과 dict::

                {
                    "passed": bool,                   # 전체 통과 여부
                    "failed_stage": str | None,       # 실패한 단계명
                    "failure_reason": str | None,     # 실패 사유
                    "rule_check_passed": bool,
                    "rule_check_issues": List[str],
                    "semantic_check_passed": bool,
                    "semantic_check_results": List[dict],
                    "llm_judge_passed": bool,
                    "llm_judge_scores": dict | None,
                }
        """
        title = message.get("title", "")
        message_text = message.get("message", "")

        if not product_id:
            return {
                "passed": False,
                "failed_stage": "product_fetch",
                "failure_reason": "product_id가 비어있습니다",
                "rule_check_passed": False,
                "rule_check_issues": [],
                "semantic_check_passed": False,
                "semantic_check_results": [],
                "llm_judge_passed": False,
                "llm_judge_scores": None,
            }

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

        vector_products, db_products = await asyncio.gather(
            _product_client.get_products_by_ids([product_id]),
            _product_client.get_products_detail_from_db([product_id]),
        )
        vector_product = vector_products[0] if vector_products else {}
        db_product = db_products[0] if db_products else {}

        if not db_product:
            logger.error("product_db_not_found", product_id=product_id)
            result["failed_stage"] = "product_fetch"
            result["failure_reason"] = f"상품 정보를 찾을 수 없습니다 (product_id: {product_id})"
            return result

        if not vector_product:
            logger.warning("product_vector_not_found", product_id=product_id)

        product = _product_client.merge_product_data(db_product, vector_product)

        product_name = db_product.get("product_name", "")
        brand_name = db_product.get("brand", "")

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
            if similar_results and similar_results[0].get("error") == "api_unavailable":
                result["failure_reason"] = "의미 유사도 검사 불가 (API 오류)"
            else:
                triggered_details = "; ".join([
                    f"'{r['query_sentence'][:40]}' → {r['source'].get('label', '금지표현')} (유사도 {r['score']:.2f})"
                    for r in similar_results[:2]
                ])
                result["failure_reason"] = f"금지 표현 유사 문장 감지: {triggered_details}"
            logger.warning("stage2_semantic_failed", triggered=similar_results)
            return result
        logger.info("stage2_semantic_passed")

        # Stage 3: LLM-as-a-Judge
        if llm is None:
            logger.error("llm_judge_skipped", reason="llm not provided")
            result["failed_stage"] = "llm_judge"
            result["failure_reason"] = "LLM이 제공되지 않아 품질 평가를 수행할 수 없습니다"
            return result
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
        규칙 기반 품질 검사 (Stage 1).

        검사 항목:
            - 제목/본문 존재 여부
            - 제목 길이: 5–40자
            - 본문 길이: 20–350자
            - forbidden_keyword.json에 등재된 금지 표현 포함 여부

        Args:
            title:   메시지 제목.
            message: 메시지 본문.

        Returns:
            ``(passed, issues)`` 튜플.
            passed가 False이면 issues 리스트에 실패 사유가 담깁니다.
        """
        issues = []

        full_text = f"{title} {message}"

        # 포맷 검증
        if not title:
            issues.append("제목이 비어있습니다")
        if not message:
            issues.append("메시지 본문이 비어있습니다")

        # 길이 검증
        if title and len(title) < 5:
            issues.append(f"제목이 너무 짧습니다 ({len(title)}자, 최소 5자)")
        if title and len(title) > 40:
            issues.append(f"제목이 너무 깁니다 ({len(title)}자, 최대 40자)")
        if message and len(message) < 20:
            issues.append(f"메시지가 너무 짧습니다 ({len(message)}자, 최소 20자)")
        if message and len(message) > 350:
            issues.append(f"메시지가 너무 깁니다 ({len(message)}자, 최대 350자)")

        # 금지 표현 검사 (3단계 매칭)
        detected = self._detect_forbidden_expressions(full_text)
        for expr in detected:
            issues.append(f"금지 표현 감지: '{expr}'")

        passed = len(issues) == 0
        return passed, issues

    def _extract_forbidden_expressions(self) -> List[str]:
        """
        forbidden_keyword.json에서 전체 금지 키워드 목록 추출

        Returns:
            금지 표현 키워드 리스트
        """
        categories = get_forbidden_keywords().get("categories", {})
        keywords = []
        for category in categories.values():
            keywords.extend(category.get("keywords", []))
        return keywords

    @staticmethod
    def _strip_spaces(text: str) -> str:
        """공백을 모두 제거하여 띄어쓰기 불일치 무력화"""
        return re.sub(r"\s+", "", text)

    def _build_automaton(self) -> ahocorasick.Automaton:
        """
        Aho-Corasick 오토마톤 빌드 (공백 제거 정규화 적용).

        공백을 제거한 키워드를 등록하여 O(n+m)으로 다중 키워드 탐색.
        """
        A = ahocorasick.Automaton()
        for idx, expr in enumerate(self._forbidden_expressions):
            norm = self._strip_spaces(expr.strip())
            if norm:
                # 동일 정규화 키가 있으면 덮어쓰기(중복 방지)
                A.add_word(norm, (idx, expr.strip()))
        A.make_automaton()
        return A

    def _morpheme_tokens(self, text: str) -> str:
        """
        kiwipiepy로 체언·용언·어근 형태소만 추출하여 공백 구분 문자열 반환.

        조사·어미가 분리되므로 "피부를 치료해" → "피부 치료" 형태로
        키워드 형태소 시퀀스와 매칭할 수 있음.
        """
        tokens = [
            t.form
            for t in self._kiwi.tokenize(text)
            if t.tag.startswith(("N", "V", "XR"))
        ]
        return " ".join(tokens)

    def _detect_forbidden_expressions(self, text: str) -> List[str]:
        """
        3단계 금지 표현 탐지:
          1. 원문 Aho-Corasick  — 정확 매칭
          2. 공백 제거 Aho-Corasick — 띄어쓰기 변형 대응
          3. 형태소 분석 순차 매칭 — 조사·어미 변형 대응

        Returns:
            감지된 금지 표현 원문 리스트 (중복 제거)
        """
        detected: List[str] = []
        seen_idx: set = set()

        # Step 1: 원문 Aho-Corasick
        for _, (idx, original) in self._automaton.iter(text):
            if idx not in seen_idx:
                seen_idx.add(idx)
                detected.append(original)

        # Step 2: 공백 제거 후 Aho-Corasick
        norm_text = self._strip_spaces(text)
        for _, (idx, original) in self._automaton.iter(norm_text):
            if idx not in seen_idx:
                seen_idx.add(idx)
                detected.append(original)

        # Step 3: 형태소 분석 — 조사/어미 변형 대응
        morph_text = self._morpheme_tokens(text)
        for idx, expr in enumerate(self._forbidden_expressions):
            if idx in seen_idx:
                continue
            morph_expr = self._morpheme_tokens(expr)
            if morph_expr and morph_expr in morph_text:
                seen_idx.add(idx)
                detected.append(expr)

        return detected

# ============================================================
# Stage 2: Semantic Similarity Check
# ============================================================

    _SEMANTIC_THRESHOLD = 0.85
    _SEMANTIC_INDEX = "forbidden_sentences"
    _SEMANTIC_TOP_K = 3
    _SEMANTIC_MAX_RETRIES = 2

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

        # 문장 단위 분리: ., !, ?, 줄바꿈 기준 (빈 문장 제거)
        sentences = [
            s.strip()
            for s in re.split(r"[.!?。！？\n]+", full_text)
            if s.strip()
        ]

        if not sentences:
            return True, []

        all_results: List[Dict[str, Any]] = []

        async with httpx.AsyncClient(timeout=10.0) as client:
            search_tasks = [self._search_sentence(client, s, endpoint) for s in sentences]
            results_per_sentence = await asyncio.gather(*search_tasks)

        # API 오류가 하나라도 있으면 검증 불가 -> 안전하게 실패 처리
        api_errors = [s for s, r in zip(sentences, results_per_sentence) if r is None]
        if api_errors:
            logger.warning(
                "semantic_check_api_failed",
                failed_count=len(api_errors),
                total=len(sentences),
            )
            return False, [{"error": "api_unavailable"}]

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

    async def _search_sentence(
        self,
        client: httpx.AsyncClient,
        sentence: str,
        endpoint: str,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        단일 문장의 유사도 검색 요청을 보냅니다 (최대 ``_SEMANTIC_MAX_RETRIES``회 재시도).

        Args:
            client:   재사용할 httpx 비동기 클라이언트.
            sentence: 유사도를 검색할 단일 문장.
            endpoint: ``/api/search/similar-sentences`` 엔드포인트 URL.

        Returns:
            검색 결과 리스트 (각 항목은 ``query_sentence``, ``matched_sentence``,
            ``score``, ``source`` 키를 포함). 모든 재시도 실패 시 ``None``.
        """
        for attempt in range(1, self._SEMANTIC_MAX_RETRIES + 1):
            try:
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
                    attempt=attempt,
                    max_retries=self._SEMANTIC_MAX_RETRIES,
                    error=str(e),
                )
        return None  # 재시도 소진: 빈 결과(정상)와 구분

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
        LLM-as-a-Judge로 메시지 품질을 평가합니다 (Stage 3).

        ``llm.with_structured_output(LLMJudgeOutput)``을 통해 5개 항목
        (accuracy, tone, personalization, naturalness, safety)을 1–5점으로 채점합니다.

        통과 기준:
            - 모든 개별 항목 ≥ 3점
            - 5개 항목 평균(overall) ≥ 4.0점

        Args:
            title:        메시지 제목.
            message:      메시지 본문.
            product_name: 상품명.
            product:      벡터 DB + DB에서 병합한 상품 정보 dict.
            purpose:      메시지 발송 목적.
            brand_name:   브랜드명 (brand_tone 조회용).
            llm:          LangChain BaseChatModel 인스턴스.

        Returns:
            ``(passed, scores)`` 튜플.
            scores는 accuracy·tone·personalization·naturalness·safety·overall·feedback 키를 포함.
            LLM 호출 오류 시 ``(False, {"feedback": 오류 메시지})``.
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
                "cta_clarity": result.cta_clarity,
                "overall": round(
                    (result.accuracy + result.tone + result.personalization
                     + result.naturalness + result.cta_clarity) / 5.0, 2
                ),
                "feedback": result.feedback,
            }

            # 코드가 직접 판정: 모든 항목 3점 이상 AND 평균 4점 이상
            score_keys = ("accuracy", "tone", "personalization", "naturalness", "cta_clarity")
            passed = (
                all(scores[k] >= 3 for k in score_keys)
                and scores["overall"] >= 4
            )
            return passed, scores

        except Exception as e:
            logger.error("llm_judge_failed", error=str(e), exc_info=True)
            return False, {"feedback": f"LLM 평가 중 오류: {str(e)}"}

    def _get_brand_tone(self, brand_name: str) -> str:
        """
        브랜드명에 맞는 톤 가이드 문자열을 반환합니다.

        brand_tone.yaml의 ``brand_ton_prompt`` 섹션에서 대소문자 무관하게 조회합니다.
        일치하는 항목이 없으면 기본값 "친근하면서도 전문적이고 신뢰감 있는 어조"를 반환합니다.

        Args:
            brand_name: 조회할 브랜드명.

        Returns:
            해당 브랜드의 톤 가이드 문자열.
        """
        brand_tones = get_brand_tones().get("brand_ton_prompt", {})

        if brand_name in brand_tones:
            return brand_tones[brand_name]

        for key, value in brand_tones.items():
            if key.lower() == brand_name.lower():
                return value

        logger.warning("brand_tone_not_found", brand_name=brand_name)
        return "친근하면서도 전문적이고 신뢰감 있는 어조"