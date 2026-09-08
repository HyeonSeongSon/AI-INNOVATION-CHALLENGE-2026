"""
judge_v4 — 카테고리 게이트 + 축 판정 + 코드 점수 산출.

설계 요지:
    LLM에게 점수를 매기게 하지 않는다. 판정만 시키고 점수는 to_score()가 계산한다.
    등급 경계 캘리브레이션 편차가 원천 제거되고, 등급 규칙을 바꿔도
    저장된 판정에서 LLM 재호출 없이 재계산할 수 있다.

    [1] 카테고리 게이트   코드   결정적, LLM 호출 없음
    [2] PersonaSpec       extract_persona_spec.py 가 만든 캐시를 그대로 사용
    [3] 축 판정           LLM, 근거 우선 + 4축
         └ 점수 산출      코드

기존 채점기 대비 바뀐 점:
    · 순위·RRF를 프롬프트에 넣지 않는다 (앵커링 제거)
    · 5건 묶음이 아니라 1건씩 독립 호출한다 (상대화 제거)
    · 근거 필드를 판정보다 먼저 생성한다 (사후 합리화 제거)
    · 등급표를 LLM에게 주지 않는다
    · 카테고리별로 없는 필드는 UNKNOWN 으로 흡수해 감점하지 않는다

사용법:
    python judge_v4.py
    python judge_v4.py --concurrency 5
    python judge_v4.py --force        # 캐시 무시하고 전건 재채점
"""

import asyncio
import argparse
import json
import sys
from pathlib import Path
from typing import Literal

_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "backend"))

import os
from dotenv import load_dotenv
load_dotenv(_ROOT / "backend" / "app" / ".env")

from pydantic import BaseModel, Field
from backend.app.config.settings import settings
from backend.app.core.llm_factory import get_llm

os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
RESULT_DIR = BASE_DIR / "result"

HUMAN_FILES = [
    RESULT_DIR / "annotated_results_1.jsonl",
    RESULT_DIR / "annotated_results_2.jsonl",
    RESULT_DIR / "annotated_results_3.jsonl",
]
SPEC_FILE = RESULT_DIR / "persona_specs.json"
TAG_MAP_FILE = BASE_DIR / "tag_normalize.json"
OUTPUT_FILE = RESULT_DIR / "judged_v4.jsonl"

DEFAULT_CONCURRENCY = 5

# annotate_top5.py 와 동일 — 사람이 보지 않은 필드는 LLM에게도 주지 않는다
STRUCTURED_EXCLUDE = {"_original_semantic"}


# ─────────────────────────────────────────────
# 스키마
# ─────────────────────────────────────────────

Verdict = Literal["MATCH", "UNKNOWN", "CONFLICT"]


class AxisJudgement(BaseModel):
    core_need_evidence: str = Field(description="핵심 니즈 판정 근거. 상품 정보를 인용한다.")
    core_need_met: bool = Field(description="페르소나의 핵심 니즈/고민을 이 상품이 해결하는가")

    preference_evidence: str = Field(description="선호 판정 근거. 상품 정보를 인용한다.")
    preference: Verdict = Field(description="선호 속성 일치 여부")

    condition_evidence: str = Field(description="본인 조건 판정 근거. 상품 정보를 인용한다.")
    condition: Verdict = Field(description="본인 조건 적합 여부")

    avoid_evidence: str = Field(description="회피 조건 위반 근거. 위반이 아니면 '해당 없음'.")
    avoid_violated: bool = Field(description="명시적 회피 조건을 실제로 위반하는가")


JUDGE_SYSTEM_PROMPT = """당신은 상품이 페르소나의 요구를 충족하는지 대조하는 도구입니다.
점수를 매기지 않습니다. 아래 네 가지를 각각 판정하고, 판정마다 근거를 먼저 씁니다.

[근거 우선]
각 판정의 evidence에는 상품 정보에서 근거가 된 값을 인용합니다.
인용할 값이 없으면 "근거 없음"이라고 적습니다. 추측으로 채우지 마세요.

[1] core_need_met (true/false)
    요구 명세의 core_needs 를 이 상품이 해결하는가.
    상품의 기능·대상 고민에 대응하는 값이 있으면 true.
    일부만 해결해도 핵심에 해당하면 true. 전혀 대응하지 않으면 false.

[2] preference (MATCH / UNKNOWN / CONFLICT)
    요구 명세의 preferences 와 상품 속성을 대조합니다.
    MATCH    - 하나 이상 일치하는 값이 상품 정보에 있음
    UNKNOWN  - 상품 정보에 대조할 값이 없음 (해당 항목이 아예 비어있는 경우 포함)
    CONFLICT - 상품 정보가 선호와 명백히 반대되는 값을 가짐
    ※ 상품 카테고리상 존재할 수 없는 속성은 CONFLICT가 아니라 UNKNOWN 입니다.
      (예: 식기·가전에는 성분·제형이 없습니다)

[3] condition (MATCH / UNKNOWN / CONFLICT)
    요구 명세의 self_conditions(피부·두피·모발 타입, 사용 환경 등)와
    상품의 적합 대상을 대조합니다. 판정 기준은 [2]와 같습니다.

[4] avoid_violated (true/false)
    요구 명세의 avoid 에 적힌 항목을 상품이 실제로 위반하는가.
    **상품 정보에서 위반 근거를 인용하지 못하면 반드시 false 입니다.**
    avoid 가 비어 있으면 항상 false 입니다.
    추론으로 위반을 판정하지 마세요."""


# ─────────────────────────────────────────────
# 데이터 로드
# ─────────────────────────────────────────────

def load_jsonl(path: Path) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def load_product_index() -> dict[str, dict]:
    index: dict[str, dict] = {}
    for path in sorted(DATA_DIR.glob("*.jsonl")):
        for rec in load_jsonl(path):
            pid = rec.get("product_id")
            if pid:
                index[pid] = rec
    return index


def load_tag_normalizer():
    with open(TAG_MAP_FILE, encoding="utf-8") as f:
        mapping = json.load(f)["persona_to_product"]

    def normalize(tag: str | None) -> str:
        t = (tag or "").strip()
        return mapping.get(t, t)

    return normalize


def build_targets() -> list[dict]:
    """사람 3인이 모두 채점한 항목만 대상으로 삼는다."""
    key_fn = lambda r: (r["persona_id"], r["product_tag"], r["product_id"], r["rank"])
    sets = [{key_fn(r): r for r in load_jsonl(p)} for p in HUMAN_FILES]
    common = set(sets[0]) & set(sets[1]) & set(sets[2])

    targets = []
    for key in sorted(common):
        persona_id, product_tag, product_id, rank = key
        targets.append({
            "persona_id": persona_id,
            "product_tag": product_tag,
            "product_id": product_id,
            "rank": rank,  # 기록만 한다. 프롬프트에는 넣지 않는다.
        })
    return targets


# ─────────────────────────────────────────────
# 프롬프트
# ─────────────────────────────────────────────

def format_product(product: dict) -> str:
    """사람 주석 화면(annotate_top5.py print_product)과 같은 범위를 제시한다.
    순위와 RRF 점수는 넣지 않는다."""
    lines = [
        f"상품명: {product.get('상품명', '')}",
        f"서브태그: {product.get('서브태그', '')}",
        "",
        "[structured]",
    ]
    structured = {
        k: v for k, v in (product.get("structured") or {}).items()
        if k not in STRUCTURED_EXCLUDE
    }
    for k, v in structured.items():
        if isinstance(v, list):
            v_str = ", ".join(str(x) for x in v[:10])
            if len(v) > 10:
                v_str += f" ... (+{len(v) - 10})"
        elif isinstance(v, str) and len(v) > 200:
            v_str = v[:200] + "..."
        else:
            v_str = str(v)
        lines.append(f"  {k}: {v_str}")
    return "\n".join(lines)


def build_prompt(spec: dict, product: dict) -> str:
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

def to_score(j: AxisJudgement, category_matched: bool) -> tuple[int, str | None]:
    """(점수, gate_reason) 반환.

    게이트는 확인 가능한 두 사유에서만 발동한다.
    preference / condition 의 CONFLICT 는 가산 0으로만 반영하고 감점하지 않는다 —
    두 축은 "있으면 좋은 것"과 "본인 조건"이라 하드 리젝트 근거가 없다.
    """
    if not category_matched:
        return 1, "category_mismatch"
    if j.avoid_violated:
        return 1, "avoid_violated"
    if not j.core_need_met:
        return 2, None
    return 3 + (j.preference == "MATCH") + (j.condition == "MATCH"), None


# ─────────────────────────────────────────────
# 채점
# ─────────────────────────────────────────────

async def judge_single(
    target: dict,
    specs: dict,
    products: dict,
    normalize,
    llm,
    semaphore: asyncio.Semaphore,
    done_ref: list,
    total: int,
) -> dict | None:
    from langchain_core.messages import SystemMessage, HumanMessage

    persona_id = target["persona_id"]
    product_id = target["product_id"]

    spec_item = specs.get(persona_id)
    product = products.get(product_id)
    if spec_item is None or product is None:
        done_ref[0] += 1
        missing = "PersonaSpec" if spec_item is None else "상품"
        print(f"[{done_ref[0]}/{total}] {persona_id}/{product_id} 건너뜀 — {missing} 없음")
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

    # 카테고리 게이트는 LLM 없이 결정된다
    if not category_matched:
        done_ref[0] += 1
        print(f"[{done_ref[0]}/{total}] {persona_id} {product_id} → 1점 (category_mismatch)")
        return {**base, "judgement": None, "score": 1, "gate_reason": "category_mismatch"}

    async with semaphore:
        try:
            structured_llm = llm.with_structured_output(AxisJudgement)
            messages = [
                SystemMessage(content=JUDGE_SYSTEM_PROMPT),
                HumanMessage(content=build_prompt(spec, product)),
            ]
            j: AxisJudgement = await structured_llm.ainvoke(messages)
            score, gate_reason = to_score(j, category_matched)

            done_ref[0] += 1
            print(
                f"[{done_ref[0]}/{total}] {persona_id} {product_id} → {score}점 "
                f"(need={j.core_need_met} pref={j.preference} cond={j.condition} "
                f"avoid={j.avoid_violated})"
            )
            return {**base, "judgement": j.model_dump(), "score": score, "gate_reason": gate_reason}
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
    parser.add_argument("--force", action="store_true", help="캐시 무시하고 전건 재채점")
    args = parser.parse_args()

    if not SPEC_FILE.exists():
        sys.exit(f"{SPEC_FILE.name} 이 없습니다. extract_persona_spec.py 를 먼저 실행하세요.")

    RESULT_DIR.mkdir(parents=True, exist_ok=True)
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

    print(f"사람 3인 공통 {len(targets)}건 | 완료 {len(done)}건 | 채점 대상 {len(todo)}건")
    print(f"모델: {settings.chatgpt_model_name}  동시성: {args.concurrency}")
    print("─" * 70)

    if not todo:
        print("채점할 항목이 없습니다.")
        return

    llm = get_llm(settings.chatgpt_model_name, temperature=0)
    semaphore = asyncio.Semaphore(args.concurrency)
    done_ref = [0]

    results = await asyncio.gather(
        *(
            judge_single(t, specs, products, normalize, llm, semaphore, done_ref, len(todo))
            for t in todo
        )
    )
    ok = [r for r in results if r is not None]

    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        for r in ok:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print("─" * 70)
    print(f"저장: {OUTPUT_FILE.name}  (신규 {len(ok)}건 / 누적 {len(done) + len(ok)}건)")
    failed = len(todo) - len(ok)
    if failed:
        print(f"실패 {failed}건 — 재실행하면 이어서 처리한다.")


if __name__ == "__main__":
    asyncio.run(main())
