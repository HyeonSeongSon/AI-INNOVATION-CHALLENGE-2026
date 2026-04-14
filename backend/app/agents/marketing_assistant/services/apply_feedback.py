import json
import re
import asyncio
from typing import Dict, Any, Optional, List
from langchain_core.language_models import BaseChatModel
from ....core.logging import get_logger
from ....core.langsmith_config import traced
from ....core.data_loader import get_brand_tones
from ....core.llm_factory import get_llm
from ....config.settings import settings
from .product_client import ProductClient
from ..prompts.apply_feedback_prompt import build_apply_feedback_prompt

logger = get_logger("apply_feedback")

_DEFAULT_BRAND_TONE = "친근하면서도 전문적이고 신뢰감 있는 어조"
_product_client = ProductClient()


def _parse_message(ai_message) -> dict:
    """AIMessage content에서 JSON 파싱 → {title, message}"""
    content = ai_message.content if hasattr(ai_message, "content") else str(ai_message)
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
    if match:
        content = match.group(1)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {"title": "", "message": content}


class ApplyFeedback:
    def __init__(self):
        self.llm = get_llm(model_name=settings.chatgpt_model_name, temperature=0.5)

    def _get_brand_tone(self, brand_name: str) -> str:
        """브랜드명에 맞는 톤 가이드 반환. 없으면 기본값 반환."""
        brand_tones = get_brand_tones().get("brand_ton_prompt", {})
        if brand_name in brand_tones:
            return brand_tones[brand_name]
        for key, value in brand_tones.items():
            if key.lower() == brand_name.lower():
                return value
        logger.warning("brand_tone_not_found", brand_name=brand_name)
        return _DEFAULT_BRAND_TONE

    def _extract_feedback(self, quality_check: Dict[str, Any]) -> str:
        """
        품질 검사 결과에서 피드백 텍스트 추출.

        - llm_judge 실패: llm_judge_scores.feedback (상세 피드백)
        - rule_check 실패: 위반 항목별 구체적 교정 지시
        - semantic_check 실패: 감지 문장 + 화장품 기능 범위 교체 지시
        """
        failed_stage = quality_check.get("failed_stage")

        if failed_stage == "llm_judge":
            llm_scores = quality_check.get("llm_judge_scores") or {}
            llm_feedback = llm_scores.get("feedback", "")
            if llm_feedback:
                return llm_feedback

        if failed_stage == "rule_check":
            return self._build_rule_check_feedback(quality_check)

        if failed_stage == "semantic_check":
            return self._build_semantic_check_feedback(quality_check)

        return quality_check.get("failure_reason", "")

    def _build_rule_check_feedback(self, quality_check: Dict[str, Any]) -> str:
        """
        rule_check 실패 항목을 교정 지시 형태로 변환.

        각 issue 유형에 따라 단순 사실 서술 대신
        "어떻게 고쳐야 하는지"를 포함한 지시문을 반환.
        """
        issues: List[str] = quality_check.get("rule_check_issues") or []
        if not issues:
            return quality_check.get("failure_reason", "")

        lines = ["다음 문제를 수정하여 메시지를 개선하세요:\n"]
        for issue in issues:
            if "금지 표현 감지" in issue:
                keyword = issue.split("'")[1] if "'" in issue else issue
                lines.append(
                    f"- '{keyword}' 표현을 삭제하고, 같은 의미를 전달하되 "
                    f"금지되지 않은 순화된 표현으로 교체하세요."
                )
            elif "너무 깁니다" in issue and "제목" in issue:
                lines.append(
                    f"- {issue} → 불필요한 수식어를 줄여 제목을 40자 이내로 압축하세요."
                )
            elif "너무 깁니다" in issue and "메시지" in issue:
                lines.append(
                    f"- {issue} → 중복 표현이나 부가 설명을 제거하여 본문을 350자 이내로 줄이세요."
                )
            elif "너무 짧습니다" in issue and "제목" in issue:
                lines.append(
                    f"- {issue} → 상품명이나 핵심 혜택을 추가하여 제목을 5자 이상으로 작성하세요."
                )
            elif "너무 짧습니다" in issue and "메시지" in issue:
                lines.append(
                    f"- {issue} → 타깃 고객의 고민과 상품 혜택을 구체적으로 서술하여 20자 이상으로 작성하세요."
                )
            elif "비어있습니다" in issue:
                lines.append(f"- {issue} → 해당 항목을 반드시 채워 주세요.")
            else:
                lines.append(f"- {issue}")

        return "\n".join(lines)

    def _build_semantic_check_feedback(self, quality_check: Dict[str, Any]) -> str:
        """
        semantic_check 실패 시 감지된 문장과 교체 방향을 포함한 지시 반환.

        triggered 결과에서 감지 문장을 추출하여
        화장품 기능 범위(보습·진정·탄력 등) 내 표현으로 교체하도록 안내.
        """
        triggered: List[Dict[str, Any]] = quality_check.get("semantic_check_results") or []

        # api_unavailable 오류인 경우
        if triggered and triggered[0].get("error") == "api_unavailable":
            return (
                "의미 유사도 검사를 수행할 수 없었습니다. "
                "의약품 효능·치료 효과를 암시하는 표현이 없는지 직접 검토하고, "
                "화장품 기능 범위(보습, 진정, 탄력, 미백 등) 내 표현만 사용하세요."
            )

        if not triggered:
            return quality_check.get("failure_reason", "")

        lines = [
            "아래 문장이 약사법·화장품법 위반 표현과 유사하여 감지되었습니다.",
            "해당 문장을 삭제하거나, 의학적 효능·치료 효과 암시 없이 화장품 기능 범위 내 표현으로 교체하세요.",
            "(허용 예시: 보습, 진정, 탄력, 미백, 윤기, 피부결 개선)\n",
        ]
        seen = set()
        for r in triggered[:3]:  # 상위 3개만 표시
            sentence = r.get("query_sentence", "")
            label = r.get("source", {}).get("label", "금지 표현 유사")
            score = r.get("score", 0.0)
            if sentence and sentence not in seen:
                seen.add(sentence)
                lines.append(f'- 감지 문장: "{sentence}"')
                lines.append(f"  → 위반 유형: {label} (유사도 {score:.2f})")

        lines.append("\n위 문장을 반드시 수정하세요.")
        return "\n".join(lines)

    @traced(name="apply_feedback", run_type="chain")
    async def apply_feedback(
        self,
        task: Dict[str, Any],
        llm: Optional[BaseChatModel] = None,
    ) -> Dict[str, Any]:
        """
        피드백을 반영하여 기존 메시지를 개선합니다.

        Args:
            task: generated_tasks의 단일 항목
                  (product_id, purpose, brand, message, quality_check 포함)
            llm:  사용할 LangChain LLM 인스턴스. None이면 기본 LLM 사용.

        Returns:
            개선된 message로 교체된 task dict.
            피드백 텍스트가 없으면 원본 그대로 반환.
        """
        quality_check = task.get("quality_check") or {}
        existing_message = task.get("message", {})
        product_id = task.get("product_id", "")
        brand_name = task.get("brand", "")

        feedback_text = self._extract_feedback(quality_check)
        if not feedback_text:
            logger.warning("no_feedback_available", product_id=product_id)
            return task

        brand_tone = self._get_brand_tone(brand_name)
        product_info = await _product_client.get_merged_product_info(product_id)

        prompt_messages = build_apply_feedback_prompt(
            existing_title=existing_message.get("title", ""),
            existing_message=existing_message.get("message", ""),
            feedback=feedback_text,
            brand_tone=brand_tone,
            product_info=product_info,
        )

        _llm = llm or self.llm
        result = await _llm.ainvoke(prompt_messages)
        improved = _parse_message(result)

        logger.info(
            "feedback_applied",
            product_id=product_id,
            failed_stage=quality_check.get("failed_stage"),
            issues=quality_check.get("rule_check_issues", []),
            before_title=existing_message.get("title", ""),
            before_snippet=existing_message.get("message", "")[:80],
            after_title=improved.get("title", ""),
            after_snippet=improved.get("message", "")[:80],
        )

        return {**task, "message": improved}

    async def apply_feedback_batch(
        self,
        tasks: List[Dict[str, Any]],
        failed_ids: set,
        llm: Optional[BaseChatModel] = None,
    ) -> List[Dict[str, Any]]:
        """
        실패한 태스크에만 피드백을 병렬 적용.

        Args:
            tasks:      전체 generated_tasks
            failed_ids: 품질 검사 실패 태스크의 product_id set
            llm:        사용할 LLM 인스턴스

        Returns:
            실패 태스크는 개선된 메시지로, 통과 태스크는 원본으로 구성된 리스트
        """
        async def improve_one(task: dict) -> dict:
            if task.get("product_id") in failed_ids:
                return await self.apply_feedback(task, llm)
            return task

        return list(await asyncio.gather(*[improve_one(t) for t in tasks]))


_applier: Optional[ApplyFeedback] = None


def get_applier() -> ApplyFeedback:
    global _applier
    if _applier is None:
        _applier = ApplyFeedback()
    return _applier
