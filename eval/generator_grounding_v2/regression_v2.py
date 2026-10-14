"""
회귀 시험 (효과 주장 아님, 축소 진행 — 검증기 없이 규칙 검사 + 사례 보기).

    python regression_v2.py

알려진 실패 입력 8건을 v1 · v2 프롬프트로 각 3회 생성한다(양쪽 같은 횟수 → 평균 회귀 상쇄).
- v1: git HEAD 의 purpose_prompt.py(잠금 v1 해시)를 불러 생성(fitter 없음)
- v2: 현재 purpose_prompt.py + 실시간 PersonaFitter
검사: 항목별 '알려진 실패 문구' 정규식 + 정리 항목 정규식(measure_v2.regex_metrics_v2).
결과: result/regression/messages.jsonl, summary.md (요약표 — 사람이 훑어본다)
"""

import asyncio
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import v2_common as vc
from gg_common import load_jsonl, write_jsonl

import measure_v2 as mv  # noqa: E402
from app.config.settings import settings  # noqa: E402
from app.core.data_loader import get_brand_tones  # noqa: E402
from app.core.llm_factory import get_llm  # noqa: E402
from app.agents.generate_message_agent.nodes import _parse_message  # noqa: E402
from app.agents.generate_message_agent.prompts import persona_fit as pf  # noqa: E402
from app.agents.generate_message_agent.services.generate_crm_message import CrmMessageGenerator  # noqa: E402

OUT = vc.RESULT / "regression"
REPS = 3
# 항목 → (출처 세트, 알려진 실패, 재발 후보 정규식)
CASES = {
    "H051": ("holdout", "특성어긋남: 산뜻 · 가벼운 제형을 '묵직하게 코팅'", r"묵직"),
    "H062": ("holdout", "특성어긋남: 흡수 보통 · 3단계를 '빠른 흡수' · '1–2단계'", r"빠른\s?흡수|빠르게\s?흡수|1\s?[–~-]\s?2\s?단계"),
    "H016": ("holdout", "고민연결: '건조와 피로로 칙칙해진 분'", r"피로"),
    "H059": ("holdout", "고민연결: '세안 후 당김이 신경 쓰이는 분'", r"당김"),
    "H067": ("holdout", "고민연결: '번들거림이 신경 쓰이는 분'", r"번들"),
    "H057": ("holdout", "숫자 변형: 상품정보 '3초' → '3분'", r"\d+\s?분"),
    "H010": ("holdout", "리뷰 기반 '검증된'", r"검증"),
    "O042": ("insample", "숫자 변형: '3초 진단' → '3분 맞춤 케어'", r"\d+\s?분"),
}


def v1_prompts():
    rel = "backend/app/agents/generate_message_agent/prompts/purpose_prompt.py"
    src = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=vc.gg.REPO, capture_output=True, check=True).stdout
    base = json.loads(vc.BASELINE_V2.read_text(encoding="utf-8"))["purpose_prompt_v1"]
    crlf = src.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    assert base in (hashlib.sha256(src).hexdigest(), hashlib.sha256(crlf).hexdigest()), "HEAD 가 v1 해시가 아님"
    d = tempfile.mkdtemp()
    p = Path(d) / "purpose_prompt_v1.py"
    p.write_bytes(src)
    spec = importlib.util.spec_from_file_location("purpose_prompt_v1", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.PurPosePrompts()


def generator_v1() -> CrmMessageGenerator:
    gen = CrmMessageGenerator()
    pp = v1_prompts()
    gen._purpose_prompt_map = {
        "브랜드/제품 첫소개": pp.build_purpose_introduction_prompt,
        "신제품 홍보": pp.build_purpose_new_products_prompt,
        "베스트셀러 제품 소개": pp.build_purpose_bestseller_prompt,
        "프로모션/이벤트 소개": pp.build_purpose_promotion_and_event_prompt,
        "성분/효능 강조 소개": pp.build_purpose_ingredient_efficacy_point_prompt,
        "피부타입/고민 강조 소개": pp.build_purpose_skintype_and_concern_point_prompt,
        "라이프스타일/연령대 강조 소개": pp.build_purpose_lifestyle_and_age_point_prompt,
    }
    return gen


async def main() -> None:
    src = {s: {r["item_id"]: r for r in vc.gg.load_inputs(s)} for s in ("holdout", "insample")}
    gens = {"v1": generator_v1(), "v2": CrmMessageGenerator(persona_fitter=pf.PersonaFitter())}
    llm = get_llm(settings.chatgpt_model_name, temperature=settings.llm_temperature_generator)
    tones = get_brand_tones().get("brand_ton_prompt", {})
    sem = asyncio.Semaphore(8)

    async def one(cond, iid, rep):
        it = src[CASES[iid][0]][iid]
        async with sem:
            tasks = [{"product_id": it.get("product_id") or it["product_snapshot"].get("product_id"),
                      "purpose": it["purpose"], "product_info": it["product_snapshot"]}]
            tasks = await gens[cond].get_brand_tone(tasks)
            tasks = await gens[cond].get_crm_prompt(tasks, persona_info=it["persona_info"])
            g = await gens[cond].generate_crm_message(tasks, llm)
        m = _parse_message(g[0]["message"]) if g else {"title": "", "message": ""}
        row = {**it, "item_id": f"{iid}#{cond}#{rep}", "case": iid, "cond": cond, "rep": rep,
               "title": m.get("title", ""), "message": m.get("message", ""), "fit_status": tasks[0].get("fit_status")}
        text = row["title"] + " " + row["message"]
        row["known_failure_hit"] = re.findall(CASES[iid][2], text)
        reg = mv.regex_metrics_v2(row, str(tones.get(it["brand"], "") or ""))
        row["cleanup"] = {k: reg[k] for k in ("number_mutation", "review_verified", "change_hook_title", "test_kind_missing")}
        return row

    rows = await asyncio.gather(*(one(c, i, r) for c in ("v1", "v2") for i in CASES for r in range(1, REPS + 1)))
    OUT.mkdir(parents=True, exist_ok=True)
    write_jsonl(OUT / "messages.jsonl", rows)
    L = ["# 회귀 시험 — 알려진 실패 입력 8건 × v1 · v2 × 3회 (규칙 검사, 효과 주장 아님)", "",
         "| 항목 | 알려진 실패 | v1 재발 후보 | v2 재발 후보 |", "|---|---|---|---|"]
    for iid, (_, desc, _pat) in CASES.items():
        cnt = {c: sum(1 for r in rows if r["case"] == iid and r["cond"] == c and r["known_failure_hit"]) for c in ("v1", "v2")}
        L.append(f"| {iid} | {desc} | {cnt['v1']}/{REPS} | {cnt['v2']}/{REPS} |")
    L += ["", "재발 후보는 문구 일치만 본 것이다(예: '당김'은 공감 문장일 수도 있다). 아래 문장을 훑어 실제 재발인지 본다.", ""]
    for r in sorted(rows, key=lambda x: (x["case"], x["cond"], x["rep"])):
        if r["known_failure_hit"]:
            sents = [s for s in re.split(r"(?<=[.!?])\s+|\n", r["title"] + " / " + r["message"]) if re.search(CASES[r["case"]][2], s)]
            L.append(f"- **{r['case']} {r['cond']} #{r['rep']}**: " + " … ".join(sents)[:300])
    (OUT / "summary.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"→ {OUT / 'summary.md'}")
    print("\n".join(L[:12]))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
