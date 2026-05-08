from .state import GenerateMessageState
from ..shared.parser_and_router.parser_and_router_request import generate_message_router
from ...config.settings import settings
from ...core.llm_factory import get_llm
from ...core.logging import AgentLogger
from .services.generate_crm_message import CrmMessageGenerator
from .services.quality_check import QualityChecker
from .services.apply_feedback import get_applier
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from typing import Dict, Any
import json

_generator = CrmMessageGenerator()
_checker = QualityChecker()


def _format_generated_tasks(tasks) -> str:
    lines = ["생성된 CRM 메시지:"]
    for t in tasks:
        msg = t.get("message", {})
        lines.append(
            f"\n[상품ID: {t.get('product_id')}] [{t.get('brand')}] {t.get('product_name')}"
            f"\n목적: {t.get('purpose', '')}"
            f"\n제목: {msg.get('title', '')}"
            f"\n메시지: {msg.get('message', '')}"
        )
    return "\n".join(lines)


def _parse_message(raw) -> Dict[str, Any]:
    content = raw.content if hasattr(raw, "content") else str(raw)
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict) and "title" in parsed:
            return parsed
    except Exception:
        pass
    return {"title": "", "message": content}


async def init_node(state: GenerateMessageState, config: RunnableConfig) -> dict:
    return {
        "generated_tasks": [],
        "failed_task_ids": [],
        "feedback_retry_count": 0,
        "status": "running",
        "error": None,
        "logs": [],
    }


async def router_node(state: GenerateMessageState, config: RunnableConfig) -> Dict[str, Any]:
    messages = state.get("messages")
    model = config.get("configurable", {}).get("model", settings.chatgpt_model_name)
    router_llm = get_llm(model, settings.parser_model_temperature)

    result = await generate_message_router(messages, router_llm)

    return {
        "decisions": {"next_node": result.next_node},
        "intermediate": {
            "tasks": [t.model_dump() for t in result.tasks] if result.tasks else None,
            "feedback_input": result.feedback_input.model_dump() if result.feedback_input else None,
        },
    }


async def generate_message_node(state: GenerateMessageState, config: RunnableConfig) -> Dict[str, Any]:
    agent_logger = AgentLogger(state, node_name="generate_message_node")
    model = config.get("configurable", {}).get("model", settings.chatgpt_model_name)
    message_llm = get_llm(model, temperature=0.7)

    tasks = state.get("intermediate", {}).get("tasks") or []

    agent_logger.info(
        "generate_message_started",
        user_message=f"CRM 메시지 생성 시작 ({len(tasks)}개 태스크)",
        task_count=len(tasks),
    )

    tasks = await _generator.get_product_info(tasks)
    tasks = await _generator.get_brand_tone(tasks)
    tasks = await _generator.get_crm_prompt(tasks)
    tasks = await _generator.generate_crm_message(tasks, message_llm)

    generated_tasks = [
        {
            "product_id": t["product_id"],
            "product_name": t.get("product_info", {}).get("product_name", ""),
            "brand": t.get("product_info", {}).get("brand", ""),
            "sub_tag": t.get("product_info", {}).get("sub_tag", ""),
            "purpose": t["purpose"],
            "message": _parse_message(t["message"]),
        }
        for t in tasks
    ]

    agent_logger.info(
        "generate_message_done",
        user_message=f"CRM 메시지 생성 완료 ({len(generated_tasks)}개)",
        task_count=len(generated_tasks),
    )

    return {
        "generated_tasks": generated_tasks,
        "logs": agent_logger.get_user_logs(),
    }


async def quality_check_node(state: GenerateMessageState, config: RunnableConfig) -> Dict[str, Any]:
    agent_logger = AgentLogger(state, node_name="quality_check_node")
    model = config.get("configurable", {}).get("model", settings.chatgpt_model_name)
    judge_llm = get_llm(model, temperature=0)

    generated_tasks = state.get("generated_tasks") or []

    agent_logger.info(
        "quality_check_started",
        user_message=f"품질 검사 시작 ({len(generated_tasks)}개)",
        task_count=len(generated_tasks),
    )

    checked_tasks = []
    failed_task_ids = []

    for task in generated_tasks:
        quality_check = await _checker.check_quality(
            message=task["message"],
            product_id=task["product_id"],
            purpose=task["purpose"],
            llm=judge_llm,
        )
        checked_tasks.append({**task, "quality_check": quality_check})
        if not quality_check["passed"]:
            failed_task_ids.append(task["product_id"])

    agent_logger.info(
        "quality_check_done",
        user_message=f"품질 검사 완료 (실패: {len(failed_task_ids)}개)",
        failed_count=len(failed_task_ids),
    )

    return {
        "generated_tasks": checked_tasks,
        "failed_task_ids": failed_task_ids,
        "logs": agent_logger.get_user_logs(),
    }


async def message_feedback_node(state: GenerateMessageState, config: RunnableConfig) -> Dict[str, Any]:
    agent_logger = AgentLogger(state, node_name="message_feedback_node")
    model = config.get("configurable", {}).get("model", settings.chatgpt_model_name)
    feedback_llm = get_llm(model, temperature=0.5)

    generated_tasks = state.get("generated_tasks") or []
    failed_task_ids = set(state.get("failed_task_ids") or [])
    retry_count = state.get("feedback_retry_count", 0)
    feedback_input = (state.get("intermediate") or {}).get("feedback_input")

    applier = get_applier()

    if feedback_input:
        agent_logger.info("user_feedback_started", user_message="사용자 피드백 적용 시작")
        task = {
            "product_id": feedback_input["product_id"],
            "purpose": feedback_input.get("purpose"),
            "brand": "",
            "message": {"title": feedback_input["title"], "message": feedback_input["message"]},
            "quality_check": {
                "failed_stage": "user_feedback",
                "failure_reason": feedback_input["feedback"],
            },
        }
        improved = await applier.apply_feedback(task, llm=feedback_llm)
        updated_tasks = [improved]
    else:
        agent_logger.info(
            "auto_feedback_started",
            user_message=f"자동 피드백 적용 시작 ({len(failed_task_ids)}개)",
            failed_count=len(failed_task_ids),
        )
        updated_tasks = await applier.apply_feedback_batch(generated_tasks, failed_task_ids, llm=feedback_llm)

    agent_logger.info("feedback_done", user_message="피드백 적용 완료")

    return {
        "generated_tasks": updated_tasks,
        "failed_task_ids": [],
        "feedback_retry_count": retry_count + 1,
        "logs": agent_logger.get_user_logs(),
    }


async def output_node(state: GenerateMessageState) -> Dict[str, Any]:
    generated_tasks = state.get("generated_tasks") or []
    failed_task_ids = set(state.get("failed_task_ids") or [])

    if not failed_task_ids:
        content = _format_generated_tasks(generated_tasks)
        status = "completed"
    else:
        failed_details = [
            f"- [상품ID: {t['product_id']}] {t.get('product_name', '')}: "
            f"{t.get('quality_check', {}).get('failure_reason', '알 수 없는 오류')}"
            for t in generated_tasks
            if t["product_id"] in failed_task_ids
        ]
        retry_count = state.get("feedback_retry_count", 0)
        unrecoverable = any(
            t.get("quality_check", {}).get("failed_stage") == "product_fetch"
            for t in generated_tasks
            if t["product_id"] in failed_task_ids
        )
        reason = "상품 정보를 가져올 수 없어 처리가 중단됐습니다." if unrecoverable else f"품질 검사 {retry_count}회 재시도 후에도 기준을 충족하지 못했습니다."
        content = f"CRM 메시지 생성 실패: {reason}\n\n실패 목록:\n" + "\n".join(failed_details)
        status = "failed"

    return {
        "messages": [AIMessage(content=content)],
        "status": status,
    }
