"""
무관 근거 확인 도구 — result/fit_effort/irrelevant_check.csv 를 브라우저에서 한 건씩 O/X 로 채운다.

    python fit_check_tool.py            # http://127.0.0.1:8768 이 열린다. 누르면 바로 저장된다.
    python fit_check_tool.py status     # 남은 빈칸 수와 X 비율

- 저장: 같은 CSV 의 '관련(O/X)' · '메모' 열. 시작할 때 fit_effort/backup/ 에 백업한다.
- 키보드: o / x 로 판정, j / k 로 다음 / 이전.
"""

import json
import shutil
import sys
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import v2_common as vc
from gg_common import load_jsonl

import review_kit as rk  # noqa: E402 — read_csv · write_csv_atomic

CSV_PATH = vc.RESULT / "fit_effort" / "irrelevant_check.csv"
PORT = 8768
COL, MEMO = "관련(O/X)", "메모"

PAGE = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>무관 근거 확인</title>
<style>
:root{--bg:#f7f7f5;--panel:#fff;--ink:#1d1d1b;--mute:#6b6b66;--line:#e2e1dc;--accent:#2f5d9e;--o:#2e7d4f;--x:#b4372f;--chip:#eef1f6}
@media (prefers-color-scheme:dark){:root{--bg:#1b1b1a;--panel:#242423;--ink:#ecebe6;--mute:#a3a29c;--line:#3a3a37;--accent:#8db3ec;--o:#7fcf9f;--x:#ec8a82;--chip:#2f3440}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 system-ui,"Malgun Gothic",sans-serif}
header{position:sticky;top:0;background:var(--panel);border-bottom:1px solid var(--line);display:flex;gap:10px;align-items:center;padding:8px 16px;flex-wrap:wrap}
main{max-width:900px;margin:0 auto;padding:16px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:12px 16px;margin-bottom:12px}
h3{margin:0 0 6px;font-size:13px;color:var(--mute)}
.big{font-size:18px;font-weight:700}
.chip{display:inline-block;background:var(--chip);border-radius:4px;padding:0 6px;font-size:12px;margin-right:4px}
button{font:inherit;border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:6px;padding:6px 16px;cursor:pointer}
button.onO{background:var(--o);color:#fff;border-color:var(--o)}button.onX{background:var(--x);color:#fff;border-color:var(--x)}
input[type=text]{font:inherit;width:100%;padding:6px 8px;border:1px solid var(--line);border-radius:6px;background:var(--panel);color:var(--ink)}
.saved{color:var(--mute);font-size:12px}.err{color:var(--x);font-weight:600}
.rule{font-size:13px}kbd{border:1px solid var(--line);border-radius:3px;padding:0 4px;font-size:11px}
</style></head><body>
<header><b>무관 근거 확인</b><span id="prog"></span>
<button id="prev">◀ 이전 <kbd>k</kbd></button><button id="next">다음 <kbd>j</kbd> ▶</button><button id="blank">다음 빈칸</button>
<span id="saved" class="saved"></span></header>
<main id="main">불러오는 중…</main>
<script>
let R=[],cur=0;const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
async function load(){R=(await (await fetch("/api/data")).json()).rows;const i=R.findIndex(r=>!r.v);cur=i<0?0:i;render()}
async function save(col,val){const r=R[cur];const res=await (await fetch("/api/save",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({no:r.no,col,value:val})})).json();
const el=document.getElementById("saved");if(res.ok){if(col==="v")r.v=val;else r.memo=val;el.className="saved";el.textContent=`${r.no}번 저장 ${res.saved_at}`}else{el.className="err";el.textContent=res.error}render(false)}
function prog(){const d=R.filter(r=>r.v).length,x=R.filter(r=>r.v==="X").length;document.getElementById("prog").textContent=`${d} / ${R.length} 완료 · X ${x}건 (${d?Math.round(x*100/d):0}%) · ${cur+1}번째`}
function render(scroll=true){const r=R[cur];document.getElementById("main").innerHTML=`
<div class="card"><h3>${esc(r.no)}번 · ${esc(r.item_id)} · ${esc(r.product)}</h3>
<div class="big"><span class="chip">${esc(r.kind)}</span>${esc(r.need)}</div>
<div style="margin:8px 0">→ 상품정보 근거 <span class="chip">${esc(r.field)}</span><b>${esc(r.evidence)}</b></div>
<div>${["O","X"].map(v=>`<button data-v="${v}" class="${r.v===v?"on"+v:""}">${v==="O"?"O 관련 있음":"X 무관 · 억지"}</button>`).join(" ")} <button data-v="">지우기</button></div>
<div style="margin-top:8px"><input type="text" id="memo" placeholder="메모(선택)" value="${esc(r.memo)}"></div></div>
<div class="card"><h3>페르소나</h3>${esc(r.persona)}</div>
<div class="card rule"><h3>판단 기준</h3><b>O</b>: 근거 문구가 그 고민·선호와 직접 같은 뜻 (예: 입술 건조 → "입술 건조감을 빠르게 완화", 가벼운 제형 → "로션처럼 가벼운 제형")<br>
<b>X</b>: 문구는 상품정보에 있지만 그 고민·선호의 근거로는 무관하거나 억지 (예: 번들거림 → "피부 결 정돈")<br>
X가 15% 이상이면 코드 검증에 단어 겹침 조건을 추가하고 다시 시험합니다.</div>`;
document.querySelectorAll("button[data-v]").forEach(b=>b.onclick=()=>save("v",b.dataset.v));
const m=document.getElementById("memo");m.onchange=()=>save("memo",m.value);prog();if(scroll)window.scrollTo(0,0)}
function go(d){cur=Math.max(0,Math.min(R.length-1,cur+d));render()}
document.getElementById("prev").onclick=()=>go(-1);document.getElementById("next").onclick=()=>go(1);
document.getElementById("blank").onclick=()=>{for(let k=1;k<=R.length;k++){const i=(cur+k)%R.length;if(!R[i].v){cur=i;render();return}}};
document.addEventListener("keydown",e=>{if(e.target.tagName==="INPUT")return;if(e.key==="j")go(1);else if(e.key==="k")go(-1);
else if(e.key==="o"||e.key==="x")save("v",e.key.toUpperCase()).then(()=>{if(cur<R.length-1)go(1)})});
load();
</script></body></html>"""


class Store:
    def __init__(self) -> None:
        self.fields, self.rows = rk.read_csv(CSV_PATH)

    def payload(self) -> list[dict[str, Any]]:
        return [{"no": r["no"], "item_id": r["item_id"], "product": r["상품명"], "persona": r["페르소나"],
                 "need": r["페르소나_고민선호"], "kind": r["종류"], "evidence": r["상품정보_근거"], "field": r["필드"],
                 "v": r.get(COL, ""), "memo": r.get(MEMO, "")} for r in self.rows]

    def save(self, no: str, col: str, value: str) -> str | None:
        row = next((r for r in self.rows if r["no"] == str(no)), None)
        if row is None:
            return f"없는 번호: {no}"
        key = COL if col == "v" else MEMO
        value = (value or "").replace("\n", " ").strip()[:300]
        if key == COL and value not in ("", "O", "X"):
            return f"O/X 가 아닌 값: {value}"
        old = row.get(key, "")
        row[key] = value
        try:
            rk.write_csv_atomic(CSV_PATH, self.fields, self.rows)
        except PermissionError:
            row[key] = old
            return "CSV 가 다른 프로그램(엑셀 등)에서 열려 있어 저장하지 못했습니다. 닫고 다시 누르세요."
        return None


def handler(store: Store):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a: Any) -> None:
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path in ("/", "/index.html"):
                self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
            elif self.path == "/api/data":
                self._send(200, json.dumps({"rows": store.payload()}, ensure_ascii=False).encode(), "application/json; charset=utf-8")
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self) -> None:
            try:
                req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8"))
                err = store.save(req["no"], req["col"], req.get("value", ""))
            except Exception as e:  # noqa: BLE001
                err = f"저장 오류: {e}"
            body = {"ok": err is None, "error": err, "saved_at": datetime.now().strftime("%H:%M:%S")}
            self._send(200, json.dumps(body, ensure_ascii=False).encode(), "application/json; charset=utf-8")
    return H


def status() -> None:
    _, rows = rk.read_csv(CSV_PATH)
    done = [r for r in rows if r.get(COL)]
    x = sum(1 for r in done if r[COL] == "X")
    print(f"완료 {len(done)}/{len(rows)} · X {x}건 ({(x / len(done) * 100 if done else 0):.1f}%) · 판단 기준 15%")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1:] == ["status"]:
        status()
        return
    bk = CSV_PATH.parent / "backup"
    bk.mkdir(exist_ok=True)
    shutil.copy2(CSV_PATH, bk / f"{datetime.now():%Y%m%d-%H%M%S}_{CSV_PATH.name}")
    server = HTTPServer(("127.0.0.1", PORT), handler(Store()))
    url = f"http://127.0.0.1:{PORT}"
    print(f"확인 화면: {url}  (끝낼 때 Ctrl+C)\n저장 위치: {CSV_PATH}", flush=True)
    if "--no-open" not in sys.argv:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        status()


if __name__ == "__main__":
    main()
