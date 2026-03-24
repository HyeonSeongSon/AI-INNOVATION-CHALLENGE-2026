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
        - rule / semantic 실패: failure_reason (규칙 위반 사유)
        """
        failed_stage = quality_check.get("failed_stage")

        if failed_stage == "llm_judge":
            llm_scores = quality_check.get("llm_judge_scores") or {}
            llm_feedback = llm_scores.get("feedback", "")
            if llm_feedback:
                return llm_feedback

        return quality_check.get("failure_reason", "")

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
        )

        return {**task, "message": improved}

    async def apply_feedback_batch(
        self,
        tasks: List[Dict[str, Any]],
        failed_ids: set,
        llm: Optional[BaseChatModel] = None,
    ) -> List[Dict[str, Any]]:
        """
        실패한 태스크에만 피드백을 병렬 적용합니다.

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
