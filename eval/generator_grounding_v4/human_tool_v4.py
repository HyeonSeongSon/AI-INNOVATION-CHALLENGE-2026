"""
V4 사람 판정 화면 — CSV 한 행씩 기준표(HUMAN_RUBRIC.md)로 판정한다. 누르면 바로 저장된다.

    python human_tool_v4.py <csv 경로> [--port 8771] [--no-open]
    python human_tool_v4.py <csv 경로> status

- 편집 칸: "판정"(O / X / 애매) · "메모". 나머지 칸은 읽기 전용으로 위에서부터 보여 준다.
- "지적 문구" 칸이 있으면 제목 · 본문에서 그 문구를 강조한다.
- 버전 · 항목 번호 · 이전 판정은 CSV 에 넣지 않는다(키 파일은 따로, 열지 않음).
- 키보드: o / x / a(애매) 판정 후 다음 행, j / k 다음 / 이전.
- 오래 켜 둘 때는 WMI(Invoke-CimMethod Win32_Process Create)로 띄운다(도구 프로세스가 끝나도 유지).
"""

import csv
import json
import os
import shutil
import sys
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

EDIT = ("판정", "메모")
ALLOWED = {"판정": ("", "O", "X", "애매")}
HIDE = {"행"}
RUBRIC = (Path(__file__).resolve().parent / "HUMAN_RUBRIC.md").read_text(encoding="utf-8")

PAGE = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>V4 사람 판정</title>
<style>
:root{--bg:#f7f7f5;--panel:#fff;--ink:#1d1d1b;--mute:#6b6b66;--line:#e2e1dc;--o:#2e7d4f;--x:#b4372f;--a:#8a6d1f;--hl:#fff1a8}
@media (prefers-color-scheme:dark){:root{--bg:#1b1b1a;--panel:#242423;--ink:#ecebe6;--mute:#a3a29c;--line:#3a3a37;--o:#7fcf9f;--x:#ec8a82;--a:#e0c46a;--hl:#5a4d10}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 system-ui,"Malgun Gothic",sans-serif}
header{position:sticky;top:0;background:var(--panel);border-bottom:1px solid var(--line);display:flex;gap:10px;align-items:center;padding:8px 16px;flex-wrap:wrap;z-index:1}
main{max-width:920px;margin:0 auto;padding:16px}.card{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:12px 16px;margin-bottom:12px}
h3{margin:0 0 4px;font-size:13px;color:var(--mute)}mark{background:var(--hl);color:inherit}.val{white-space:pre-wrap;word-break:break-word}
.long{max-height:260px;overflow:auto;font-size:13px}
button{font:inherit;border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:6px;padding:6px 14px;cursor:pointer;margin:2px}
button.O{background:var(--o);color:#fff;border-color:var(--o)}button.X{background:var(--x);color:#fff;border-color:var(--x)}button.A{background:var(--a);color:#fff;border-color:var(--a)}
input{font:inherit;width:100%;padding:6px 8px;border:1px solid var(--line);border-radius:6px;background:var(--panel);color:var(--ink)}
.saved{color:var(--mute);font-size:12px}.err{color:var(--x);font-weight:600}details{font-size:13px}
</style></head><body>
<header><b>V4 사람 판정</b><span id="prog"></span><button id="prev">◀ 이전(k)</button><button id="next">다음(j) ▶</button>
<button id="blank">다음 빈칸</button><span id="saved" class="saved"></span></header><main id="main">불러오는 중…</main>
<script>
let R=[],F=[],RUB="",cur=0;const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const hl=(t,s)=>{t=esc(t);s=esc(s);return s&&t.includes(s)?t.split(s).join(`<mark>${s}</mark>`):t};
async function load(){const d=await (await fetch("/api/data")).json();R=d.rows;F=d.fields;RUB=d.rubric;const i=R.findIndex(r=>!r["판정"]);cur=i<0?0:i;render()}
async function save(col,val){const r=R[cur];const res=await (await fetch("/api/save",{method:"POST",headers:{"Content-Type":"application/json"},
body:JSON.stringify({row:r["행"],col,value:val})})).json();const el=document.getElementById("saved");
if(res.ok){r[col]=val;el.className="saved";el.textContent=`${r["행"]}행 저장 ${res.saved_at}`}else{el.className="err";el.textContent=res.error}render(false)}
function render(scroll=true){const r=R[cur];const d=R.filter(x=>x["판정"]).length;const span=r["지적 문구"]||"";
document.getElementById("prog").textContent=`${d} / ${R.length} 완료 · ${cur+1}번째`;
const cards=F.filter(f=>!["행","판정","메모"].includes(f)).map(f=>{const v=r[f]||"";const long=v.length>400;
const body=(f==="제목"||f==="본문")?hl(v,span):(f==="지적 문구"?`<mark>${esc(v)}</mark>`:esc(v));
return `<div class="card"><h3>${esc(f)}</h3><div class="val ${long?"long":""}">${body}</div></div>`}).join("");
const b=v=>`<button data-v="${v}" class="${r["판정"]===v&&v?(v==="애매"?"A":v):""}">${v||"지우기"}</button>`;
document.getElementById("main").innerHTML=cards+`<div class="card"><h3>${F.includes("니즈")?"연결 판정 (o / x / a) — O = 근거 문구가 이 니즈와 같은 결과 · 같은 속성을 말한다 · X = 관련만 있고 같은 말이 아니다":"주장 판정 (o / x / a) — O = 상품정보에 근거 없는 상품 주장이다 · X = 근거가 있다(같은 뜻) 또는 상품 주장이 아니다"}</h3>${["O","X","애매",""].map(b).join("")}
<div style="margin-top:8px"><input id="memo" placeholder="메모(애매일 때 이유 한 줄)" value="${esc(r["메모"])}"></div></div>
<div class="card"><details><summary>기준표 보기</summary><div class="val">${esc(RUB)}</div></details></div>`;
document.querySelectorAll("button[data-v]").forEach(x=>x.onclick=()=>save("판정",x.dataset.v));
const m=document.getElementById("memo");m.onchange=()=>save("메모",m.value);if(scroll)window.scrollTo(0,0)}
function go(d){cur=Math.max(0,Math.min(R.length-1,cur+d));render()}
document.getElementById("prev").onclick=()=>go(-1);document.getElementById("next").onclick=()=>go(1);
document.getElementById("blank").onclick=()=>{for(let k=1;k<=R.length;k++){const i=(cur+k)%R.length;if(!R[i]["판정"]){cur=i;render();return}}};
document.addEventListener("keydown",e=>{if(e.target.tagName==="INPUT")return;if(e.key==="j")go(1);else if(e.key==="k")go(-1);
else if("oxa".includes(e.key)&&e.key){const v={o:"O",x:"X",a:"애매"}[e.key];save("판정",v).then(()=>{if(cur<R.length-1)go(1)})}});
load();
</script></body></html>"""


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        with open(path, encoding="utf-8-sig", newline="") as f:
            rd = csv.DictReader(f)
            self.fields, self.rows = list(rd.fieldnames or []), list(rd)
        missing = [c for c in ("행", *EDIT) if c not in self.fields]
        if missing:
            raise SystemExit(f"CSV 에 칸이 없습니다: {missing}")

    def write(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=self.fields)
            w.writeheader()
            w.writerows(self.rows)
        os.replace(tmp, self.path)

    def save(self, row: str, col: str, value: str) -> str | None:
        r = next((x for x in self.rows if x["행"] == str(row)), None)
        if r is None or col not in EDIT:
            return f"잘못된 요청: {row} {col}"
        value = (value or "").replace("\n", " ").strip()[:300]
        if col in ALLOWED and value not in ALLOWED[col]:
            return f"허용되지 않는 값: {value}"
        old, r[col] = r.get(col, ""), value
        try:
            self.write()
        except PermissionError:
            r[col] = old
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
                body = {"rows": store.rows, "fields": store.fields, "rubric": RUBRIC}
                self._send(200, json.dumps(body, ensure_ascii=False).encode(), "application/json; charset=utf-8")
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self) -> None:
            try:
                req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8"))
                err = store.save(req["row"], req["col"], req.get("value", ""))
            except Exception as e:  # noqa: BLE001
                err = f"저장 오류: {e}"
            body = {"ok": err is None, "error": err, "saved_at": datetime.now().strftime("%H:%M:%S")}
            self._send(200, json.dumps(body, ensure_ascii=False).encode(), "application/json; charset=utf-8")
    return H


def status(path: Path) -> None:
    st = Store(path)
    v = [r["판정"] for r in st.rows]
    print(f"완료 {sum(bool(x) for x in v)}/{len(v)} · O {v.count('O')} · X {v.count('X')} · 애매 {v.count('애매')}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    path = Path(sys.argv[1]).resolve()
    if "status" in sys.argv[2:]:
        status(path)
        return
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8771
    store = Store(path)
    bk = path.parent / "backup"
    bk.mkdir(exist_ok=True)
    shutil.copy2(path, bk / f"{datetime.now():%Y%m%d-%H%M%S}_{path.name}")
    server = HTTPServer(("127.0.0.1", port), handler(store))
    url = f"http://127.0.0.1:{port}"
    print(f"판정 화면: {url}  (끝낼 때 Ctrl+C)\n저장 위치: {path}", flush=True)
    if "--no-open" not in sys.argv:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        status(path)


if __name__ == "__main__":
    main()
