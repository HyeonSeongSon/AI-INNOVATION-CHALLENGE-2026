"""
페르소나 요구 명세(PersonaSpec) 추출 — 1회 실행 후 캐시.

페르소나 텍스트를 구조로 고정해두면
  · 조합 A/B 비교 때 양쪽이 완전히 같은 기준을 쓴다
  · 채점 프롬프트가 매번 페르소나를 다시 해석하지 않는다
  · 사람이 60건을 검수해 "사람이 승인한 요구 명세"로 만들 수 있다

핵심 원칙 — 추론 금지:
    페르소나 텍스트에 명시된 것만 추출한다.
    "민감성이니까 산 성분은 안 좋을 것" 같은 추론을 허용하면
    게이트가 주관의 통로가 되고, 비전용 지식 없이 재현 가능하다는 설계 의도가 무너진다.

사용법:
    python extract_persona_spec.py
    python extract_persona_spec.py --concurrency 5
    python extract_persona_spec.py --force        # 캐시 무시하고 전건 재추출
"""

import asyncio
import argparse
import json
import sys
from pathlib import Path

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
RESULT_DIR = BASE_DIR / "result"
PERSONA_FILE = BASE_DIR / "human_annotated_eval_data_set.jsonl"
OUTPUT_FILE = RESULT_DIR / "persona_specs.json"
REVIEW_FILE = RESULT_DIR / "persona_specs_review.txt"

DEFAULT_CONCURRENCY = 5


# ─────────────────────────────────────────────
# 스키마
# ─────────────────────────────────────────────

class PersonaSpec(BaseModel):
    core_needs: list[str] = Field(
        description="반드시 해결해야 할 것. '니즈'와 '고민/피부 고민' 항목에서 추출한다."
    )
    preferences: list[str] = Field(
        description="있으면 좋은 것. '선호 포인트'와 '구매 기준' 항목에서 추출한다."
    )
    self_conditions: list[str] = Field(
        description="본인 조건. 피부/두피/모발 타입·상태, 사용 방식, 사용 환경 등."
    )
    avoid: list[str] = Field(
        description="사용 자체가 불가능한 명시적 회피 조건. 없으면 빈 리스트."
    )


EXTRACT_SYSTEM_PROMPT = """당신은 페르소나 텍스트에서 상품 요구 명세를 추출하는 도구입니다.
평가나 추천을 하지 않습니다. 텍스트에 적힌 것을 네 가지 항목으로 옮기기만 합니다.

[절대 원칙 — 추론 금지]
텍스트에 명시된 표현만 옮깁니다. 배경지식으로 항목을 추가하지 마세요.
  - 금지 예: "민감성"이라고 적혀 있다고 해서 "산 성분 회피"를 추가하는 것
  - 금지 예: "건성"이라고 적혀 있다고 해서 "고보습 필요"를 임의로 추가하는 것
텍스트에 근거가 없으면 넣지 않습니다. 빈 리스트도 정상적인 답입니다.

[항목별 기준]

core_needs — 반드시 해결해야 할 것
  '니즈', '고민', '피부 고민' 항목에서 추출합니다.
  해결 대상이 되는 문제와 기대 효과를 짧은 구로 씁니다.

preferences — 있으면 좋은 것 (선택 사항)
  '선호 포인트', '구매 기준' 항목에서 추출합니다.
  **부정형으로 표현된 선호도 여기에 넣습니다.**
  예: "끈적임 없는", "자극 없이", "무향", "부담 없는" → 전부 preferences

self_conditions — 본인 조건
  '피부 타입', '두피 타입', '모발 상태', '피부 상태', '입술 상태' 등 상태 항목과
  '사용 방식', '사용 환경', '사용 상황' 을 넣습니다.
  '이름'의 나이·직업, '라이프스타일'은 상품 속성과 대조할 수 없으므로 넣지 않습니다.

avoid — 사용 자체가 불가능한 명시적 회피 조건
  **가장 엄격하게 판단합니다. 이 항목만 하드 리젝트를 발동시킵니다.**
  아래처럼 '사용 불가'가 분명할 때만 넣습니다.
    - "○○ 알레르기가 있어 쓸 수 없음"
    - "○○ 성분은 절대 피함"
    - "○○는 안 맞아서 못 씀"
  다음은 avoid가 아니라 preferences 입니다. 절대 avoid에 넣지 마세요.
    - "무향", "저자극", "끈적임 없는", "자극 없이", "부담 없는", "순한"
    - "○○ 위주로 고름", "○○ 피하고 △△ 위주로" 같은 선호 표현
  대부분의 페르소나는 avoid가 빈 리스트입니다. 그것이 정상입니다."""


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


def load_cache() -> dict:
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


# ─────────────────────────────────────────────
# 추출
# ─────────────────────────────────────────────

async def extract_single(
    record: dict,
    llm,
    semaphore: asyncio.Semaphore,
    done_ref: list,
    total: int,
) -> tuple[str, dict] | None:
    from langchain_core.messages import SystemMessage, HumanMessage

    persona_id = record["persona_id"]

    async with semaphore:
        try:
            structured_llm = llm.with_structured_output(PersonaSpec)
            messages = [
                SystemMessage(content=EXTRACT_SYSTEM_PROMPT),
                HumanMessage(content=f"[페르소나 텍스트]\n{record['information']}"),
            ]
            spec: PersonaSpec = await structured_llm.ainvoke(messages)

            done_ref[0] += 1
            print(
                f"[{done_ref[0]}/{total}] {persona_id} ({record['product_tag']}) "
                f"needs={len(spec.core_needs)} pref={len(spec.preferences)} "
                f"cond={len(spec.self_conditions)} avoid={len(spec.avoid)}"
            )
            return persona_id, {
                "persona_id": persona_id,
                "product_tag": record["product_tag"],
                "information": record["information"],
                "spec": spec.model_dump(),
            }
        except Exception as e:
            done_ref[0] += 1
            print(f"[{done_ref[0]}/{total}] {persona_id} 실패 — {type(e).__name__}")
            return None


def write_review(cache: dict) -> None:
    """사람 검수용 텍스트. 원문과 추출 결과를 나란히 둔다."""
    lines = [
        "PersonaSpec 검수 시트",
        "",
        "확인할 것",
        "  1. core_needs 가 비어 있는 페르소나가 없는가",
        "  2. avoid 에 텍스트에 없는 추론이 들어가지 않았는가  ← 가장 엄격히",
        "     '무향' '저자극' '끈적임 없는' 은 preferences 여야 한다",
        "  3. preferences 와 avoid 가 뒤바뀌지 않았는가",
        "",
        "수정은 result/persona_specs.json 을 직접 편집한다.",
        "=" * 78,
        "",
    ]
    for pid in sorted(cache):
        item = cache[pid]
        spec = item["spec"]
        lines.append("─" * 78)
        lines.append(f"{pid}  [{item['product_tag']}]")
        lines.append("")
        lines.append("  [원문]")
        for ln in item["information"].split("\n"):
            if ln.strip():
                lines.append(f"    {ln.strip()}")
        lines.append("")
        lines.append("  [추출]")
        for field in ("core_needs", "preferences", "self_conditions", "avoid"):
            values = spec.get(field) or []
            mark = "  ⚠" if (field == "avoid" and values) else "   "
            lines.append(f"  {mark} {field:<16}: {values}")
        lines.append("")
    REVIEW_FILE.write_text("\n".join(lines), encoding="utf-8")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--force", action="store_true", help="캐시 무시하고 전건 재추출")
    args = parser.parse_args()

    RESULT_DIR.mkdir(parents=True, exist_ok=True)

    records = load_jsonl(PERSONA_FILE)
    cache = {} if args.force else load_cache()
    todo = [r for r in records if r["persona_id"] not in cache]

    print(f"페르소나 {len(records)}건 | 캐시 {len(cache)}건 | 추출 대상 {len(todo)}건")
    print(f"모델: {settings.chatgpt_model_name}  동시성: {args.concurrency}")
    print("─" * 70)

    if todo:
        llm = get_llm(settings.chatgpt_model_name, temperature=0)
        semaphore = asyncio.Semaphore(args.concurrency)
        done_ref = [0]
        results = await asyncio.gather(
            *(extract_single(r, llm, semaphore, done_ref, len(todo)) for r in todo)
        )
        for item in results:
            if item is not None:
                cache[item[0]] = item[1]

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)

    write_review(cache)

    print("─" * 70)
    print(f"저장: {OUTPUT_FILE.name} ({len(cache)}/{len(records)}건)")
    print(f"검수: {REVIEW_FILE.name}")

    missing = [r["persona_id"] for r in records if r["persona_id"] not in cache]
    if missing:
        print(f"미완료 {len(missing)}건 — 재실행하면 이어서 처리한다: {missing[:5]}")

    empty_needs = [p for p, v in cache.items() if not v["spec"]["core_needs"]]
    with_avoid = [p for p, v in cache.items() if v["spec"]["avoid"]]
    print()
    print(f"core_needs 비어있음 : {len(empty_needs)}건 {empty_needs[:5]}")
    print(f"avoid 있음          : {len(with_avoid)}건 {with_avoid[:10]}")
    print("  ※ avoid는 하드 리젝트를 발동시키는 유일한 필드다. 전건 검수할 것.")


if __name__ == "__main__":
    asyncio.run(main())
