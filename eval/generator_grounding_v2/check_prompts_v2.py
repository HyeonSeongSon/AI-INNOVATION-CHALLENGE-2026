"""
v2 프롬프트 점검 (6단계) — v2 · nofit 생성 전에 통과해야 한다(main_v2.py 가 기록을 확인).

    python check_prompts_v2.py

목적 7개 × 본 표본 70건을 두 경로로 그린다.
- fit 경로: 캐시된 fit 결과로 연결 안내 섹션이 들어간 프롬프트
- fit 없는 경로: 보수적 페르소나 문구
점검: 지운 문장이 없음 · 새 규칙이 있음 · 경로별 문구 · 제외 필드 키 없음.
자기 점검: 같은 '지운 문장' 목록을 git HEAD 의 v1 purpose_prompt.py(잠금 해시와 같아야 함)로 그린 프롬프트에 대 보아
모두 걸리는지 확인한다(점검이 실제로 작동하는지).
결과: result/check_prompts_v2.json
"""

import asyncio
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import v2_common as vc
from gg_common import load_jsonl

import build_originals as bo  # noqa: E402 — PURPOSES
from app.agents.generate_message_agent.prompts import persona_fit as pf  # noqa: E402
from app.agents.generate_message_agent.prompts.product_fields import GENERATION_EXCLUDED_FIELDS  # noqa: E402
from app.agents.generate_message_agent.services.generate_crm_message import CrmMessageGenerator  # noqa: E402

OUT = vc.RESULT / "check_prompts_v2.json"
MAIN = vc.RESULT / "main"

REMOVED = [
    "(반드시 반영)",
    "메시지 전체에 자연스럽게 반영",
    "이 한 가지가 달랐던 이유",
    "검증된 베스트셀러 제품을 추천",
    "바로 내 고민을 위한 것",
    "해당 타입의 일반적 고민에서 출발",
    "지금 제품 자세히 보기 — 사용법과 성분 확인",
    "라벨과 제품 특징으로 시작)",
]
REQUIRED_ALL = [
    "사실 근거 규칙 (모든 목적 공통",
    "사실 주장 제한(가장 우선)",
    "상품정보 필드 안내",
    "숫자·단위·기간은 상품정보 문구를 그대로 옮기고 바꿔 쓰지 않습니다",
    "리뷰 수·평점은 그대로 인용만 하고 \"검증\"의 근거로 쓰지 않습니다",
    "변화 암시어는 상품정보에 리뉴얼·기존 대비 근거가 있을 때만",
    "같은 틀(\"사용법과 ○○ 확인\")을 반복하지 말고",
    "그 종류어(시험·임상·인증·수상)가 상품정보에 있을 때만",
    "상품 특성(제형·마무리감·흡수·사용 단계·효능·용도)은 페르소나에 맞추려고 바꾸지 마세요",
]
REQUIRED_BY_PURPOSE = {
    "베스트셀러 제품 소개": ["\"베스트셀러\" 라벨을 반드시 1회 씁니다"],
    "브랜드/제품 첫소개": ["브랜드명 또는 제품명을 1회 자연스럽게 소개"],
    "피부타입/고민 강조 소개": ["상품정보에 없는 고민을 상품이 해결한다고 쓰지 않습니다"],
}
FIT_ONLY = ["아래 연결 안내에 따라 겹치는 지점만 잇습니다", "## 페르소나-상품 연결 안내"]
NOFIT_ONLY = ["상품정보에 없는 고민은 공감만 하며"]


def flat(s: str) -> str:
    return " ".join(s.split())


class CachedFitter:
    def __init__(self, by_pid):
        self._by = by_pid

    async def fit(self, persona_info, product_info):
        return self._by[product_info.get("product_id")]


async def render(gen: CrmMessageGenerator, items: list[dict]) -> list[tuple[str, str, str]]:
    out = []
    for purpose in bo.PURPOSES:
        tasks = [{"product_id": it["product_id"], "purpose": purpose, "product_info": it["product_snapshot"],
                  "_item": it["item_id"], "_persona": it["persona_info"]} for it in items]
        tasks = await gen.get_brand_tone(tasks)
        for t in tasks:
            [r] = await gen.get_crm_prompt([t], persona_info=t["_persona"])
            out.append((purpose, t["_item"], "\n".join(m.content for m in r["prompt"])))
    return out


def check(rendered, path: str) -> list[str]:
    fails = []
    for purpose, item, text in rendered:
        f = flat(text)
        for k in GENERATION_EXCLUDED_FIELDS:
            if f"'{k}'" in text:
                fails.append(f"{path}/{purpose}/{item}: 제외 필드 {k}")
        for s in REMOVED:
            if flat(s) in f:
                fails.append(f"{path}/{purpose}/{item}: 지운 문장 남음 — {s}")
        for s in REQUIRED_ALL + REQUIRED_BY_PURPOSE.get(purpose, []):
            if flat(s) not in f:
                fails.append(f"{path}/{purpose}/{item}: 필수 문장 없음 — {s}")
        for s in (FIT_ONLY if path == "fit" else NOFIT_ONLY):
            if flat(s) not in f:
                fails.append(f"{path}/{purpose}/{item}: 경로 문구 없음 — {s}")
        for s in (NOFIT_ONLY if path == "fit" else FIT_ONLY):
            if flat(s) in f:
                fails.append(f"{path}/{purpose}/{item}: 다른 경로 문구 섞임 — {s}")
    return fails


def v1_selfcheck(items: list[dict]) -> dict:
    """git HEAD 의 v1 purpose_prompt.py 로 그려 REMOVED 가 모두 걸리는지."""
    rel = "backend/app/agents/generate_message_agent/prompts/purpose_prompt.py"
    src = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=vc.gg.REPO, capture_output=True, check=True).stdout
    base = json.loads(vc.BASELINE_V2.read_text(encoding="utf-8"))["purpose_prompt_v1"]
    crlf = src.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")  # git 은 LF 로 저장, 작업 사본은 CRLF
    if base not in (hashlib.sha256(src).hexdigest(), hashlib.sha256(crlf).hexdigest()):
        return {"ok": False, "reason": "HEAD 의 purpose_prompt.py 가 v1 잠금 해시와 다름"}
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "purpose_prompt_v1.py"
        p.write_bytes(src)
        spec = importlib.util.spec_from_file_location("purpose_prompt_v1", p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    pp = mod.PurPosePrompts()
    it = items[0]
    builders = [pp.build_purpose_introduction_prompt, pp.build_purpose_bestseller_prompt,
                pp.build_purpose_skintype_and_concern_point_prompt, pp.build_purpose_ingredient_efficacy_point_prompt]
    text = flat("\n".join(m.content for b in builders for m in b(it["product_snapshot"], "톤", persona_info=it["persona_info"])))
    hits = {s: flat(s) in text for s in REMOVED}
    return {"ok": all(hits.values()), "hits": hits}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    items = load_jsonl(MAIN / "inputs.jsonl")
    cache = load_jsonl(MAIN / "fit_cache.jsonl")
    pid = {it["item_id"]: it["product_snapshot"].get("product_id") for it in items}
    fitter = CachedFitter({pid[c["item_id"]]: pf.FitResult.from_dict(c) for c in cache})
    fit_r = asyncio.run(render(CrmMessageGenerator(persona_fitter=fitter), items))
    nofit_r = asyncio.run(render(CrmMessageGenerator(), items))
    fails = check(fit_r, "fit") + check(nofit_r, "nofit")
    selfc = v1_selfcheck(items)
    if not selfc["ok"]:
        fails.append(f"자기 점검 실패: {selfc}")
    rec = {"checked_at": datetime.now(timezone.utc).isoformat(), "passed": not fails,
           "purpose_prompt": vc.gg.sha256(vc.gg.PURPOSE_PROMPT), "n_prompts": len(fit_r) + len(nofit_r),
           "v1_selfcheck": selfc, "n_fail": len(fails), "fails": sorted(set(fails))[:200]}
    OUT.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"프롬프트 {rec['n_prompts']}개 점검 · 실패 {len(fails)}건 · v1 자기 점검 {selfc['ok']} → {OUT}")
    for f in sorted({x.split(': ', 1)[-1] for x in fails})[:15]:
        print("  ", f)
    if fails:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
