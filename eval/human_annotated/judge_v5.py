"""
judge_v5 — judge_v4 의 core_need_met 캘리브레이션 버전.

judge_v4 결과(κ 0.246, 사람-사람 0.616~0.672)에서 관측된 실패:
    core_need_met 이 186/197(94%)에 True, 5점이 79.3% — 변별력 상실.
    상향 오분류 17건 / 하향 6건. 이전 채점기와 반대 방향으로 과관대.

원인 (dev 분할에서 확인):
    v4 프롬프트의 "일부만 해결해도 핵심에 해당하면 true" 가
    판정 기준을 "카테고리의 기본 기능을 수행하는가" 로 느슨하게 만들었다.
    바디워시가 '세정'을 하니 '운동 후 땀 냄새 제거'를 해결한다고 판정하는 식.
    근거 부재를 evidence 에 스스로 적어놓고 True 를 준 건이 15건 있었다.

v4 대비 변경 (3가지):
    1. core_needs 를 항목별로 열거하게 한다 — addressed / unaddressed 를 불리언보다 먼저
    2. addressed 가 비면 core_need_met 을 코드가 False 로 강제한다 (자기모순 차단)
    3. 프롬프트에서 관대 문구를 제거하고, 카테고리 기본 기능만으로는 부족함을 명시.
       dev 분할에서 뽑은 예시 2개를 few-shot 으로 넣는다.

평가 규율:
    실패 원인 진단은 198건 전체를 보고 했으므로 held-out 이 완전히 깨끗하지는 않다.
    다만 위 변경은 특정 항목에 맞춘 것이 아니라 일반 규칙이며,
    few-shot 예시는 dev 분할에서만 가져왔다.
    dev / held-out 수치를 모두 보고하되 **held-out 을 주 수치로 삼는다.**

사용법:
    python judge_v5.py --concurrency 5
"""

import asyncio
import argparse
import json
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

# judge_v4 의 데이터 로딩·프롬프트 조립·게이트를 그대로 재사용한다
from judge_v4 import (
    Verdict,
    build_targets,
    format_product,
    load_jsonl,
    load_product_index,
    load_tag_normalizer,
)

sys.stdout.reconfigure(encoding="utf-8")

from backend.app.config.settings import settings
from backend.app.core.llm_factory import get_llm

BASE_DIR = Path(__file__).parent
RESULT_DIR = BASE_DIR / "result"
SPEC_FILE = RESULT_DIR / "persona_specs.json"
OUTPUT_FILE = RESULT_DIR / "judged_v5.jsonl"

DEFAULT_CONCURRENCY = 5


# ─────────────────────────────────────────────
# 스키마 — 열거를 불리언보다 먼저
# ─────────────────────────────────────────────

class AxisJudgementV5(BaseModel):
    core_needs_addressed: list[str] = Field(
        description="상품 정보에서 근거를 인용할 수 있는 core_needs 항목만 그대로 옮긴다."
    )
    core_needs_unaddressed: list[str] = Field(
        description="근거를 찾지 못한 core_needs 항목."
    )
    core_need_evidence: str = Field(description="addressed 각 항목의 근거로 인용한 상품 정보.")
    core_need_met: bool = Field(description="핵심 고민을 정면으로 해결하는가")

    preference_evidence: str = Field(description="선호 판정 근거. 상품 정보를 인용한다.")
    preference: Verdict = Field(description="선호 속성 일치 여부")

    condition_evidence: str = Field(description="본인 조건 판정 근거. 상품 정보를 인용한다.")
    condition: Verdict = Field(description="본인 조건 적합 여부")

    avoid_evidence: str = Field(description="회피 조건 위반 근거. 위반이 아니면 '해당 없음'.")
    avoid_violated: bool = Field(description="명시적 회피 조건을 실제로 위반하는가")


JUDGE_SYSTEM_PROMPT_V5 = """당신은 상품이 페르소나의 요구를 충족하는지 대조하는 도구입니다.
점수를 매기지 않습니다. 아래를 판정하고, 판정마다 근거를 먼저 씁니다.

[근거 우선]
evidence 에는 상품 정보에서 근거가 된 값을 인용합니다.
인용할 값이 없으면 "근거 없음"이라고 적고, 그 항목은 충족되지 않은 것으로 처리합니다.
근거가 없다고 적어놓고 충족했다고 판정하는 것은 모순입니다. 하지 마세요.

[1] core_needs 열거와 core_need_met

먼저 요구 명세의 core_needs 를 항목별로 나눕니다.
  core_needs_addressed   - 상품 정보에서 **직접 대응하는 값을 인용할 수 있는** 항목
  core_needs_unaddressed - 인용할 근거가 없는 항목
두 리스트의 합은 core_needs 전체와 같아야 합니다.

**판정 기준은 '카테고리의 기본 기능'이 아니라 '이 페르소나의 구체적 고민'입니다.**
상품이 그 카테고리가 원래 하는 일을 한다는 것만으로는 충족이 아닙니다.
페르소나가 적은 구체적 고민에 상품이 정면으로 대응할 때만 addressed 에 넣습니다.

  예시 1 — addressed 아님
    core_needs: ["운동 후 땀 냄새 제거", "땀과 피지를 깔끔하게 씻어주는 바디워시"]
    상품: 바디워시. function "바디 클렌징, 향기 부여", "부드러운 세정, 촉촉한 거품"
    → 바디워시가 세정을 하는 것은 카테고리의 기본 기능입니다.
      '땀 냄새 제거'나 '피지 세정'에 대응하는 값이 없습니다.
      unaddressed 로 분류하고 core_need_met = false.

  예시 2 — addressed 아님
    core_needs: ["온 가족이 쓸 수 있는 제품 필요", "순하고 무난한 데일리 샴푸"]
    상품: 샴푸. function "딥클렌징, 두피 각질 케어", target_user "지성 두피"
    → 특정 두피 타입을 겨냥한 기능성 제품이라 '온 가족용 순한 데일리'와 어긋납니다.
      core_need_met = false.

  예시 3 — addressed 맞음
    core_needs: ["세안 후 당김", "자극 없이 피부 장벽을 강화해주는 고보습 크림"]
    상품: 크림. concern "속건조, 당김", function "피부 장벽 강화, 고보습",
          suitable_for "민감성"
    → 고민과 기대 효과에 직접 대응하는 값이 있습니다. core_need_met = true.

core_need_met 은 addressed 가 비어 있지 않고, 그중 페르소나의 핵심 고민에
해당하는 항목이 실제로 포함될 때만 true 입니다.

[2] preference (MATCH / UNKNOWN / CONFLICT)
    요구 명세의 preferences 와 상품 속성을 대조합니다.
    MATCH    - 하나 이상 일치하는 값이 상품 정보에 있음
    UNKNOWN  - 상품 정보에 대조할 값이 없음 (해당 항목이 비어있는 경우 포함)
    CONFLICT - 상품 정보가 선호와 명백히 반대되는 값을 가짐
    ※ 상품 카테고리상 존재할 수 없는 속성은 CONFLICT 가 아니라 UNKNOWN 입니다.
      (예: 식기·가전에는 성분·제형이 없습니다)

[3] condition (MATCH / UNKNOWN / CONFLICT)
    요구 명세의 self_conditions 와 상품의 적합 대상을 대조합니다. 기준은 [2]와 같습니다.

[4] avoid_violated (true/false)
    요구 명세의 avoid 항목을 상품이 실제로 위반하는가.
    **상품 정보에서 위반 근거를 인용하지 못하면 반드시 false 입니다.**
    avoid 가 비어 있으면 항상 false 입니다."""


def build_prompt_v5(spec: dict, product: dict) -> str:
    return (
        "[페르소나 요구 명세]\n"
        f"  core_needs      : {spec['core_needs']}\n"
        f"  preferences     : {spec['preferences']}\n"
        f"  self_conditions : {spec['self_conditions']}\n"
        f"  avoid           : {spec['avoid']}\n"
        "\n[상품 정보]\n"
        f"{format_product(product)}"
    )


# ─────────────────────────────────────────────
# 점수 산출 — 코드
# ─────────────────────────────────────────────

def to_score_v5(j: AxisJudgementV5, category_matched: bool) -> tuple[int, str | None, bool]:
    """(점수, gate_reason, forced) 반환.

    forced: addressed 가 비었는데 core_need_met=True 로 온 자기모순을 코드가 바로잡았는지.
    """
    if not category_matched:
        return 1, "category_mismatch", False
    if j.avoid_violated:
        return 1, "avoid_violated", False

    met = j.core_need_met
    forced = False
    if met and not j.core_needs_addressed:
        met, forced = False, True   # 근거 없이 충족 판정한 경우 코드가 차단

    if not met:
        return 2, None, forced
    return 3 + (j.preference == "MATCH") + (j.condition == "MATCH"), None, forced


# ─────────────────────────────────────────────
# 채점
# ─────────────────────────────────────────────

async def judge_single_v5(target, specs, products, normalize, llm, semaphore, done_ref, total):
    from langchain_core.messages import SystemMessage, HumanMessage

    persona_id = target["persona_id"]
    product_id = target["product_id"]
    spec_item = specs.get(persona_id)
    product = products.get(product_id)
    if spec_item is None or product is None:
        done_ref[0] += 1
        return None

    spec = spec_item["spec"]
    category_matched = normalize(target["product_tag"]) == normalize(product.get("서브태그"))
    base = {
        "persona_id": persona_id,
        "product_tag": target["product_tag"],
        "product_id": product_id,
        "rank": target["rank"],
        "product_subtag": product.get("서브태그"),
        "category_matched": category_matched,
    }

    if not category_matched:
        done_ref[0] += 1
        print(f"[{done_ref[0]}/{total}] {persona_id} {product_id} → 1점 (category_mismatch)")
        return {**base, "judgement": None, "score": 1,
                "gate_reason": "category_mismatch", "forced_false": False}

    async with semaphore:
        try:
            structured_llm = llm.with_structured_output(AxisJudgementV5)
            messages = [
                SystemMessage(content=JUDGE_SYSTEM_PROMPT_V5),
                HumanMessage(content=build_prompt_v5(spec, product)),
            ]
            j: AxisJudgementV5 = await structured_llm.ainvoke(messages)
            score, gate_reason, forced = to_score_v5(j, category_matched)

            done_ref[0] += 1
            mark = " [코드가 False로 정정]" if forced else ""
            print(
                f"[{done_ref[0]}/{total}] {persona_id} {product_id} → {score}점 "
                f"(addr={len(j.core_needs_addressed)}/{len(j.core_needs_addressed) + len(j.core_needs_unaddressed)} "
                f"need={j.core_need_met} pref={j.preference} cond={j.condition}){mark}"
            )
            return {**base, "judgement": j.model_dump(), "score": score,
                    "gate_reason": gate_reason, "forced_false": forced}
        except Exception as e:
            done_ref[0] += 1
            print(f"[{done_ref[0]}/{total}] {persona_id} {product_id} 실패 — {type(e).__name__}")
            return None


def load_done_keys() -> set:
    if not OUTPUT_FILE.exists():
        return set()
    return {
        (r["persona_id"], r["product_tag"], r["product_id"], r["rank"])
        for r in load_jsonl(OUTPUT_FILE)
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.force and OUTPUT_FILE.exists():
        OUTPUT_FILE.unlink()

    with open(SPEC_FILE, encoding="utf-8") as f:
        specs = json.load(f)
    products = load_product_index()
    normalize = load_tag_normalizer()

    targets = build_targets()
    done = load_done_keys()
    todo = [
        t for t in targets
        if (t["persona_id"], t["product_tag"], t["product_id"], t["rank"]) not in done
    ]

    print(f"대상 {len(targets)}건 | 완료 {len(done)}건 | 채점 {len(todo)}건")
    print(f"모델: {settings.chatgpt_model_name}  동시성: {args.concurrency}")
    print("─" * 70)
    if not todo:
        print("채점할 항목이 없습니다.")
        return

    llm = get_llm(settings.chatgpt_model_name, temperature=0)
    semaphore = asyncio.Semaphore(args.concurrency)
    done_ref = [0]
    results = await asyncio.gather(
        *(judge_single_v5(t, specs, products, normalize, llm, semaphore, done_ref, len(todo))
          for t in todo)
    )
    ok = [r for r in results if r is not None]

    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        for r in ok:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    forced = sum(r["forced_false"] for r in ok)
    print("─" * 70)
    print(f"저장: {OUTPUT_FILE.name} (신규 {len(ok)}건 / 누적 {len(done) + len(ok)}건)")
    print(f"코드가 자기모순을 정정한 건: {forced}건")


if __name__ == "__main__":
    asyncio.run(main())
