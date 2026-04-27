"""
추천 시스템 가중치 평가 스크립트 (LLM-as-Judge)

human_annotated_eval_data_set.jsonl (페르소나)와
human_annotated_top5_results.jsonl (추천 결과)를 읽어,
각 추천 상품의 페르소나 적합도를 LLM이 1~5점으로 평가합니다.

핵심 분석:
  - 전체 평균 점수
  - 순위별 평균 점수 (rank1 > rank5 이어야 가중치가 작동 중)
  - 카테고리별 품질

사용법:
    python eval/eval_recommendation_weights.py
    python eval/eval_recommendation_weights.py --concurrency 3 --output eval/weight_eval_results.jsonl
"""

import asyncio
import json
import argparse
import sys
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).parent.parent
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

_EVAL_DIR   = Path(__file__).parent
_V3_DATA_PATHS = [
    _ROOT / "data" / "v3_product_data_rewritten_beauty_tool.jsonl",
    _ROOT / "data" / "v3_product_data_rewritten_color_tone.jsonl",
    _ROOT / "data" / "v3_product_data_rewritten_fragrance_body.jsonl",
    _ROOT / "data" / "v3_product_data_rewritten_hair.jsonl",
    _ROOT / "data" / "v3_product_data_rewritten_inner_beauty.jsonl",
    _ROOT / "data" / "v3_product_data_rewritten_living_supplies.jsonl",
    _ROOT / "data" / "v3_product_data_rewritten_skincare.jsonl",
]

DEFAULT_PERSONA_PATH = _EVAL_DIR / "human_annotated_eval_data_set.jsonl"
DEFAULT_RESULT_PATH  = _EVAL_DIR / "human_annotated_top5_results.jsonl"
DEFAULT_OUTPUT_PATH  = _EVAL_DIR / "weight_eval_results.jsonl"
DEFAULT_CONCURRENCY  = 5


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


def load_product_db(paths: list[Path]) -> dict[str, dict]:
    """product_id → 상품 정보 딕셔너리 (v3 JSONL 파일들에서 로드)"""
    db: dict[str, dict] = {}
    for path in paths:
        if not path.exists():
            print(f"[WARN] 파일 없음, 건너뜀: {path.name}")
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    p = json.loads(line)
                    pid = p.get("product_id")
                    if pid:
                        db[pid] = p
    return db


def format_product_summary(product: dict) -> str:
    """LLM에 넘길 상품 요약 텍스트 생성 (product_details/structured 기반)"""
    name  = product.get("상품명", "")
    brand = product.get("브랜드", "")
    det   = product.get("structured") or product.get("product_details") or {}

    summary     = det.get("summary", "")
    target_user = det.get("target_user", "")
    concerns    = ", ".join(det.get("concern",       []) or [])
    ingredients = ", ".join(det.get("ingredient",    []) or [])
    skin        = ", ".join(det.get("suitable_for",  []) or [])
    functions   = ", ".join(det.get("function",      []) or [])
    texture     = ", ".join(det.get("texture",       []) or [])
    value       = ", ".join(det.get("value",         []) or [])

    lines = [f"  상품명: {brand} {name}", f"  소개: {summary}"]
    if skin:        lines.append(f"  적합피부: {skin}")
    if concerns:    lines.append(f"  대상고민: {concerns}")
    if ingredients: lines.append(f"  주요성분: {ingredients}")
    if functions:   lines.append(f"  기능: {functions}")
    if texture:     lines.append(f"  제형: {texture}")
    if value:       lines.append(f"  가치: {value}")
    if target_user: lines.append(f"  타겟: {target_user}")
    return "\n".join(lines)


# ─────────────────────────────────────────────
# LLM Judge (Structured Output)
# ─────────────────────────────────────────────

class ProductScore(BaseModel):
    rank: int   = Field(description="추천 순위 (1~5)")
    score: int  = Field(description="페르소나 적합도 점수 (1~5)")
    reason: str = Field(description="한 문장 이내의 점수 근거")


class JudgeOutput(BaseModel):
    scores: list[ProductScore] = Field(description="각 추천 상품의 적합도 평가")
    overall_comment: str = Field(description="전체 추천 품질에 대한 한 문장 총평")


JUDGE_SYSTEM_PROMPT = """당신은 뷰티 상품 추천 시스템의 품질 평가 전문가입니다.
페르소나 정보와 추천된 상품 목록을 보고 각 상품이 해당 페르소나에 얼마나 적합한지 평가합니다.

점수 기준:
5점 - 페르소나 니즈, 고민, 선호 성분/제형 등이 모두 잘 맞음
4점 - 대부분 잘 맞고 핵심 니즈를 충족
3점 - 부분적으로 맞지만 아쉬운 점 있음
2점 - 카테고리는 맞으나 페르소나 특성과 잘 안 맞음
1점 - 전혀 적합하지 않음

각 상품에 대해 개별 점수를 매기고, 마지막에 전체 추천 세트에 대한 한 줄 총평을 작성하세요."""


def build_judge_prompt(persona_info: str, products: list[dict], product_db: dict) -> str:
    lines = ["[페르소나 정보]", persona_info, "", "[추천 상품 목록]"]
    for i, p in enumerate(products, start=1):
        pid     = p["product_id"]
        product = product_db.get(pid)
        if product:
            lines.append(f"\n{i}순위 (product_id: {pid})")
            lines.append(format_product_summary(product))
        else:
            lines.append(f"\n{i}순위 (product_id: {pid}): 상품 정보 없음")
    return "\n".join(lines)


# ─────────────────────────────────────────────
# 단일 레코드 평가
# ─────────────────────────────────────────────

async def evaluate_single(
    persona_record: dict,
    result_record: dict,
    product_db: dict,
    llm,
    semaphore: asyncio.Semaphore,
    done_ref: list,
    total: int,
) -> dict:
    persona_id  = persona_record["persona_id"]
    product_tag = persona_record["product_tag"]
    persona_info = persona_record["information"]
    top5         = result_record.get("top5", [])

    async with semaphore:
        try:
            if not top5:
                raise ValueError("top5 결과 없음")

            prompt_text = build_judge_prompt(persona_info, top5, product_db)

            structured_llm = llm.with_structured_output(JudgeOutput)
            from langchain_core.messages import SystemMessage, HumanMessage
            messages = [
                SystemMessage(content=JUDGE_SYSTEM_PROMPT),
                HumanMessage(content=prompt_text),
            ]
            output: JudgeOutput = await structured_llm.ainvoke(messages)

            scores_by_rank = {s.rank: s.score for s in output.scores}
            reasons_by_rank = {s.rank: s.reason for s in output.scores}

            done_ref[0] += 1
            avg = sum(scores_by_rank.values()) / len(scores_by_rank) if scores_by_rank else 0
            print(
                f"[{done_ref[0]}/{total}] {persona_id} ({product_tag}) "
                f"avg={avg:.2f} | {[scores_by_rank.get(r, '-') for r in range(1, len(top5)+1)]}"
            )

            return {
                "persona_id":      persona_id,
                "product_tag":     product_tag,
                "language_type":   persona_record.get("language_type", ""),
                "top5":            top5,
                "scores_by_rank":  scores_by_rank,
                "reasons_by_rank": reasons_by_rank,
                "avg_score":       round(avg, 3),
                "overall_comment": output.overall_comment,
                "error":           None,
            }

        except Exception as e:
            done_ref[0] += 1
            print(f"[{done_ref[0]}/{total}] [error] {persona_id}: {e}")
            return {
                "persona_id":  persona_id,
                "product_tag": product_tag,
                "top5":        top5,
                "avg_score":   None,
                "error":       str(e),
            }


# ─────────────────────────────────────────────
# 집계 및 출력
# ─────────────────────────────────────────────

def print_report(results: list[dict], top_n: int):
    valid = [r for r in results if r.get("error") is None and r.get("avg_score") is not None]
    errors = [r for r in results if r.get("error") is not None]

    if not valid:
        print("유효한 평가 결과 없음")
        return

    # ── 전체 평균 ──
    overall_avg = sum(r["avg_score"] for r in valid) / len(valid)

    # ── 순위별 평균 ──
    rank_scores: dict[int, list[float]] = {i: [] for i in range(1, top_n + 1)}
    for r in valid:
        # JSON 직렬화 후 로드 시 key가 str로 변환되므로 int로 재변환
        sbr = {int(k): v for k, v in r.get("scores_by_rank", {}).items()}
        for rank in range(1, top_n + 1):
            if rank in sbr:
                rank_scores[rank].append(sbr[rank])

    # ── top3 평균 (rank 1~3만) ──
    top3_scores_all = [s for rank in range(1, 4) for s in rank_scores.get(rank, [])]
    top3_avg = sum(top3_scores_all) / len(top3_scores_all) if top3_scores_all else 0.0

    # ── 카테고리별 평균 (top5 / top3) ──
    by_category: dict[str, list[float]] = {}
    by_category_top3: dict[str, list[float]] = {}
    for r in valid:
        cat = r.get("product_tag", "기타")
        by_category.setdefault(cat, []).append(r["avg_score"])
        sbr = {int(k): v for k, v in r.get("scores_by_rank", {}).items()}
        top3_vals = [sbr[rk] for rk in range(1, 4) if rk in sbr]
        if top3_vals:
            by_category_top3.setdefault(cat, []).append(sum(top3_vals) / len(top3_vals))

    # ── language_type별 평균 ──
    by_lang: dict[str, list[float]] = {}
    for r in valid:
        lt = r.get("language_type", "unknown")
        by_lang.setdefault(lt, []).append(r["avg_score"])

    sep = "=" * 60
    print(f"\n{sep}")
    print(f" 추천 가중치 평가 리포트 (LLM-as-Judge)  N={len(valid)}")
    print(sep)

    print(f"\n[전체 평균]")
    print(f"  top5: {overall_avg:.3f} / 5.0")
    print(f"  top3: {top3_avg:.3f} / 5.0")

    print(f"\n[순위별 평균 점수] — rank1 > rankN 이면 정렬 품질 양호")
    print(f"  {'순위':<6} {'평균':>6} {'건수':>5}")
    print("  " + "-" * 22)
    for rank in range(1, top_n + 1):
        scores = rank_scores[rank]
        if scores:
            avg = sum(scores) / len(scores)
            marker = " ◀ top3" if rank == 3 else ""
            print(f"  rank{rank:<3} {avg:>6.3f} ({len(scores):>4}건){marker}")
    # rank1 vs rank5 격차
    r1 = rank_scores.get(1, [])
    r5 = rank_scores.get(5, [])
    r3 = rank_scores.get(3, [])
    if r1 and r5:
        gap = sum(r1) / len(r1) - sum(r5) / len(r5)
        print(f"\n  rank1 - rank5 격차: {gap:+.3f}  {'✓ 양호' if gap > 0 else '✗ 역전 발생 → 가중치 재조정 필요'}")
    if r1 and r3:
        gap3 = sum(r1) / len(r1) - sum(r3) / len(r3)
        print(f"  rank1 - rank3 격차: {gap3:+.3f}  {'✓ 양호' if gap3 > 0 else '✗ 역전 발생'}")

    print(f"\n[카테고리별 평균]")
    print(f"  {'카테고리':<20} {'top5':>6} {'top3':>6} {'건수':>5}")
    print("  " + "-" * 44)
    for cat, scores in sorted(by_category.items(), key=lambda x: -sum(x[1]) / len(x[1])):
        avg5 = sum(scores) / len(scores)
        t3 = by_category_top3.get(cat, [])
        avg3 = sum(t3) / len(t3) if t3 else 0.0
        print(f"  {cat:<20} {avg5:>6.3f} {avg3:>6.3f} ({len(scores):>4}건)")

    print(f"\n[페르소나 유형별 평균] (language_type)")
    for lt, scores in sorted(by_lang.items()):
        avg = sum(scores) / len(scores)
        print(f"  {lt:<12}: {avg:.3f}  (N={len(scores)})")

    if errors:
        print(f"\n[오류] {len(errors)}건")
        for e in errors:
            print(f"  - {e['persona_id']}: {e['error']}")

    print(f"\n{sep}\n")


# ─────────────────────────────────────────────
# main
# ─────────────────────────────────────────────

async def main(
    persona_path: Path,
    result_path: Path,
    output_path: Path,
    concurrency: int,
):
    print(f"\n{'='*60}")
    print(f"추천 가중치 평가 (LLM-as-Judge)")
    print(f"  페르소나: {persona_path.name}")
    print(f"  추천결과: {result_path.name}")
    print(f"  상품DB  : v3 JSONL ({len(_V3_DATA_PATHS)}개 파일)")
    print(f"  출력    : {output_path.name}")
    print(f"  LLM     : {settings.chatgpt_model_name}")
    print(f"  동시실행: {concurrency}")
    print(f"{'='*60}\n")

    # 이미 처리된 persona_id 스킵
    existing: set[str] = set()
    if output_path.exists():
        for r in load_jsonl(output_path):
            pid = r.get("persona_id")
            if pid and r.get("error") is None:
                existing.add(pid)
    if existing:
        print(f"기존 결과: {len(existing)}개 스킵\n")

    personas  = {r["persona_id"]: r for r in load_jsonl(persona_path)}
    results   = {r["persona_id"]: r for r in load_jsonl(result_path)}
    product_db = load_product_db(_V3_DATA_PATHS)
    print(f"상품 DB 로드: {len(product_db)}개\n")

    # 페르소나 & 결과 매핑
    targets = [
        (personas[pid], results[pid])
        for pid in personas
        if pid in results and pid not in existing
    ]
    total = len(targets)
    if total == 0:
        print("모든 레코드가 이미 평가됨.")
        # 기존 결과 리포트만 출력
        all_results = load_jsonl(output_path)
        top_n = max((len(r.get("top5", [])) for r in all_results if r.get("top5")), default=5)
        print_report(all_results, top_n)
        return

    print(f"평가 대상: {total}개\n")

    llm       = get_llm(settings.chatgpt_model_name, temperature=0)
    semaphore = asyncio.Semaphore(concurrency)
    done_ref  = [0]

    eval_results = await asyncio.gather(*[
        evaluate_single(p, r, product_db, llm, semaphore, done_ref, total)
        for p, r in targets
    ])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "a", encoding="utf-8") as f:
        for r in eval_results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 전체 결과 리포트 (기존 + 신규)
    all_results = load_jsonl(output_path) if output_path.exists() else eval_results
    top_n = max((len(r.get("top5", [])) for r in all_results if r.get("top5")), default=5)
    print_report(all_results, top_n)


def parse_args():
    parser = argparse.ArgumentParser(description="추천 가중치 LLM 평가")
    parser.add_argument("--persona",     default=str(DEFAULT_PERSONA_PATH))
    parser.add_argument("--result",      default=str(DEFAULT_RESULT_PATH))
    parser.add_argument("--output",      default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(
        persona_path=Path(args.persona),
        result_path=Path(args.result),
        output_path=Path(args.output),
        concurrency=args.concurrency,
    ))
