"""
사람 확인 도구 (7단계) — 눈가림 표본을 한 건씩 보며 근거 없는 상품 사실 주장이 있는지 표시한다.

    python check_tool.py            # 브라우저가 열린다(127.0.0.1:8766). 누르면 바로 저장된다.
    python check_tool.py status     # 남은 빈칸 수

- 읽는 파일: result/human/check_items.jsonl 만. sample_map.json(조건 · LLM 판정)과 measure 결과는 읽지 않는다.
- 저장: result/human/human_check.csv. 시작할 때 human_backup/ 에 백업한다.
- 화면의 정의 문장은 LLM 검증 프롬프트와 같은 grounding_def.definition_text() 이다.
- review_kit 은 고치지 않고 함수만 가져다 쓴다(original_evidence · read_csv · write_csv_atomic · split_sentences).
"""

import json
import re
import shutil
import sys
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import gg_common as gg
import grounding_def as gd
from gg_common import load_jsonl

import review_kit as rk  # noqa: E402 — gg_common 이 eval/quality_gate 경로를 잡은 뒤

from app.core.data_loader import get_brand_tones  # noqa: E402

HUMAN = gg.RESULT / "human"
ITEMS = HUMAN / "check_items.jsonl"
CSV_PATH = HUMAN / "human_check.csv"
BACKUP = HUMAN / "human_backup"
UI = gg.HERE / "check_tool_ui.html"
PORT = 8766
FIELDS = ["code", "unsupported_claim(O/X)", "sentences", "purpose_conveyed(O/X)", "memo"]
EDITABLE = {"unsupported_claim(O/X)": "ox", "purpose_conveyed(O/X)": "ox", "sentences": "text", "memo": "text"}


def ensure_csv(codes: list[str]) -> None:
    if CSV_PATH.exists():
        _, rows = rk.read_csv(CSV_PATH)
        have = {r["code"] for r in rows}
        missing = [c for c in codes if c not in have]
        if missing:  # 확장으로 늘어난 코드만 덧붙인다
            rows += [{f: (c if f == "code" else "") for f in FIELDS} for c in missing]
            rk.write_csv_atomic(CSV_PATH, FIELDS, rows)
        return
    rk.write_csv_atomic(CSV_PATH, FIELDS, [{f: (c if f == "code" else "") for f in FIELDS} for c in codes])


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
    return {"definition": gd.GROUNDING_DEF, "boundary": gd.BOUNDARY_CASES, "items": items}


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


def status() -> None:
    _, rows = rk.read_csv(CSV_PATH)
    for col in ("unsupported_claim(O/X)", "purpose_conveyed(O/X)"):
        print(f"{col}: 빈칸 {sum(1 for r in rows if not r.get(col, '').strip())} / {len(rows)}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    if not ITEMS.exists():
        raise SystemExit(f"{ITEMS} 없음 — human_sample.py 를 먼저 돌린다")
    codes = [it["code"] for it in load_jsonl(ITEMS)]
    ensure_csv(codes)
    if sys.argv[1:] == ["status"]:
        status()
        return
    BACKUP.mkdir(exist_ok=True)
    shutil.copy2(CSV_PATH, BACKUP / f"{datetime.now():%Y%m%d-%H%M%S}_{CSV_PATH.name}")
    print("근거 계산 중(형태소 분석)…")
    data = payload()
    server = HTTPServer(("127.0.0.1", PORT), handler(Store(), data))
    url = f"http://127.0.0.1:{PORT}"
    print(f"확인 화면: {url}  (끝낼 때 Ctrl+C)\n저장 위치: {CSV_PATH}")
    if "--no-open" not in sys.argv:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n종료")
        status()


if __name__ == "__main__":
    main()
