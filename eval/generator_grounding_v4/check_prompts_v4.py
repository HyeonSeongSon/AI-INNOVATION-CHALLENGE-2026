"""
V4 프롬프트 정적 점검 — 7개 목적 × (fit 있음 · 없음) 프롬프트에 새 규칙 문구가 있고, 지운 문구 · 원문 페르소나가 없는지.

    python check_prompts_v4.py      # → result/check_prompts_v4.json
"""

import json
import sys

import v4_common as c

from app.agents.generate_message_agent.prompts import persona_fit as pf
from app.agents.generate_message_agent.prompts.purpose_prompt import PurPosePrompts

REQUIRED_ALL = [
    "상품정보의 서로 다른 문장에 있는 효능을 한 문장으로 합치지 않습니다",
    "효능을 특정 성분 · 도구 · 구성품에 붙일 때는",
    "usage_context · application_timing ·",
    "시간 · 횟수 · 양 · 비교(다른 제품 · 이전 대비) 표현은 제목과 본문 모두",
    "질문형 제목이어도 상품정보에 없는 시간 · 횟수 · 양 · 비교 표현은 쓰지 않습니다",
    "연결 안내의 공감 표현이나 상품 특징으로 묻기",
    "제품의 사용 시점 · 단계 · 사용량은 상품정보를 따릅니다",
]
FIT_ONLY = ["연결 안내에 없는 고민 · 피부 타입 · 상황은 꺼내지 않습니다", "## 페르소나-상품 연결 안내"]
NOFIT_ONLY = ["연결 안내가 없으므로 고객의 고민 · 피부 타입 · 상황을 꺼내거나 상품과 잇지 않습니다"]
REMOVED = [
    "페르소나의 사용 상황 · 루틴(시간대 · 장소 · 사용 순서)은 메시지를 여는 장면 묘사로만",
    "질문형 — 고객의 고민이나 상황을 직접 묻기",
    "페르소나의 구매 패턴(세트 구매, 대용량 선호)",
    "페르소나의 구매 결정 요인(리뷰, 추천 등)",
    "1. 피부 타입 + '말할 수 있는 효과'의 고민",
    "3. 세부 상황 (야근, 운동, 재택 등)",
    "연결 불가 (메시지에서 꺼내지 않는다)",
]
BY_PURPOSE = {
    "피부타입/고민 강조 소개": ["1. 연결 안내의 공감 표현(없으면 상품정보의 대상 고민 · 피부 타입) → Hook에 반영"],
    "라이프스타일/연령대 강조 소개": ["1. 라이프스타일 줄", "라이프스타일 장면에 이 제품이 맞는다 · 해결한다는 주장은 연결 안내 범위에서만"],
    "베스트셀러 제품 소개": ["연결 안내에 항목이 있을 때만 그중 하나를 본문 한 문장에 씁니다(리뷰 수·평점 다음)"],
    "프로모션/이벤트 소개": ["연결 안내에 항목이 있을 때만 그중 하나를 본문 한 문장에 씁니다(혜택 다음)"],
}
RAW_PERSONA_MARKERS = ["피부 고민:", "니즈:", "구매 기준:", "사용 방식:", "선호 포인트:"]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    msgs, _ = c.stored("v3r_N")
    fits = {r["item_id"]: pf.FitResult.from_dict(r) for r in c.load_jsonl(c.V3_RESULT / "dev" / "v3r" / "fit_cache.jsonl")}
    pp = PurPosePrompts()
    fails, n = [], 0
    for m in msgs.values():
        for purpose, builder in c.v3.PURPOSE_BUILDERS.items():
            for with_fit in (True, False):
                f = fits[m["item_id"]]
                pr = getattr(pp, builder)(m["product_snapshot"], "브랜드 톤", persona_info=pf.build_persona_view(m["persona_info"], purpose),
                                          fit_section=pf.build_fit_section(f) if with_fit else None)
                text = "\n".join(x.content for x in pr)
                need = REQUIRED_ALL + (FIT_ONLY if with_fit else NOFIT_ONLY) + BY_PURPOSE.get(purpose, [])
                miss = [s for s in need if s not in text]
                bad = [s for s in REMOVED if s in text]
                i = text.find("## 타겟 페르소나 정보")
                persona_part = text[i:text.find("\n\n", i)] if i >= 0 else ""
                raw = [s for s in RAW_PERSONA_MARKERS if s in persona_part]
                j = text.find("## 페르소나-상품 연결 안내")
                fit_part = text[j:text.find("# 출력 형식", j)] if j >= 0 else ""
                for nc in f.not_connectable:
                    if with_fit and nc in fit_part:
                        bad.append(f"연결 불가 니즈 노출: {nc}")
                n += 1
                if miss or bad or raw:
                    fails.append({"item": m["item_id"], "purpose": purpose, "fit": with_fit, "missing": miss, "removed_found": bad, "raw": raw})
    out = {"prompts": n, "fails": len(fails), "examples": fails[:10]}
    (c.RESULT / "check_prompts_v4.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"프롬프트 {n}개 점검 · 실패 {len(fails)}")
    for x in fails[:5]:
        print(x)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
