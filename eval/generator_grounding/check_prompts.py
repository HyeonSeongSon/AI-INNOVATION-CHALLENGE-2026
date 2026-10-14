"""
수정 후 프롬프트 점검 (4단계) — after 생성 전에 반드시 통과해야 한다(regenerate.py 가 기록을 확인).

    python check_prompts.py

목적 7개 × 보류 표본 스냅숏(목적마다 전부)으로 생성기 경로(get_brand_tone → get_crm_prompt)를 그려 확인한다.
- 제외 필드(GENERATION_EXCLUDED_FIELDS)의 키와 product_created_at 값이 프롬프트에 없다.
- 지운 지시문 문장이 없다(문장 단위).
- 새 규칙(사실 근거 규칙 · 브랜드 가이드 전체 규칙 · 필드 안내 · 인기 문턱 값)이 있다.
결과: result/check_prompts.json (passed · purpose_prompt 해시 · 실패 목록)
"""

import asyncio
import json
import sys
from datetime import datetime, timezone

import gg_common as gg

from app.agents.generate_message_agent.prompts.product_fields import (  # noqa: E402
    GENERATION_EXCLUDED_FIELDS,
    POPULARITY_MIN_REVIEWS,
)
from app.agents.generate_message_agent.services.generate_crm_message import CrmMessageGenerator  # noqa: E402
import build_originals as bo  # noqa: E402

OUT = gg.RESULT / "check_prompts.json"

# 수정 전 프롬프트에서 지운 지시문 — 남아 있으면 실패
REMOVED = [
    "상품정보에 출시일이 있으면 반드시 포함하세요",
    "제품과 연관된 키워드 1-2개 반드시 포함",
    "저자극 테스트 결과 확인",
    "이 제품만의 차별점 1가지를 중심에 두고",
    "이 제품이 다른 것과 다른 핵심 이유",
    "기존 제품과 무엇이 다른가",
    "기존 제품 대비 차별점 또는 새로운 혁신 포인트가 메시지의 중심",
    "기존과 다른 핵심 차별점",
    "무엇이 달라졌는지",
    "많은 사람이 선택했고, 이유가 있다",
    "사회적 증거(많은 사람의 선택)",
    "많은 사람이 선택한 구체적 이유",
    "베스트셀러 지위를 전달하는 시작",
    "\"꾸준히 사랑받는\", \"오랫동안 선택되는\" 등의 표현 사용",
    "베스트셀러 유형별 강조 방향",
    "3년째 사랑받는",
    "SNS에서 화제",
    "품절 대란",
    "한 번 쓰면 계속 찾게 되는",
    "이렇게 많이 찾는",
    "페르소나와 유사한 타겟의 선택임을 암시",
    "\"임상 결과 확인하기\", \"제품 상세 보기\")",
    "출근 준비 30분 중",
    "검증된 정보만 사용",
    "검증된 신제품 정보만 사용",
]
# 있어야 하는 새 규칙
REQUIRED = [
    "사실 근거 규칙 (모든 목적 공통",
    "사실 주장 제한(가장 우선)",
    "상품정보 필드 안내",
    f"{POPULARITY_MIN_REVIEWS}건 미만",
    "상품 특성(제형·마무리감·효능·용도)은 페르소나에 맞추려고 바꾸지 마세요",
    "확인을 권하는 대상(시험 결과·인증·수상 등)은 상품정보에 있는 것만",
]


async def render(items: list[dict]) -> list[tuple[str, str, str]]:
    gen = CrmMessageGenerator()
    out = []
    for purpose in bo.PURPOSES:
        tasks = [{"product_id": it["product_id"], "purpose": purpose, "product_info": it["product_snapshot"],
                  "_item": it["item_id"], "_persona": it["persona_info"]} for it in items]
        tasks = await gen.get_brand_tone(tasks)
        for t in tasks:
            [rendered] = await gen.get_crm_prompt([t], persona_info=t["_persona"])
            text = "\n".join(m.content for m in rendered["prompt"])
            out.append((purpose, t["_item"], text, t["product_info"]))
    return out


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    items = gg.load_inputs("holdout")
    rendered = asyncio.run(render(items))
    fails: list[str] = []
    for purpose, item, text, snap in rendered:
        flat = " ".join(text.split())
        for k in GENERATION_EXCLUDED_FIELDS:
            if f"'{k}'" in text:
                fails.append(f"{purpose}/{item}: 제외 필드 키 {k}")
        created = snap.get("product_created_at")
        if created and str(created) in text:
            fails.append(f"{purpose}/{item}: product_created_at 값")
        for s in REMOVED:
            if " ".join(s.split()) in flat:
                fails.append(f"{purpose}/{item}: 지운 지시문 남음 — {s}")
        for s in REQUIRED:
            if " ".join(s.split()) not in flat:
                fails.append(f"{purpose}/{item}: 새 규칙 없음 — {s}")
    n_expected = len(items) * len(bo.PURPOSES)
    if len(rendered) != n_expected:
        fails.append(f"그린 프롬프트 {len(rendered)}개 ≠ 기대 {n_expected}개(브랜드 톤 누락)")
    rec = {"checked_at": datetime.now(timezone.utc).isoformat(), "passed": not fails,
           "purpose_prompt": gg.sha256(gg.PURPOSE_PROMPT), "product_fields": gg.sha256(gg.PRODUCT_FIELDS),
           "n_prompts": len(rendered), "n_fail": len(fails), "fails": sorted(set(fails))[:200]}
    OUT.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"프롬프트 {len(rendered)}개 점검 · 실패 {len(fails)}건 → {OUT}")
    for f in sorted(set(f.split(": ", 1)[1] for f in fails))[:20]:
        print("  ", f)
    if fails:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
