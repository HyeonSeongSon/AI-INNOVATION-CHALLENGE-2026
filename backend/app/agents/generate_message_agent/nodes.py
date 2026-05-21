from datetime import datetime, timezone

from .state import GenerateMessageState
from ..shared.parser_and_router.parser_and_router_request import generate_message_router
from ...config.settings import settings
from ...core.llm_factory import get_llm
from ...core.logging import AgentLogger, get_logger
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from typing import Dict, Any, Union
from langgraph.types import Command
import json

_MAX_RETRIES = 2
_logger = get_logger("generate_message_agent")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    except Exception as e:
        _logger.debug("message_json_parse_failed", error=str(e))
    return {"title": "", "message": content}


async def init_node(state: GenerateMessageState, config: RunnableConfig) -> dict:
    logger = AgentLogger({**state, "logs": []}, node_name="init_node", agent_name="generate_message_agent")
    logger.info("agent_started", user_message="[init] 에이전트 시작")
    return {
        # GenerateMessageState 전용
        "generated_tasks": [],
        "failed_task_ids": [],
        "feedback_retry_count": 0,
        "tasks": None,
        "feedback_input": None,
        "persona_id": None,
        # BaseState 공통
        "status": "running",
        "error": None,
        "error_details": None,
        "logs": logger.get_user_logs(),
        "step": 0,
        "node_history": ["init"],
        "current_node": "init",
        "last_node": None,
        "is_interrupted": False,
        "decisions": {},
        "intermediate": {},
        "start_time": _now_iso(),
        "end_time": None,
        "duration_ms": None,
        # active_persona_id는 초기화하지 않음 — 턴 간 유지
    }


async def router_node(state: GenerateMessageState, config: RunnableConfig) -> Dict[str, Any]:
    logger = AgentLogger(state, node_name="router_node", agent_name="generate_message_agent")
    logger.info("router_started", user_message="[router] 라우팅 분석 시작")
    try:
        messages = state.get("messages")
        model = config.get("configurable", {}).get("model", settings.chatgpt_model_name)
        router_llm = get_llm(model, settings.parser_model_temperature)

        result = await generate_message_router(messages, router_llm)

        task_count = len(result.tasks) if result.tasks else 0
        logger.info("router_done", user_message=f"[router] 라우팅 결정 완료 (task_count={task_count})", task_count=task_count)

        update = {
            "decisions": {"next_node": result.next_node},
            "tasks": [t.model_dump() for t in result.tasks] if result.tasks else None,
            "feedback_input": result.feedback_input.model_dump() if result.feedback_input else None,
            "persona_id": result.persona_id,
            "logs": logger.get_user_logs(),
        }
        if result.persona_id:
            update["active_persona_id"] = result.persona_id
        return update
    except Exception as e:
        logger.error("router_error", user_message=f"[router] 오류: {e}", exc_info=True)
        return {
            "status": "failed",
            "error": "라우팅 중 오류가 발생했습니다.",
            "error_details": {"node": "router_node"},
            "decisions": {"next_node": "output_node"},
            "logs": logger.get_user_logs(),
        }


async def generate_message_node(state: GenerateMessageState, config: RunnableConfig) -> Union[Dict[str, Any], Command]:
    generator = config["configurable"]["services"].generator
    agent_logger = AgentLogger(state, node_name="generate_message_node")
    model = config.get("configurable", {}).get("model", settings.chatgpt_model_name)
    message_llm = get_llm(model, temperature=0.7)

    tasks = state.get("tasks") or []
    persona_id = state.get("persona_id") or state.get("active_persona_id")

    agent_logger.info(
        "generate_message_started",
        user_message=f"CRM 메시지 생성 시작 ({len(tasks)}개 태스크)",
        task_count=len(tasks),
    )

    try:
        persona_info = await generator.get_persona_info(persona_id) if persona_id else None
        tasks = await generator.get_product_info(tasks)
        tasks = await generator.get_brand_tone(tasks)
        tasks = await generator.get_crm_prompt(tasks, persona_info=persona_info)
        tasks = await generator.generate_crm_message(tasks, message_llm)
    except Exception as e:
        agent_logger.error("generate_message_error", user_message=f"[generate] 오류: {e}", exc_info=True)
        return Command(
            goto="output_node",
            update={
                "status": "failed",
                "error": "메시지 생성 중 오류가 발생했습니다.",
                "error_details": {"node": "generate_message_node"},
                "logs": agent_logger.get_user_logs(),
            },
        )

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
    services = config["configurable"]["services"]
    generator = services.generator
    checker = services.checker
    agent_logger = AgentLogger(state, node_name="quality_check_node")
    model = config.get("configurable", {}).get("model", settings.chatgpt_model_name)
    judge_llm = get_llm(model, temperature=0)

    generated_tasks = state.get("generated_tasks") or []
    persona_id = state.get("persona_id") or state.get("active_persona_id")
    try:
        persona_info = await generator.get_persona_info(persona_id) if persona_id else None
    except Exception as e:
        agent_logger.warning("persona_fetch_failed_fallback", user_message=f"[quality_check] 페르소나 조회 실패, 미사용으로 진행: {e}")
        persona_info = None

    agent_logger.info(
        "quality_check_started",
        user_message=f"품질 검사 시작 ({len(generated_tasks)}개)",
        task_count=len(generated_tasks),
    )

    checked_tasks = []
    failed_task_ids = []

    for task in generated_tasks:
        try:
            quality_check = await checker.check_quality(
                message=task["message"],
                product_id=task["product_id"],
                purpose=task["purpose"],
                llm=judge_llm,
                persona_info=persona_info,
            )
        except Exception as e:
            agent_logger.error(
                "quality_check_task_error",
                user_message=f"[quality_check] 태스크 검사 실패 (product_id={task['product_id']}): {e}",
                product_id=task["product_id"],
            )
            quality_check = {"passed": False, "failed_stage": "quality_check_error", "failure_reason": "품질 검사 중 오류가 발생했습니다."}
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


async def message_feedback_node(state: GenerateMessageState, config: RunnableConfig) -> Union[Dict[str, Any], Command]:
    agent_logger = AgentLogger(state, node_name="message_feedback_node")
    model = config.get("configurable", {}).get("model", settings.chatgpt_model_name)
    feedback_llm = get_llm(model, temperature=0.5)

    generated_tasks = state.get("generated_tasks") or []
    failed_task_ids = set(state.get("failed_task_ids") or [])
    retry_count = state.get("feedback_retry_count", 0)
    feedback_input = state.get("feedback_input")
    persona_id = state.get("persona_id") or state.get("active_persona_id")

    if retry_count >= _MAX_RETRIES:
        failed_ids_list = list(failed_task_ids)
        all_failed = len(failed_ids_list) == len(generated_tasks) and len(generated_tasks) > 0
        failure_status = "failed" if all_failed else "partial_failure"
        agent_logger.info(
            "feedback_max_retries_exceeded",
            user_message=f"품질 검사 최대 재시도 횟수 초과 (status={failure_status})",
            retry_count=retry_count,
        )
        return Command(
            goto="output_node",
            update={"status": failure_status, "failed_task_ids": failed_ids_list},
        )

    services = config["configurable"]["services"]
    applier = services.applier
    generator = services.generator
    try:
        persona_info = await generator.get_persona_info(persona_id) if persona_id else None
    except Exception as e:
        agent_logger.warning("persona_fetch_failed_fallback", user_message=f"[feedback] 페르소나 조회 실패, 미사용으로 진행: {e}")
        persona_info = None

    try:
        if feedback_input:
            agent_logger.info("user_feedback_started", user_message="사용자 피드백 적용 시작")
            raw = [{"product_id": feedback_input["product_id"], "purpose": feedback_input.get("purpose")}]
            enriched = await generator.get_product_info(raw)
            product_info = enriched[0].get("product_info", {}) if enriched else {}
            task = {
                "product_id": feedback_input["product_id"],
                "purpose": feedback_input.get("purpose"),
                "brand": product_info.get("brand", ""),
                "product_name": product_info.get("product_name", ""),
                "sub_tag": product_info.get("sub_tag", ""),
                "message": {"title": feedback_input["title"], "message": feedback_input["message"]},
                "quality_check": {
                    "failed_stage": "user_feedback",
                    "failure_reason": feedback_input["feedback"],
                },
            }
            improved = await applier.apply_feedback(task, llm=feedback_llm, product_info=product_info, persona_info=persona_info)
            updated_tasks = [improved]
        else:
            agent_logger.info(
                "auto_feedback_started",
                user_message=f"자동 피드백 적용 시작 ({len(failed_task_ids)}개)",
                failed_count=len(failed_task_ids),
            )
            updated_tasks = await applier.apply_feedback_batch(generated_tasks, failed_task_ids, llm=feedback_llm, persona_info=persona_info)
    except Exception as e:
        agent_logger.error("feedback_error", user_message=f"[feedback] 오류: {e}", exc_info=True)
        return Command(
            goto="output_node",
            update={
                "status": "failed",
                "error": "피드백 적용 중 오류가 발생했습니다.",
                "error_details": {"node": "message_feedback_node"},
                "logs": agent_logger.get_user_logs(),
            },
        )

    agent_logger.info("feedback_done", user_message="피드백 적용 완료")

    return {
        "generated_tasks": updated_tasks,
        "failed_task_ids": [],
        "feedback_retry_count": retry_count + 1,
        "logs": agent_logger.get_user_logs(),
    }


async def output_node(state: GenerateMessageState) -> Dict[str, Any]:
    logger = AgentLogger(state, node_name="output_node", agent_name="generate_message_agent")
    logger.info("output_started", user_message="[output] 결과 정리 시작")
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
        reason = (
            "상품 정보를 가져올 수 없어 처리가 중단됐습니다."
            if unrecoverable
            else f"품질 검사 {retry_count}회 재시도 후에도 기준을 충족하지 못했습니다."
        )
        all_failed = len(failed_task_ids) == len(generated_tasks) and len(generated_tasks) > 0
        status = "failed" if all_failed else "partial_failure"
        if status == "partial_failure":
            succeeded_content = _format_generated_tasks(
                [t for t in generated_tasks if t["product_id"] not in failed_task_ids]
            )
            content = f"{succeeded_content}\n\nCRM 메시지 일부 생성 실패: {reason}\n\n실패 목록:\n" + "\n".join(failed_details)
        else:
            content = f"CRM 메시지 생성 실패: {reason}\n\n실패 목록:\n" + "\n".join(failed_details)

    logger.info("output_done", user_message=f"[output] 완료 (status={status})", status=status)
    return {
        "messages": [AIMessage(content=content, name="generate_message_agent")],
        "status": status,
        "logs": logger.get_user_logs(),
    }
