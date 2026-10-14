"""
D3(개인화 실패) 속성 치환표 초안 — LLM 이 초안을 쓰고, 사용자가 전수 검수한다(플랜 "D3 절차").

D3 는 메시지를 그대로 두고, 같은 페르소나 원문에서 **메시지가 실제로 언급한 속성 하나**만 명시적으로
모순되는 값으로 바꿔 판정한다. 다른 페르소나로 바꾸지 않는다(같은 상품군 후보가 거의 없고, 다른 상품군
페르소나는 "상품이 안 맞는 사람"과 "개인화 실패"를 섞는다).
    - "속성 하나"는 그 속성을 표현하는 **모든 줄**이다(O001 외근 속성은 세 줄에 나온다).
    - 바꿀 속성은 상품 적합성을 깨지 않는 것(연령 · 직업 · 생활 방식)을 우선한다. 피부 타입은 상품의
      skin_type · suitable_for 가 새 값도 포함할 때만.
    - 상품이 필요한 이유까지 바꿔야 하면 쓰지 않는다. "바쁜 일상"처럼 무엇과 충돌하는지 정할 수 없는
      언급도 쓰지 않는다.

자동 검사(초안마다): message_evidence 가 메시지 원문에 그대로 있는가 · 줄 번호가 유효한가 ·
새 줄 수가 같은가 · 바뀐 줄이 실제로 다른가 · 피부 타입이면 새 값이 상품 필드에 있는가.

출력: result/<run>/d3_table_draft.csv — 사용자가 reviewed_usable(O/X) 을 채워 d3_table.csv 로 저장하면
make_variants.py 가 O 인 행만 쓴다.

사용법 (Python 3.11, LLM 호출 원본당 1회):
    python draft_d3.py --run main --concurrency 8
"""

import argparse
import asyncio
import csv
import json
from typing import Any

from _common import bootstrap, load_jsonl, load_personas, run_dir

bootstrap()

from langchain_core.messages import HumanMessage, SystemMessage  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from app.config.settings import settings  # noqa: E402
from app.core.llm_factory import get_llm  # noqa: E402

SYSTEM = """당신은 마케팅 메시지 평가 실험의 테스트 데이터를 만드는 연구 보조입니다.
목표: 메시지는 그대로 두고, 고객 프로필의 속성 하나만 바꿔서 "메시지가 이 고객에게 맞지 않게" 만든다.
규칙:
1. 메시지가 고객 프로필의 속성을 구체적인 값으로 언급한 경우만 쓴다(연령 · 직업 · 생활 방식 · 피부 타입 등).
   "바쁜 일상"처럼 어떤 값과 충돌하는지 정할 수 없는 언급이면 usable=false.
2. 연령 · 직업 · 생활 방식을 우선한다. 피부 타입은 [상품 정보]의 skin_type · suitable_for 가 새 값도 포함할 때만.
3. 그 속성을 표현하는 프로필의 줄을 **모두** 찾아 바꾼다. 한 줄만 바꾸면 나머지 줄이 메시지를 계속 뒷받침한다.
4. 바꾼 값은 메시지의 해당 서술을 명백히 거짓으로 만들어야 한다(명시적 모순).
5. 상품이 필요한 이유(예: 발 상태 · 피부 고민)까지 바꿔야 한다면 usable=false.
6. 바꾸지 않는 줄은 그대로 둔다. 바꾼 줄은 원래 줄의 형식("라벨: 내용")을 유지한다.
7. message_evidence 는 메시지 원문에서 그대로 복사한 구절이어야 한다."""

HUMAN = """## 메시지 (제목 + 본문)
{title}
{message}

## 고객 프로필 (줄 번호: 내용)
{persona_lines}

## 상품 정보 (적합성 확인용)
skin_type: {skin_type}
suitable_for: {suitable_for}"""


class D3Draft(BaseModel):
    usable: bool = Field(description="규칙을 모두 지키는 치환이 가능한가")
    attribute: str = Field(description="바꾼 속성 이름 (연령 / 직업 / 생활 방식 / 피부 타입 / 기타)")
    message_evidence: str = Field(description="메시지에서 그 속성을 언급한 구절(원문 그대로)")
    persona_line_numbers: list[int] = Field(description="그 속성을 표현하는 프로필 줄 번호 전부")
    new_lines: list[str] = Field(description="바꾼 줄 내용 (persona_line_numbers 와 같은 순서, 같은 개수)")
    conflict_basis: str = Field(description="바꾼 값이 메시지 서술을 어떻게 거짓으로 만드는지 한 문장")
    reason_if_unusable: str = Field(default="", description="usable=false 인 이유")


def auto_checks(draft: D3Draft, original: dict[str, Any], lines: list[str]) -> list[str]:
    problems = []
    text = f"{original['title']} {original['message']}"
    if draft.usable:
        if draft.message_evidence not in text:
            problems.append("evidence 가 메시지 원문에 없음")
        if not draft.persona_line_numbers or any(n < 1 or n > len(lines) for n in draft.persona_line_numbers):
            problems.append("줄 번호 오류")
        elif len(draft.new_lines) != len(draft.persona_line_numbers):
            problems.append("새 줄 수가 다름")
        elif any(lines[n - 1].strip() == new.strip() for n, new in zip(draft.persona_line_numbers, draft.new_lines)):
            problems.append("바뀌지 않은 줄 포함")
        if "피부" in draft.attribute and "타입" in draft.attribute:
            product = original["product_snapshot"]
            fit = json.dumps([product.get("skin_type"), product.get("suitable_for")], ensure_ascii=False)
            if not any(tok in fit for new in draft.new_lines for tok in ("건성", "지성", "복합성", "민감성", "중성") if tok in new):
                problems.append("피부 타입 새 값이 상품 skin_type · suitable_for 에 없음(적합성 확인 필요)")
    return problems


async def main_async(args: argparse.Namespace) -> None:
    out_dir = run_dir(args.run)
    originals = load_jsonl(out_dir / "originals.jsonl")
    personas = load_personas()
    llm = get_llm(settings.chatgpt_model_name, temperature=settings.llm_temperature_classifier)
    structured = llm.with_structured_output(D3Draft)
    sem = asyncio.Semaphore(args.concurrency)

    async def one(o: dict[str, Any]) -> dict[str, Any]:
        lines = personas[o["persona_id"]]["information"].split("\n")
        product = o["product_snapshot"]
        human = HUMAN.format(
            title=o["title"], message=o["message"],
            persona_lines="\n".join(f"{i}: {ln}" for i, ln in enumerate(lines, 1)),
            skin_type=product.get("skin_type"), suitable_for=product.get("suitable_for"),
        )
        async with sem:
            draft: D3Draft = await structured.ainvoke([SystemMessage(content=SYSTEM), HumanMessage(content=human)])
        return {
            "original_id": o["original_id"], "persona_id": o["persona_id"],
            "draft_usable": "O" if draft.usable else "X",
            "attribute": draft.attribute, "message_evidence": draft.message_evidence,
            "persona_line_numbers": ",".join(map(str, draft.persona_line_numbers)),
            "old_lines": " || ".join(lines[n - 1] for n in draft.persona_line_numbers if 1 <= n <= len(lines)),
            "new_lines": " || ".join(draft.new_lines),
            "conflict_basis": draft.conflict_basis, "reason_if_unusable": draft.reason_if_unusable,
            "auto_problems": " | ".join(auto_checks(draft, o, lines)),
            "reviewed_usable(O/X)": "", "review_note": "",
        }

    rows = await asyncio.gather(*(one(o) for o in originals))
    path = out_dir / "d3_table_draft.csv"
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    (out_dir / "d3_draft_prompt.txt").write_text(
        f"model={settings.chatgpt_model_name} temperature_setting={settings.llm_temperature_classifier}\n\n"
        f"[SYSTEM]\n{SYSTEM}\n\n[HUMAN TEMPLATE]\n{HUMAN}\n", encoding="utf-8")
    usable = sum(r["draft_usable"] == "O" and not r["auto_problems"] for r in rows)
    print(f"초안 {len(rows)}건 · 초안상 사용 가능(자동 검사 통과) {usable}건 → {path}")
    print("검수: reviewed_usable(O/X) 를 채워 d3_table.csv 로 저장하면 make_variants.py 가 O 행만 쓴다.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", default="main")
    parser.add_argument("--concurrency", type=int, default=8)
    asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    main()
