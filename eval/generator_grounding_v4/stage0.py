"""
V4 단계 0 — 사전 기록 · 분모 분류 · 사람 재판정 준비.

    python stage0.py record          # 플랜 · 기준표 · 분류 규칙 해시와 수치 기준을 AMENDMENTS 에 기록(결과 보기 전, 1회)
    python stage0.py candidates      # 범주 A · D 분모 후보(수치 · 변화차별 · 특성어긋남 지적) → result/stage0/candidates.jsonl
    python stage0.py denoms          # Claude 1차 분류(DENOM_LABELS) 를 붙여 result/stage0/denominators.csv 로 쓴다(사용자 확인용)
    python stage0.py denoms_lock     # 사용자 확인을 마친 denominators.csv 의 목록 · 건수를 AMENDMENTS 에 기록
    python stage0.py rejudge_export  # 재판정 표(v3R 지적 + 음성 채움 10건, 버전 · 이전 판정 가림) → result/stage0/rejudge.csv
    python stage0.py rejudge_summary # 재판정 결과와 이전 판정의 일치율 · 같은 종류 일관성(보조 기록)
"""

import csv
import json
import random
import sys

import v4_common as c

KIND_RECORD = "V4 사전 기록(단계 0)"
RECORD_CONTENT = (
    "V4 플랜(zippy-moseying-gem, 외부 검토 9회 반영, 사용자 승인 2026-10-06) 결과 보기 전 기록. "
    "목표: 근거 없는 주장을 v3R 의 절반 이하로(입력 차단 · fit 연결 확인 · 생성 뒤 점검), (나) 짝 개인화 회복. "
    "단계 1(b) 기준: 연결 확인 단독 — H 라벨 X 8 중 ≥6 차단, 막힌 H-O 중 기준표 재판정 O(진짜 과잉) ≤ 11/108(usage 성격 제외); "
    "새 fit 정밀도 — N·F 승인 연결 무작위 40개 기준표 O ≥ 90%(점검용); 재현율 대리 (나) 7쌍 + N057 중 ≥ 6/8 고민 연결; "
    "fit + 연결 확인 추가 지연 중앙값(10태스크 × 3회) ≤ 7.0초(사용자 결정). "
    "단계 1(a) 기준(범주별): 분모 양성 ≥ 10(미만이면 결정권자 확인), 재현율(적중 위치가 검증기 지적 문구와 겹칠 때) ≥ 50%, "
    "지적 없는 메시지 중 걸림 ≤ 10%, 켜는 범주 합집합 걸림 ≤ 10%(210건). "
    "단계 2 게이트(N+F 140, v3R 대비, 검증기는 v3R 저장분 — 사용자 결정): 주 지표 ≤ 6 · 짝 비교 악화 ≤ 개선, 9개 유형 ≤ 10, "
    "개인화 단측 90% 하한 > −0.15(비열등, 사용자 결정), CTA · tone · 통과율 · 목적 전달 하한 > −0.15, 재생성 비율 ≤ 10%, 형식 위반 0. "
    "재시도 1회(내용 사전 지정), 미달이면 최종 버전 v3R 유지. "
    "개인화 예측: (가) 약 −0.17 · 공통 언급 짝 약 −0.19 → 최종 전체 비열등(−0.3) 미달 가능성 높음. "
    "최종 시험: v3 최종 절차, v0 대 V4, 채택은 단계 2에서 결정(최종 결과는 채택을 바꾸지 않음), 맞는 짝 층 개인화 2차 사전 등록 지표."
)


def record() -> None:
    if any(e["kind"] == KIND_RECORD for e in c.gg.amendments_entries()):
        raise SystemExit("이미 기록되어 있습니다")
    files = [c.HERE / "PLAN_V4.md", c.HERE / "HUMAN_RUBRIC.md", c.HERE / "DENOM_RULES.md"]
    hashes = {str(p.relative_to(c.gg.REPO)).replace("\\", "/"): c.gg.sha256(p) for p in files}
    e = c.gg.append_amendment(KIND_RECORD, RECORD_CONTENT, hashes)
    print(f"AMENDMENTS {e['id']} 기록: {list(hashes)}")


def candidates() -> list[dict]:
    rows = []
    for key in c.STORED:
        msgs, meas = c.stored(key)
        for iid, m in meas.items():
            for j, cl in enumerate(m["verifier"]["claims"]):
                if cl["type"] not in ("수치", "변화차별", "특성어긋남"):
                    continue
                rows.append({"cid": f"{key}:{iid}:{j}", "set": key, "item_id": iid, "type": cl["type"],
                             "span": cl["span"], "reason": cl["reason"], "closest": cl.get("closest_db_text", ""),
                             "title": msgs[iid]["title"], "message": msgs[iid]["message"]})
    c.write_jsonl(c.STAGE0 / "candidates.jsonl", rows)
    print(f"후보 {len(rows)}개 → {c.STAGE0 / 'candidates.jsonl'}")
    return rows


# Claude 1차 분류(DENOM_RULES.md 기준, AMENDMENTS 22 기록 뒤). 값: (분류, 사유)
DENOM_LABELS = {
    "v3r_N:N001:0": ("제외", "효능 출처 바뀜(원인 ③), 사용 시점 아님"),
    "v3r_N:N014:0": ("D", "드라이 전 · 젖은 모발 ↔ 상품 드라이 후"),
    "v3r_N:N014:1": ("D", "젖은 머리 ↔ 상품 드라이 후"),
    "v3r_N:N031:0": ("A", "비교(결이 다른)"),
    "v3r_N:N035:0": ("D", "드라이 마무리 ↔ 상품 드라이 전"),
    "v3r_N:N035:1": ("D", "드라이 마무리 단계 ↔ 상품 드라이 전"),
    "v3r_N:N035:2": ("제외", "사용량(소량)이지만 유형이 특성어긋남이라 A 대상 유형 아님 · 시점 아님(v3R 부분집합 보고에는 포함)"),
    "v3r_N:N042:0": ("A", "횟수(한 번)"),
    "v3r_F:F026:0": ("D", "메이크업 전 ↔ 상품 메이크업 마무리"),
    "v3r_F:F028:0": ("A", "지속 시간(하루 종일)"),
    "v3r_F:F038:0": ("A", "횟수(한 번)"),
    "v3r_F:F047:0": ("A", "비교(다르게)"),
    "v3r_F:F058:0": ("A", "양(한 스푼)"),
    "v0_F:F002:1": ("A", "비교(기존 밤과 달리)"),
    "v0_F:F003:1": ("A", "비교(다르기)"),
    "v0_F:F007:0": ("A", "지속 시간(오후까지)"),
    "v0_F:F007:2": ("A", "지속 시간(하루 종일)"),
    "v0_F:F008:0": ("A", "빈도(주 2~3회)"),
    "v0_F:F009:0": ("A", "변화(달라졌나)"),
    "v0_F:F015:0": ("A", "빈도(주 3~4회)"),
    "v0_F:F016:0": ("A", "변화(달라졌나)"),
    "v0_F:F022:0": ("A", "양(한 겹)"),
    "v0_F:F023:0": ("A", "비교(더 오래가는)"),
    "v0_F:F027:0": ("A", "양(한 알)"),
    "v0_F:F029:0": ("A", "지속 시간(하루 동안)"),
    "v0_F:F030:0": ("A", "변화(달랐나)"),
    "v0_F:F035:0": ("A", "지속 시간(10분 루틴)"),
    "v0_F:F037:0": ("A", "변화(달라졌나)"),
    "v0_F:F037:2": ("제외", "임상 시험 기간 · 지표 불일치(임상 수치)"),
    "v0_F:F037:3": ("제외", "효능 출처 바뀜(원인 ③)"),
    "v0_F:F043:1": ("D", "샤워 후 ↔ 상품 샤워 중"),
    "v0_F:F050:0": ("A", "비교(차별화된)"),
    "v0_F:F051:0": ("A", "변화(달라진)"),
    "v0_F:F057:0": ("제외", "루틴 단계 수(1~2단계) — 넷 중 해당 없음(경계 사례)"),
    "v0_F:F058:0": ("A", "횟수(한 번이면)"),
    "v0_F:F058:2": ("D", "메이크업 전 ↔ 상품 밤 전용"),
    "v0_F:F063:0": ("제외", "마무리감 어긋남(시점 아님)"),
    "v0_F:F063:1": ("제외", "마무리감 어긋남(시점 아님)"),
    "v0_F:F026:1": ("D", "메이크업 전 ↔ 상품 메이크업 마무리"),
    "v0_F:F065:0": ("A", "변화(달라졌나요)"),
}

DENOM_CSV = c.STAGE0 / "denominators.csv"
DENOM_COLS = ["cid", "유형", "지적 문구", "검증기 이유", "Claude 분류", "사유", "사용자 수정(A/D/제외, 비우면 동의)", "메모"]


def denoms() -> None:
    rows = c.load_jsonl(c.STAGE0 / "candidates.jsonl")
    missing = [r["cid"] for r in rows if r["cid"] not in DENOM_LABELS]
    if missing or len(rows) != len(DENOM_LABELS):
        raise SystemExit(f"분류 누락 {missing} / 후보 {len(rows)} · 분류 {len(DENOM_LABELS)}")
    if DENOM_CSV.exists():
        raise SystemExit(f"{DENOM_CSV} 이 이미 있습니다(사용자 수정 보호)")
    with open(DENOM_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(DENOM_COLS)
        for r in rows:
            lab, why = DENOM_LABELS[r["cid"]]
            w.writerow([r["cid"], r["type"], r["span"], r["reason"], lab, why, "", ""])
    n = {k: sum(v[0] == k for v in DENOM_LABELS.values()) for k in ("A", "D", "제외")}
    print(f"→ {DENOM_CSV} · {n}")


def _final_labels() -> dict[str, str]:
    out = {}
    with open(DENOM_CSV, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            fix = (r[DENOM_COLS[6]] or "").strip()
            if fix and fix not in ("A", "D", "제외"):
                raise SystemExit(f"{r['cid']}: 사용자 수정 값은 A / D / 제외 중 하나")
            out[r["cid"]] = fix or r["Claude 분류"]
    return out


def denoms_lock() -> None:
    if any(e["kind"] == "V4 점검 분모 확정" for e in c.gg.amendments_entries()):
        raise SystemExit("이미 확정되어 있습니다")
    lab = _final_labels()
    changed = sum(1 for k, v in lab.items() if v != DENOM_LABELS[k][0])
    lists = {k: sorted(cid for cid, v in lab.items() if v == k) for k in ("A", "D")}
    content = (f"단계 0 범주 A · D 분모 확정(사용자 확인, Claude 1차 분류에서 {changed}건 수정). "
               f"A {len(lists['A'])}건(v3R {sum(x.startswith('v3r') for x in lists['A'])}), "
               f"D {len(lists['D'])}건(v3R {sum(x.startswith('v3r') for x in lists['D'])}). "
               f"목록: A={lists['A']} D={lists['D']}")
    e = c.gg.append_amendment("V4 점검 분모 확정", content,
                              {str(DENOM_CSV.relative_to(c.gg.REPO)).replace("\\", "/"): c.gg.sha256(DENOM_CSV)})
    print(f"AMENDMENTS {e['id']}: A {len(lists['A'])} · D {len(lists['D'])} · 수정 {changed}")


REJ_CSV = c.STAGE0 / "rejudge.csv"
REJ_KEY = c.STAGE0 / "rejudge_key.json"
REJ_COLS = ["행", "상품명", "제목", "본문", "지적 문구", "유형", "상품정보", "판정", "메모"]
SEED = 20261006


def _product_text(snapshot: dict) -> str:
    from app.agents.generate_message_agent.prompts.product_fields import generation_product_info
    return json.dumps(generation_product_info(snapshot), ensure_ascii=False, indent=1)


def rejudge_export() -> None:
    """v3R 지적(개발 9건 13문구 + 최종 7건 전 문구) + 음성 채움 10건. 버전 · 이전 판정 · 검증기 이유는 가린다."""
    if REJ_CSV.exists():
        raise SystemExit(f"{REJ_CSV} 이 이미 있습니다(판정 보호)")
    nm, nmeas = c.stored("v3r_N")
    fm, fmeas = c.stored("v3r_F")
    rows = []
    # 개발: 이전 사람 확인 행 그대로(지적 문구 단위 판정)
    dkey = json.loads((c.V3_RESULT / "dev" / "v3r" / "human_check_key.json").read_text(encoding="utf-8"))
    with open(c.V3_RESULT / "dev" / "v3r" / "human_check.csv", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            k = dkey[r["행"]]
            if k["version"] != "v3r":
                continue
            m = nm[k["item_id"]]
            rows.append(({"group": "dev", "item_id": k["item_id"], "prev": r["사람(O/X)"]},
                         m, r["지적 문구"], r["유형"]))
    # 최종: 이전 사람 확인은 메시지 단위(7건 모두 X)
    smap = json.loads((c.V3_RESULT / "final" / "human" / "sample_map.json").read_text(encoding="utf-8"))
    prev_final = {}
    with open(c.V3_RESULT / "final" / "human" / "human_check.csv", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            s = smap[r["code"]]
            if s["tag"] == "final":
                prev_final[s["item_id"]] = r["unsupported_claim(O/X)"]
    for iid, me in fmeas.items():
        if me["verifier"]["class"] == "음성":
            continue
        for cl in me["verifier"]["claims"]:
            rows.append(({"group": "final", "item_id": iid, "prev": prev_final.get(iid, "")}, fm[iid], cl["span"], cl["type"]))
    # 음성 채움: v3R 음성 메시지의 '근거 있음' 판정 문구(검증기 supported_claims)
    rng = random.Random(SEED)
    flagged = {k["item_id"] for k, *_ in rows}
    pool = [(iid, msgs[iid], me) for msgs, meas in ((nm, nmeas), (fm, fmeas)) for iid, me in meas.items()
            if me["verifier"]["class"] == "음성" and iid not in flagged and me["verifier"].get("supported_claims")]
    for iid, m, me in rng.sample(pool, 10):
        cl = rng.choice(me["verifier"]["supported_claims"])
        rows.append(({"group": "filler", "item_id": iid, "prev": ""}, m, cl["span"], cl["type"]))
    rng.shuffle(rows)
    key = {}
    with open(REJ_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(REJ_COLS)
        for i, (k, m, span, typ) in enumerate(rows, 1):
            key[str(i)] = {**k, "span": span}
            w.writerow([i, m["product_snapshot"].get("product_name", ""), m["title"], m["message"], span, typ,
                        _product_text(m["product_snapshot"]), "", ""])
    REJ_KEY.write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
    n = {g: sum(k["group"] == g for k in key.values()) for g in ("dev", "final", "filler")}
    print(f"→ {REJ_CSV} {len(rows)}행 {n} (키: {REJ_KEY.name}, 열지 않음)")


def rejudge_summary() -> None:
    key = json.loads(REJ_KEY.read_text(encoding="utf-8"))
    with open(REJ_CSV, encoding="utf-8-sig") as f:
        rows = {r["행"]: r for r in csv.DictReader(f)}
    blank = [i for i, r in rows.items() if not r["판정"]]
    if blank:
        raise SystemExit(f"빈칸 {len(blank)}행")
    out = ["# V4 단계 0 재판정 (보조 기록)", "",
           "- 기준표: HUMAN_RUBRIC.md. 이번 분석에서 각 건의 설명을 이미 봤으므로 완전한 눈가림이 아니다.",
           "- 최종 7건의 이전 판정은 메시지 단위(문구 중 하나라도 O면 O)다.", "",
           "| 묶음 | 항목 | 지적 문구 | 이전 | 재판정 | 메모 |", "|---|---|---|---|---|---|"]
    by_msg: dict[tuple, list[str]] = {}
    agree = {"dev": [0, 0], "final": [0, 0]}
    for i, k in sorted(key.items(), key=lambda x: (x[1]["group"], x[1]["item_id"])):
        r = rows[i]
        out.append(f"| {k['group']} | {k['item_id']} | {k['span']} | {k['prev'] or '-'} | {r['판정']} | {r['메모']} |")
        if k["group"] == "dev":
            agree["dev"][0] += r["판정"] == k["prev"]
            agree["dev"][1] += 1
        elif k["group"] == "final":
            by_msg.setdefault((k["item_id"], k["prev"]), []).append(r["판정"])
    for (iid, prev), vs in by_msg.items():
        now = "O" if "O" in vs else ("애매" if "애매" in vs else "X")
        agree["final"][0] += now == prev
        agree["final"][1] += 1
    fill = [rows[i]["판정"] for i, k in key.items() if k["group"] == "filler"]
    out += ["", f"- 개발(문구 단위) 이전 판정과 일치 {agree['dev'][0]}/{agree['dev'][1]}",
            f"- 최종(메시지 단위) 이전 판정과 일치 {agree['final'][0]}/{agree['final'][1]}",
            f"- 음성 채움 10건: O {fill.count('O')} · X {fill.count('X')} · 애매 {fill.count('애매')}"]
    p = c.STAGE0 / "rejudge_summary.md"
    p.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out[-3:]) + f"\n→ {p}")


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"record": record, "candidates": candidates, "denoms": denoms, "denoms_lock": denoms_lock,
     "rejudge_export": rejudge_export, "rejudge_summary": rejudge_summary}.get(cmd, lambda: print(__doc__))()


if __name__ == "__main__":
    main()
