"""
최종 측정 사람 확인 도구 — v1 check_tool.py 의 복사본에서 정의 · 기록 칸을 바꾼 것.

    python check_tool_final.py            # 브라우저가 열린다(127.0.0.1:8770). 누르면 바로 저장된다.
    python check_tool_final.py status     # 남은 빈칸 · 근거 문장/유형이 빠진 O 수

v1 대비 바뀐 점
- 화면 정의: grounding_def_v2 의 9개 유형 전체 정의와 경계 사례 전체(헤드라인 지표와 같은 정의).
- 기록 칸: types(9개 유형 중 복수 선택, 쉼표로 저장)를 추가. O 판정은 근거 문장 번호와 유형이 모두 있어야 '완료'로 센다.
- 읽는 파일: HUMAN/check_items.jsonl 만. sample_map.json(조건 · LLM 판정)과 측정 결과는 읽지 않는다.
"""

import json
import re
import shutil
import sys
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import v3_common as v3
from gg_common import load_jsonl

import grounding_def_v2 as gd  # noqa: E402
import review_kit as rk  # noqa: E402 — gg_common 이 eval/quality_gate 경로를 잡은 뒤

from app.core.data_loader import get_brand_tones  # noqa: E402

HUMAN = v3.FINAL / "human"
ITEMS = HUMAN / "check_items.jsonl"
CSV_PATH = HUMAN / "human_check.csv"
BACKUP = HUMAN / "backup"
UI = v3.HERE / "check_tool_final_ui.html"
PORT = 8770
FIELDS = ["code", "unsupported_claim(O/X)", "sentences", "types", "purpose_conveyed(O/X)", "memo"]
EDITABLE = {"unsupported_claim(O/X)": "ox", "purpose_conveyed(O/X)": "ox", "sentences": "text", "types": "types",
            "memo": "text"}


def set_paths(human_dir) -> None:
    """시험(--test)용으로 저장 위치를 바꾼다."""
    global HUMAN, ITEMS, CSV_PATH, BACKUP
    HUMAN = human_dir
    ITEMS, CSV_PATH, BACKUP = HUMAN / "check_items.jsonl", HUMAN / "human_check.csv", HUMAN / "backup"


def ensure_csv(codes: list[str]) -> None:
    if CSV_PATH.exists():
        _, rows = rk.read_csv(CSV_PATH)
        have = {r["code"] for r in rows}
        missing = [c for c in codes if c not in have]
        if missing:
            rows += [{f: (c if f == "code" else "") for f in FIELDS} for c in missing]
            rk.write_csv_atomic(CSV_PATH, FIELDS, rows)
        return
    rk.write_csv_atomic(CSV_PATH, FIELDS, [{f: (c if f == "code" else "") for f in FIELDS} for c in codes])


def row_done(v: dict[str, str]) -> bool:
    """O 는 근거 문장 · 유형이 있어야 완료, X 는 판정만 있으면 완료. 목적 전달도 있어야 한다."""
    u = v.get("unsupported_claim(O/X)", "")
    if u not in ("O", "X") or v.get("purpose_conveyed(O/X)", "") not in ("O", "X"):
        return False
    return u == "X" or bool(v.get("sentences", "").strip() and v.get("types", "").strip())


def payload() -> dict[str, Any]:
    tones = get_brand_tones().get("brand_ton_prompt", {})
    items = []
    for it in load_jsonl(ITEMS):
        ev = rk.original_evidence(it, {}, tones.get(it["brand"], ""))
        snap = {k: v for k, v in it["product_snapshot"].items() if k not in gd.GENERATION_EXCLUDED_FIELDS}
        items.append({"code": it["code"], "purpose": it["purpose"], "brand": it["brand"], "title": it["title"],
                      "message": it["message"], "persona": ev["persona"], "product": ev["product"],
                      "sentences": [{"idx": s["idx"], "text": s["text"],
                                     "matches": [{"field": m["field"], "text": m["text"], "hit": m["hit"]} for m in s["matches"]],
                                     "numbers": [{"n": n["n"], "fields": n["fields"], "brand": n["brand"]} for n in s["numbers"]],
                                     "brand_overlap": s["brand_overlap"]} for s in ev["sentences"]],
                      "brand_profile": ev["brand_profile"], "snapshot": snap})
    return {"definition": gd.GROUNDING_DEF, "boundary": gd.BOUNDARY_CASES, "types": list(gd.CLAIM_TYPES), "items": items}


class Store:
    def __init__(self) -> None:
        self._load()

    def _load(self) -> None:
        _, self.rows = rk.read_csv(CSV_PATH)
        self.mtime = CSV_PATH.stat().st_mtime

    def values(self) -> dict[str, dict[str, str]]:
        return {r["code"]: {f: r.get(f, "") for f in FIELDS[1:]} for r in self.rows}

    def save(self, code: str, col: str, value: str) -> str | None:
        kind = EDITABLE.get(col)
        if kind is None:
            return f"편집할 수 없는 열: {col}"
        value = re.sub(r"[\r\n]+", " / ", value or "").strip()[:500]
        if kind == "ox" and value not in ("", "O", "X"):
            return f"O/X 가 아닌 값: {value}"
        if kind == "types":
            parts = [p.strip() for p in value.split(",") if p.strip()]
            bad = [p for p in parts if p not in gd.CLAIM_TYPES]
            if bad:
                return f"없는 유형: {bad}"
            value = ",".join(t for t in gd.CLAIM_TYPES if t in parts)
        if CSV_PATH.stat().st_mtime != self.mtime:
            self._load()
        row = next((r for r in self.rows if r["code"] == code), None)
        if row is None:
            return f"없는 코드: {code}"
        old = row.get(col, "")
        row[col] = value
        try:
            rk.write_csv_atomic(CSV_PATH, FIELDS, self.rows)
        except PermissionError:
            row[col] = old
            return f"{CSV_PATH.name} 이(가) 다른 프로그램(엑셀 등)에서 열려 있어 저장하지 못했습니다. 닫고 다시 누르세요."
        self.mtime = CSV_PATH.stat().st_mtime
        return None


def handler(store: Store, data: dict[str, Any]):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path in ("/", "/index.html"):
                self._send(200, UI.read_bytes(), "text/html; charset=utf-8")
            elif self.path == "/api/data":
                body = json.dumps({**data, "values": store.values()}, ensure_ascii=False).encode()
                self._send(200, body, "application/json; charset=utf-8")
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self) -> None:
            if self.path != "/api/save":
                self._send(404, b"not found", "text/plain")
                return
            try:
                req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8"))
                err = store.save(req["code"], req["col"], req.get("value", ""))
            except Exception as e:  # noqa: BLE001 — 화면에 이유를 보여 준다
                err = f"저장 오류: {e}"
            body = {"ok": err is None, "error": err, "saved_at": datetime.now().strftime("%H:%M:%S")}
            self._send(200, json.dumps(body, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    return H


def status() -> dict[str, int]:
    _, rows = rk.read_csv(CSV_PATH)
    vals = [{f: r.get(f, "") for f in FIELDS[1:]} for r in rows]
    out = {"total": len(rows), "done": sum(row_done(v) for v in vals),
           "o_missing_evidence": sum(1 for v in vals if v["unsupported_claim(O/X)"] == "O"
                                     and not (v["sentences"].strip() and v["types"].strip()))}
    print(f"완료 {out['done']} / {out['total']} · 근거 문장 또는 유형이 빠진 O {out['o_missing_evidence']}건")
    return out


def serve(open_browser: bool = True) -> None:
    if not ITEMS.exists():
        raise SystemExit(f"{ITEMS} 없음 — human_final.py sample 을 먼저 돌린다")
    codes = [it["code"] for it in load_jsonl(ITEMS)]
    ensure_csv(codes)
    BACKUP.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CSV_PATH, BACKUP / f"{datetime.now():%Y%m%d-%H%M%S}_{CSV_PATH.name}")
    print("근거 계산 중(형태소 분석)…")
    data = payload()
    server = HTTPServer(("127.0.0.1", PORT), handler(Store(), data))
    url = f"http://127.0.0.1:{PORT}"
    print(f"확인 화면: {url}  (끝낼 때 Ctrl+C)\n저장 위치: {CSV_PATH}")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n종료")
        status()


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1:2] == ["status"]:
        ensure_csv([it["code"] for it in load_jsonl(ITEMS)])
        status()
        return
    serve("--no-open" not in sys.argv)


if __name__ == "__main__":
    main()
