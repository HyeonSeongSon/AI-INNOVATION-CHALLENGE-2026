"""
V4 보조 지표 — 근거 있는 개인화 · 짝 층(플랜 '지표 정의').

- 근거 있는 개인화(0/1): 메시지에 승인된 연결의 니즈 표현이나 근거 문구가 들어 있고(전체 일치, 또는 흔한 효능어를 뺀 세 글자 이상
  연속 일치), 검증기 기준 그 메시지에 근거없는고민연결 · 특성어긋남 · 적합대상 지적이 없으면 1.
- 짝 층: 생성 전에 저장한 V4 fit(result/stage1/fit_cache.jsonl)으로 정한다. 고민 연결이 1개 이상이면 "맞는 짝", 0개면 "안 맞는 짝".
  생성물과 무관하게 정해지므로 v0 · v3R · V4 모두 같은 층을 쓴다.
"""

import re

import v4_common as c

COMMON = ("보습", "촉촉", "진정", "수분", "자극", "피부", "사용감", "케어", "개선", "제품", "효과")
BAD_TYPES = ("근거없는고민연결", "특성어긋남", "적합대상")


def _clean(t: str) -> str:
    s = re.sub(r"[^가-힣A-Za-z0-9]", "", t or "")
    for w in COMMON:
        s = s.replace(w, "|")
    return s


def _tri(t: str) -> set:
    return {p[i:i + 3] for p in _clean(t).split("|") for i in range(len(p) - 2)}


def mentions(text: str, link: dict) -> bool:
    sq = re.sub(r"\s+", "", text or "")
    for k in ("persona_need", "product_evidence"):
        v = re.sub(r"\s+", "", link.get(k, ""))
        if v and v in sq:
            return True
    return bool((_tri(link.get("persona_need", "")) | _tri(link.get("product_evidence", ""))) & _tri(text))


def grounded_personalization(m: dict, verifier: dict, fit: dict) -> int:
    text = (m.get("title") or "") + " " + (m.get("message") or "")
    has_link = any(mentions(text, x) for x in fit.get("connectable", []))
    bad = any(cl["type"] in BAD_TYPES for cl in verifier.get("claims", []))
    return int(has_link and not bad)


def v4_fits() -> dict[str, dict]:
    return {r["item_id"]: r for r in c.load_jsonl(c.RESULT / "stage1" / "fit_cache.jsonl")}


def matched(fit: dict) -> bool:
    return any(x["need_type"] == "concern" for x in fit.get("connectable", []))
