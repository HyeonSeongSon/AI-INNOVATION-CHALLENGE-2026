"""
v3 · v3R 프롬프트 점검 — 생성 전에 통과해야 한다(main_v3.py 가 기록을 확인).

    python check_prompts_v3.py

목적 7개 × 2라운드 새 표본 70건을 두 경로(fit 있음 · 보수 경로)로 그린다(980개).
점검: 지운 문장(v2 긍정 예시 · v1 문구 · v3c 연결 의무 · 조건 없는 연결 요구)이 없음 · 새 필수 문장이 있음 ·
      목적별 조건부 연결 문장(문장 기준, 줄 번호 아님) · 경로별 문구 · 제외 필드 키 없음 ·
      소스의 긍정 예시 '(예: "' 는 클릭베이트 금지 예시 1곳뿐.
자기 점검: v3 에서 지운 v2 문장들이 v2 스냅숏(snapshots/purpose_prompt_v2.py)으로 그린 프롬프트에 모두 걸리는지.
결과: result/check_prompts_v3.json
"""

import asyncio
import importlib.util
import json
import sys
from datetime import datetime, timezone

import v3_common as v3
from gg_common import load_jsonl

import check_prompts_v2 as c2  # noqa: E402 — v1 · v2 에서 지운 문장 목록과 렌더러 재사용
from app.agents.generate_message_agent.prompts import persona_fit as pf  # noqa: E402
from app.agents.generate_message_agent.services.generate_crm_message import CrmMessageGenerator  # noqa: E402

OUT = v3.RESULT / "check_prompts_v3.json"
MAIN = v3.vc.RESULT / "main"

REMOVED_V3 = [  # v2 의 긍정 예시와 v3 에서 바꾼 문장
    "내 피부 고민에 맞는 사용 순서 보기", "이번 혜택 조건과 구성 보기", "실제 발색과 컬러 구성 보기",
    "아침마다 손이 먼저 가는 이유", "다시 찾게 되는 그 한 가지", "이 성분, 왜 들어갔을까?",
    "또 그 향 때문에 망설였나요?", "바르고 나면 더 당기는 그 느낌", "수분 자석 같은 역할",
    "지금 살펴보기", "더 알아보기", "내 피부에 맞는지 확인하기", "피부 타입별 추천 보기", "일상 루틴에 추가하기",
    "성분 정보 자세히 보기", "성분 정보 보기", "제품 자세히 보기", "제품 상세 보기", "같은 틀(\"사용법과 ○○ 확인\")",
]
REMOVED_V3B = [  # v3c 에서 뺀 v3b 문장(B단계에서 근거 없는 상황 적합 · 고민 연결을 늘림)
    "그 고민과 근거 효능을 한 문장 안에서 직접 잇습니다", "신제품의 새로운 특징과 한 문장에서 잇기",
    "그 효능을 가진 성분과 한 문장에서 잇기", "효과를 약속하지 않는 진입점으로 써도 됩니다",
]
REMOVED_V3R = [  # v3R 에서 뺀 v3c 문장 · 조건 없는 연결 요구(연결을 줄이는 변경만)
    "1개 이상을 메시지 앞 두 문장 안에", "선호 일치 항목에 있는 것은 구체적으로 1~2개 밝힙니다",
    "상품이 그 상황에 적합하다거나 도움이 된다고 말하지 않습니다", "상품정보에 없는 고민은 공감만 하며",
    "페르소나의 피부 고민을 진입점으로 연결", "이 신제품이 해결하는 문제라면 연결", "베스트셀러의 주요 효능을 매칭",
    "성분의 효능을 직접 연결", "이 제품이 그 고민에 어떻게 맞춤인지 논리적으로 연결", "이 제품이 그 고민에 맞춤인 이유",
    "이 제품이 그 라이프스타일/연령대에 왜 맞는지", "고민 공감은 1문장까지만", "페르소나의 피부 고민을 질문형/공감형으로 짚기",
    "피부 타입 + 주요 고민 → Hook에 반영", "공감은 해도",
]
REMOVED = c2.REMOVED + REMOVED_V3 + REMOVED_V3B + REMOVED_V3R
REQUIRED_ALL = [s for s in c2.REQUIRED_ALL if "사용법과 ○○ 확인" not in s] + [
    "CTA는 다음 세 가지를 갖춥니다",
    "그 행동의 이유가 이 메시지 본문에서 말한 근거",
    "\"혜택\"·\"할인\"·\"이벤트\"라는 말은 상품정보에 할인·혜택 정보가 있을 때만",
    "제목에 숫자를 쓸 때는 상품정보에 있는 숫자만 그대로 씁니다",
    "효능을 특정 성분에 붙일 때는 상품정보에서 그 성분과 함께 적힌 효능만",
    "페르소나의 사용 상황 · 루틴(시간대 · 장소 · 사용 순서)은 메시지를 여는 장면 묘사로만 씁니다",
]
COND = "페르소나의 피부 고민: '말할 수 있는 효과'가 있으면 그 근거 문구로만 잇고, 없으면 효능 설명으로 씁니다"
SKIN = ("'말할 수 있는 효과'가 있으면 그 고민으로 시작하고 근거 문구로 잇습니다. 없으면 페르소나 고민을 꺼내지 말고, "
        "상품정보의 대상 고민 · 피부 타입(concern · skin_type · suitable_for, 이 셋이 없을 때만 target_tags)을 중심으로 씁니다")
REQUIRED_BY_PURPOSE = {  # 목적별 조건부 연결 문장(문장 기준 — 줄 번호가 밀려도 그대로 잡힌다)
    "브랜드/제품 첫소개": c2.REQUIRED_BY_PURPOSE["브랜드/제품 첫소개"] + [COND],
    "신제품 홍보": [COND],
    "베스트셀러 제품 소개": c2.REQUIRED_BY_PURPOSE["베스트셀러 제품 소개"]
    + ["CTA 이유는 본문의 리뷰 수·평점·효능 근거와 잇기", COND],
    "프로모션/이벤트 소개": ["할인율·가격·조건이 있으면 그 수치를 CTA나 바로 앞 문장에"],
    "성분/효능 강조 소개": [COND],
    "피부타입/고민 강조 소개": c2.REQUIRED_BY_PURPOSE["피부타입/고민 강조 소개"] + [
        SKIN, "② 근거 문구로 보여 주는 제품의 해당 기능 (없으면 효능 설명으로만, 해결 · 적합 주장은 하지 않음)",
        "'말할 수 있는 효과'의 고민(없으면 상품정보의 대상 고민 · 피부 타입)을",
        "'말할 수 있는 효과'가 없으면 페르소나 고민을 꺼내지 말고"],
    "라이프스타일/연령대 강조 소개": [
        "fit 안내의 '말할 수 있는 효과 · 특성' 범위에서 왜 맞는지 (안내가 없으면 장면 묘사 + 상품정보의 사용 맥락 · 사용감"],
}
FIT_ONLY = c2.FIT_ONLY + ["근거 문구의 표현을 유지", "'말할 수 있는 효과 · 특성'이 있으면 메시지 앞부분에 써도 됩니다(의무 아님)",
                          "말할 수 있는 효과 (따옴표 안 근거 문구 범위의 효과만 말하고", "연결 불가 (메시지에서 꺼내지 않는다)"]
NOFIT_ONLY = ["연결 안내가 없으므로 페르소나의 고민을 꺼내거나 상품과 잇지 않습니다",
              "'말할 수 있는 효과 · 특성'은 이 경우 없는 것으로 봅니다"]


def check(rendered, path: str) -> list[str]:
    fails = []
    for purpose, item, text in rendered:
        f = c2.flat(text)
        for k in c2.GENERATION_EXCLUDED_FIELDS:
            if f"'{k}'" in text:
                fails.append(f"{path}/{purpose}/{item}: 제외 필드 {k}")
        fails += [f"{path}/{purpose}/{item}: 지운 문장 남음 — {s}" for s in REMOVED if c2.flat(s) in f]
        fails += [f"{path}/{purpose}/{item}: 필수 문장 없음 — {s}" for s in REQUIRED_ALL + REQUIRED_BY_PURPOSE.get(purpose, [])
                  if c2.flat(s) not in f]
        mine, other = (FIT_ONLY, NOFIT_ONLY) if path == "fit" else (NOFIT_ONLY, FIT_ONLY)
        fails += [f"{path}/{purpose}/{item}: 경로 문구 없음 — {s}" for s in mine if c2.flat(s) not in f]
        fails += [f"{path}/{purpose}/{item}: 다른 경로 문구 섞임 — {s}" for s in other if c2.flat(s) in f]
    return fails


def v2_selfcheck(items: list[dict]) -> dict:
    """v2 스냅숏(해시 대조)으로 그려 REMOVED_V3 가 실제로 걸리는지 — 점검이 작동하는지 확인."""
    snap = v3.HERE / "snapshots" / "purpose_prompt_v2.py"
    want = json.loads((v3.HERE / "snapshots" / "hashes_v2.json").read_text(encoding="utf-8"))["purpose_prompt.py"]
    if v3.gg.sha256(snap) != want:
        return {"ok": False, "reason": "v2 스냅숏 해시가 기록과 다름"}
    spec = importlib.util.spec_from_file_location("purpose_prompt_v2_snap", snap)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    pp = mod.PurPosePrompts()
    it = items[0]
    text = c2.flat("\n".join(m.content for b in v3.PURPOSE_BUILDERS.values()
                             for m in getattr(pp, b)(it["product_snapshot"], "톤", persona_info=it["persona_info"])))
    # 목적별 예시는 목적마다 다르므로 7개 목적을 모두 그린 합본에서 찾는다. 'v2 에도 없던' 문구는 제외 대상이 아니다.
    must = [s for s in REMOVED_V3 if s not in ("성분 정보 자세히 보기",)]
    hits = {s: c2.flat(s) in text for s in must}
    return {"ok": all(hits.values()), "missed": [s for s, h in hits.items() if not h]}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    items = load_jsonl(MAIN / "inputs.jsonl")
    cache = load_jsonl(MAIN / "fit_cache.jsonl")
    pid = {it["item_id"]: it["product_snapshot"].get("product_id") for it in items}
    fitter = c2.CachedFitter({pid[c["item_id"]]: pf.FitResult.from_dict(c) for c in cache})
    fit_r = asyncio.run(c2.render(CrmMessageGenerator(persona_fitter=fitter), items))
    nofit_r = asyncio.run(c2.render(CrmMessageGenerator(), items))
    fails = check(fit_r, "fit") + check(nofit_r, "nofit")
    src = v3.gg.PURPOSE_PROMPT.read_text(encoding="utf-8")
    n_ex = src.count('(예: "')
    if n_ex != 1:
        fails.append(f"소스의 '(예: \"' 가 {n_ex}곳(클릭베이트 금지 예시 1곳만 허용)")
    selfc = v2_selfcheck(items)
    if not selfc["ok"]:
        fails.append(f"자기 점검 실패: {selfc}")
    rec = {"checked_at": datetime.now(timezone.utc).isoformat(), "passed": not fails,
           "purpose_prompt": v3.gg.sha256(v3.gg.PURPOSE_PROMPT), "n_prompts": len(fit_r) + len(nofit_r),
           "v2_selfcheck": selfc, "n_fail": len(fails), "fails": sorted(set(fails))[:200]}
    OUT.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"프롬프트 {rec['n_prompts']}개 점검 · 실패 {len(fails)}건 · v2 자기 점검 {selfc['ok']} → {OUT}")
    for f in sorted({x.split(': ', 1)[-1] for x in fails})[:15]:
        print("  ", f)
    if fails:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
