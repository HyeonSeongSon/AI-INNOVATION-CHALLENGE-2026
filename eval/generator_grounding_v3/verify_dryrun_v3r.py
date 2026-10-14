"""
v3R fit 사전 점검(비용 0, API 호출 없음) → result/dev/v3r/verify_dryrun.md

    python verify_dryrun_v3r.py            # fitcache 전: 새 verify() 를 저장된 v2 · v3 fit 캐시에 다시 적용
    python verify_dryrun_v3r.py --after    # fitcache 직후 · gen 전: 새 v3r 캐시를 v3 캐시와 지표 비교(덧붙임)

캐시에는 검증 뒤 결과만 있으므로 LLM 원출력을 되살린다: connectable = 남은 것 + 내린 연결,
not_connectable = 캐시 값에서 코드가 덧붙인 니즈(근거 없음 · 필드 · 어휘로 내린 것)를 한 번씩 뺀 것,
conflicts = 남은 것 + 근거 없어 내린 충돌.
판단 규칙(사전 등록): 내려가는 연결 중 실제 모순이 아닌 것이 3개 이상이면 생성 전에 고친다.
되살아나는 연결이 있으면 그 원인 코드를 되돌린다.
"""

import argparse
import sys
from collections import Counter

import v3_common as v3
from v3_common import vc
from gg_common import load_jsonl

from app.agents.generate_message_agent.prompts import persona_fit as pf  # noqa: E402

DEV = v3.RESULT / "dev"
OUT = DEV / "v3r" / "verify_dryrun.md"
APPENDED = ("근거 문구가 상품정보에 없음", "필드는 쓸 수 없음", "겹치지 않음(어휘)")
CONN_KEYS = ("persona_need", "need_type", "product_evidence", "field")


def raw_from_cache(r: dict) -> pf.FitOutput:
    dem = r.get("demoted", [])
    conn = [c for c in r["connectable"]] + [d for d in dem if "need_type" in d]
    left = Counter(d["persona_need"] for d in dem if "need_type" in d and any(a in d["reason"] for a in APPENDED))
    nc = []
    for n in r["not_connectable"]:
        if left[n]:
            left[n] -= 1
        else:
            nc.append(n)
    conf = list(r.get("conflicts", [])) + [d for d in dem if "persona_preference" in d]
    return pf.FitOutput(connectable=[pf.FitConnectable(**{k: c[k] for k in CONN_KEYS}) for c in conn],
                        not_connectable=nc,
                        conflicts=[pf.FitConflict(**{k: c[k] for k in ("persona_preference", "product_fact", "field")})
                                   for c in conf])


def key(c: dict) -> tuple:
    return c["persona_need"], c["product_evidence"]


def replay(name: str, path) -> list[str]:
    snaps = {r["item_id"]: r["product_snapshot"] for r in load_jsonl(vc.RESULT / "main" / "inputs.jsonl")}
    L = [f"## {name} 캐시 ({path.relative_to(v3.HERE.parent).as_posix()})", ""]
    down, up, nc_drop = [], [], []
    for r in load_jsonl(path):
        new = pf.verify(raw_from_cache(r), snaps[r["item_id"]])
        old_k = {key(c) for c in r["connectable"]}
        new_k = {key(c) for c in new.connectable}
        for c in new.demoted:
            if "need_type" in c and key(c) in old_k and key(c) not in new_k:
                down.append((r["item_id"], c["persona_need"], c["need_type"], c["reason"], r["not_connectable"]))
        up += [(r["item_id"], k[0]) for k in new_k - old_k]
        gone = Counter(r["not_connectable"]) - Counter(new.not_connectable)
        nc_drop += [(r["item_id"], n) for n in gone.elements()]
    L += [f"- 새로 내려가는 연결 {len(down)}개 · 되살아나는 연결 {len(up)}개 · 연결 불가에서 빠지는 니즈 {len(nc_drop)}개", ""]
    if down:
        L += ["| 항목 | 니즈 | 종류 | 이유 | 캐시의 연결 불가 | 실제 모순(O/X) |", "|---|---|---|---|---|---|"]
        L += [f"| {i} | {n} | {t} | {why} | {' / '.join(nc)} | |" for i, n, t, why, nc in down]
        L.append("")
    if up:
        L += ["되살아나는 연결(원인 코드를 되돌릴 것): " + "; ".join(f"{i} {n}" for i, n in up), ""]
    if nc_drop:
        L += ["연결 불가에서 빠지는 니즈(검증 통과한 같은 니즈가 연결 가능에 있음, 규칙 ②): "
              + "; ".join(f"{i} {n}" for i, n in nc_drop), ""]
    return L


def stats(path) -> dict:
    rows = load_jsonl(path)
    n = len(rows)
    conn = [c for r in rows for c in r["connectable"]]
    return {"n": n, "mean_conn": sum(len(r["connectable"]) for r in rows) / n,
            "zero_concern": sum(1 for r in rows if not any(c["need_type"] == "concern" for c in r["connectable"])),
            "cap6": sum(1 for r in rows if len(r["connectable"]) >= 6),
            "composite": sum(1 for c in conn if "·" in c["persona_need"] or "/" in c["persona_need"]),
            "ok": sum(r["status"] == "ok" for r in rows)}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--after", action="store_true")
    a = ap.parse_args()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if not a.after:
        L = ["# v3R fit 사전 점검 — 새 verify() 를 저장 캐시에 다시 적용 (비용 0)", "",
             "- v3 캐시와의 차이 = v3R 코드 변경(모순 제거 ① 연결 불가 · ② 중복 니즈)만의 효과.",
             "- v2 캐시와의 차이 = v3 규칙(어휘 · 같은 니즈 충돌) + v3R 규칙의 합.", ""]
        L += replay("v3", DEV / "v3" / "fit_cache.jsonl")
        L += replay("v2", vc.RESULT / "main" / "fit_cache.jsonl")
        OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    else:
        s3, sr = stats(DEV / "v3" / "fit_cache.jsonl"), stats(DEV / "v3r" / "fit_cache.jsonl")
        L = ["", "# fitcache 직후 점검 — 새 v3r 캐시 대 v3 캐시 (gen 전, 비용 0)", "",
             "| 지표 | v3 | v3r |", "|---|---|---|",
             f"| fit ok | {s3['ok']}/{s3['n']} | {sr['ok']}/{sr['n']} |",
             f"| 연결 가능 평균 개수 | {s3['mean_conn']:.2f} | {sr['mean_conn']:.2f} |",
             f"| 고민 연결 0건 항목 | {s3['zero_concern']}/{s3['n']} | {sr['zero_concern']}/{sr['n']} |",
             f"| 상한 6 도달 | {s3['cap6']}/{s3['n']} | {sr['cap6']}/{sr['n']} |",
             f"| 복합 니즈(·, /) | {s3['composite']} | {sr['composite']} |", "",
             f"- 고민 연결 0건이 20/70 이상이면 생성 전에 원인을 본다: {'원인 확인 필요' if sr['zero_concern'] >= 20 else '해당 없음'}"]
        with open(OUT, "a", encoding="utf-8") as f:
            f.write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
