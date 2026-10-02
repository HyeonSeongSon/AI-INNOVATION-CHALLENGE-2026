"""
v3R2 플랜 1단계 — 개발 표본 주 지표 양성 사람 확인(v3R 9건 + v2 7건).

    python human_dev_v3r.py export     # result/dev/v3r/human_check.csv(버전 · 항목 없음, 섞음) + human_check_key.json
    python human_dev_v3r.py summary    # 채운 CSV 와 키를 합쳐 result/dev/v3r/human_check.md

행 = 검증기가 주 지표 유형(특성어긋남 · 근거없는고민연결)으로 지적한 주장 하나.
'사람(O/X)' 칸: O = 지적이 맞다(상품정보에 근거가 없는 주장), X = 지적이 틀렸다(근거 있음 · 문제없는 표현).
'심각도' 칸(O일 때): 규제 소지 · 오해 유발 · 표기.
'fit 연결(O/X)' 칸(선택): 그 주장이 기댄 fit 연결이 상품정보와 같은 뜻이면 O, 아니면 X.
버전 · 항목 번호는 키 파일에만 둔다(행 순서는 시드 20261020 으로 섞음). 항목 일부를 대화에서 본 적이 있어 눈가림은 불완전하다.
사람 반영 수치는 보고용이고 게이트 판정은 LLM 수치로 한다.
"""

import csv
import json
import random
import sys

import v3_common as v3
from v3_common import vc
from gg_common import load_jsonl

import measure as m1  # noqa: E402
import grounding_def_v2 as gd  # noqa: E402

DEV = v3.RESULT / "dev"
OUT = DEV / "v3r" / "human_check.csv"
KEY = DEV / "v3r" / "human_check_key.json"
MD = DEV / "v3r" / "human_check.md"
SEED = 20261020
COLS = ["행", "상품명", "제목", "본문", "지적 문구", "유형", "검증기 이유", "가장 가까운 상품정보", "fit 연결(근거 ← 니즈)",
        "사람(O/X)", "심각도", "fit 연결(O/X)", "메모"]

SRC = {"v2": (vc.RESULT / "main" / "v2", vc.RESULT / "main" / "fit_cache.jsonl"),
       "v3r": (DEV / "v3r", DEV / "v3r" / "fit_cache.jsonl")}


def export() -> None:
    if OUT.exists():
        raise SystemExit(f"{OUT} 이 이미 있습니다(채운 내용을 덮어쓰지 않음)")
    rows = []
    for ver, (d, fitp) in SRC.items():
        msgs = {r["item_id"]: r for r in load_jsonl(d / "messages.jsonl")}
        fits = {r["item_id"]: r for r in load_jsonl(fitp)}
        for r in load_jsonl(d / "measure.jsonl"):
            v = r["verifier"]
            if not v["primary_positive"]:
                continue
            m, f = msgs[r["item_id"]], fits.get(r["item_id"], {})
            links = " / ".join(f"'{c['product_evidence'][:40]}' ← {c['persona_need']}({'고민' if c['need_type'] == 'concern' else '선호'})"
                               for c in f.get("connectable", []))
            for c in v["claims"]:
                if c.get("type") not in gd.PRIMARY_TYPES:
                    continue
                rows.append({"_ver": ver, "_item": r["item_id"], "상품명": m["product_snapshot"].get("product_name", ""),
                             "제목": m["title"], "본문": m["message"], "지적 문구": c.get("span", ""), "유형": c["type"],
                             "검증기 이유": c.get("reason", ""), "가장 가까운 상품정보": c.get("closest_db_text", ""),
                             "fit 연결(근거 ← 니즈)": links, "사람(O/X)": "", "심각도": "", "fit 연결(O/X)": "", "메모": ""})
    random.Random(SEED).shuffle(rows)
    key = {}
    for n, r in enumerate(rows, 1):
        r["행"] = n
        key[n] = {"version": r.pop("_ver"), "item_id": r.pop("_item")}
    with open(OUT, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    KEY.write_text(json.dumps(key, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(rows)}행 → {OUT}\n키 → {KEY} (채점 끝날 때까지 열지 않는다)")


def summary() -> None:
    key = {int(k): v for k, v in json.loads(KEY.read_text(encoding="utf-8")).items()}
    rows = list(csv.DictReader(open(OUT, encoding="utf-8-sig")))
    empty = [r["행"] for r in rows if r["사람(O/X)"].strip().upper() not in ("O", "X")]
    if empty:
        raise SystemExit(f"'사람(O/X)' 빈 행: {empty}")
    by = {}
    for r in rows:
        k = key[int(r["행"])]
        by.setdefault((k["version"], k["item_id"]), []).append(r)
    L = ["# 개발 표본 주 지표 양성 사람 확인 — v2 7건 · v3R 9건", "",
         "- 메시지는 지적 중 하나라도 사람 O 이면 사람 기준 양성. 보고용(게이트 판정은 LLM 수치).", "",
         "| 버전 | LLM 양성 메시지 | 사람 기준 양성 메시지 | 지적 O / 전체 |", "|---|---|---|---|"]
    for ver in ("v2", "v3r"):
        ks = [k for k in by if k[0] == ver]
        pos = [k for k in ks if any(r["사람(O/X)"].strip().upper() == "O" for r in by[k])]
        cl = [r for k in ks for r in by[k]]
        L.append(f"| {ver} | {len(ks)} | {len(pos)} | {sum(r['사람(O/X)'].strip().upper() == 'O' for r in cl)}/{len(cl)} |")
    L += ["", "| 버전 | 항목 | 지적 문구 | 사람 | 심각도 | fit 연결 | 메모 |", "|---|---|---|---|---|---|---|"]
    for (ver, iid), rs in sorted(by.items()):
        for r in rs:
            L.append(f"| {ver} | {iid} | {r['지적 문구']} | {r['사람(O/X)']} | {r['심각도']} | {r['fit 연결(O/X)']} | {r['메모']} |")
    MD.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    {"export": export, "summary": summary}[sys.argv[1]]()
