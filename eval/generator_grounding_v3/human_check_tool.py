"""
사람 확인 채점 화면 — result/dev/v3r/human_check.csv 를 브라우저에서 한 행씩 채운다(human_dev_v3r.py export 결과).

    python human_check_tool.py            # http://127.0.0.1:8771 이 열린다. 누르면 바로 저장된다.
    python human_check_tool.py status     # 남은 빈칸 수

- 칸: 사람(O/X) · 심각도(O일 때) · fit 연결(O/X, 선택) · 메모. 시작할 때 같은 폴더 backup/ 에 백업한다.
- 키보드: o / x 판정 후 다음 행, j / k 다음 / 이전.
- 버전 · 항목 번호는 보여 주지 않는다(키 파일은 열지 않음). 다 채운 뒤 python human_dev_v3r.py summary.
"""

import csv
import json
import os
import shutil
import sys
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import v3_common as v3

CSV_PATH = v3.RESULT / "dev" / "v3r" / "human_check.csv"
PORT = 8771
EDIT = {"v": "사람(O/X)", "sev": "심각도", "fit": "fit 연결(O/X)", "memo": "메모"}
ALLOWED = {"v": ("", "O", "X"), "fit": ("", "O", "X"), "sev": ("", "규제 소지", "오해 유발", "표기")}

PAGE = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>사람 확인</title>
<style>
:root{--bg:#f7f7f5;--panel:#fff;--ink:#1d1d1b;--mute:#6b6b66;--line:#e2e1dc;--o:#2e7d4f;--x:#b4372f;--hl:#fff1a8}
@media (prefers-color-scheme:dark){:root{--bg:#1b1b1a;--panel:#242423;--ink:#ecebe6;--mute:#a3a29c;--line:#3a3a37;--o:#7fcf9f;--x:#ec8a82;--hl:#5a4d10}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 system-ui,"Malgun Gothic",sans-serif}
header{position:sticky;top:0;background:var(--panel);border-bottom:1px solid var(--line);display:flex;gap:10px;align-items:center;padding:8px 16px;flex-wrap:wrap}
main{max-width:900px;margin:0 auto;padding:16px}.card{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:12px 16px;margin-bottom:12px}
h3{margin:0 0 6px;font-size:13px;color:var(--mute)}mark{background:var(--hl);color:inherit}
button{font:inherit;border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:6px;padding:6px 14px;cursor:pointer;margin:2px}
button.on{background:var(--o);color:#fff;border-color:var(--o)}button.onX{background:var(--x);color:#fff;border-color:var(--x)}
input{font:inherit;width:100%;padding:6px 8px;border:1px solid var(--line);border-radius:6px;background:var(--panel);color:var(--ink)}
.saved{color:var(--mute);font-size:12px}.err{color:var(--x);font-weight:600}.rule{font-size:13px}
</style></head><body>
<header><b>사람 확인</b><span id="prog"></span><button id="prev">◀ 이전(k)</button><button id="next">다음(j) ▶</button>
<button id="blank">다음 빈칸</button><span id="saved" class="saved"></span></header><main id="main">불러오는 중…</main>
<script>
let R=[],cur=0;const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const hl=(t,s)=>{t=esc(t);s=esc(s);return s&&t.includes(s)?t.split(s).join(`<mark>${s}</mark>`):t};
async function load(){R=(await (await fetch("/api/data")).json()).rows;const i=R.findIndex(r=>!r.v);cur=i<0?0:i;render()}
async function save(col,val){const r=R[cur];const res=await (await fetch("/api/save",{method:"POST",headers:{"Content-Type":"application/json"},
body:JSON.stringify({row:r.row,col,value:val})})).json();const el=document.getElementById("saved");
if(res.ok){r[col]=val;el.className="saved";el.textContent=`${r.row}행 저장 ${res.saved_at}`}else{el.className="err";el.textContent=res.error}render(false)}
function btns(col,vals){return vals.map(v=>`<button data-c="${col}" data-v="${v}" class="${R[cur][col]===v&&v?(v==="X"?"onX":"on"):""}">${v||"지우기"}</button>`).join("")}
function render(scroll=true){const r=R[cur];const d=R.filter(x=>x.v).length;
document.getElementById("prog").textContent=`${d} / ${R.length} 완료 · ${cur+1}번째`;
document.getElementById("main").innerHTML=`
<div class="card"><h3>${esc(r.row)}행 · ${esc(r.product)} · 유형 <b>${esc(r.type)}</b></h3>
<div><b>${hl(r.title,r.span)}</b></div><div style="margin-top:6px">${hl(r.body,r.span)}</div></div>
<div class="card"><h3>검증기 지적</h3><div><mark>${esc(r.span)}</mark></div><div style="margin-top:6px">${esc(r.reason)}</div>
<h3 style="margin-top:8px">가장 가까운 상품정보</h3><div>${esc(r.closest)}</div></div>
<div class="card"><h3>사람(O/X) — O = 지적이 맞다(근거 없는 주장), X = 지적이 틀렸다</h3>${btns("v",["O","X",""])}
<h3 style="margin-top:8px">심각도(O일 때)</h3>${btns("sev",["규제 소지","오해 유발","표기",""])}
<h3 style="margin-top:8px">fit 연결(O/X, 선택) — 그 주장이 기댄 연결이 상품정보와 같은 뜻이면 O</h3>${btns("fit",["O","X",""])}
<div style="margin-top:6px;font-size:13px">${esc(r.links)}</div>
<div style="margin-top:8px"><input id="memo" placeholder="메모(선택)" value="${esc(r.memo)}"></div></div>
<div class="card rule"><h3>기준</h3>특성어긋남: 제형 · 마무리감 · 흡수 · 사용 단계 · 효능 · 용도를 상품정보와 다르게 씀.<br>
근거없는고민연결: 상품정보에 없는 고민 · 상황에 상품이 해결 · 적합하다고 말함(고민을 말한 바로 뒤에 효과를 붙여 해결을 암시하는 것 포함).<br>
고민에 공감하는 말 자체, 상품정보와 어긋나지 않는 일반 사용감 묘사는 대상 아님(→ X).</div>`;
document.querySelectorAll("button[data-c]").forEach(b=>b.onclick=()=>save(b.dataset.c,b.dataset.v));
const m=document.getElementById("memo");m.onchange=()=>save("memo",m.value);if(scroll)window.scrollTo(0,0)}
function go(d){cur=Math.max(0,Math.min(R.length-1,cur+d));render()}
document.getElementById("prev").onclick=()=>go(-1);document.getElementById("next").onclick=()=>go(1);
document.getElementById("blank").onclick=()=>{for(let k=1;k<=R.length;k++){const i=(cur+k)%R.length;if(!R[i].v){cur=i;render();return}}};
document.addEventListener("keydown",e=>{if(e.target.tagName==="INPUT")return;if(e.key==="j")go(1);else if(e.key==="k")go(-1);
else if(e.key==="o"||e.key==="x")save("v",e.key.toUpperCase()).then(()=>{if(cur<R.length-1)go(1)})});
load();
</script></body></html>"""


def read() -> tuple[list[str], list[dict]]:
    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        rd = csv.DictReader(f)
        return list(rd.fieldnames or []), list(rd)


def write(fields: list[str], rows: list[dict]) -> None:
    tmp = CSV_PATH.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, CSV_PATH)


class Store:
    def __init__(self) -> None:
        self.fields, self.rows = read()

    def payload(self) -> list[dict[str, Any]]:
        return [{"row": r["행"], "product": r["상품명"], "title": r["제목"], "body": r["본문"], "span": r["지적 문구"],
                 "type": r["유형"], "reason": r["검증기 이유"], "closest": r["가장 가까운 상품정보"],
                 "links": r["fit 연결(근거 ← 니즈)"], **{k: r.get(c, "") for k, c in EDIT.items()}} for r in self.rows]

    def save(self, row: str, col: str, value: str) -> str | None:
        r = next((x for x in self.rows if x["행"] == str(row)), None)
        if r is None or col not in EDIT:
            return f"잘못된 요청: {row} {col}"
        value = (value or "").replace("\n", " ").strip()[:300]
        if col in ALLOWED and value not in ALLOWED[col]:
            return f"허용되지 않는 값: {value}"
        old, r[EDIT[col]] = r.get(EDIT[col], ""), value
        try:
            write(self.fields, self.rows)
        except PermissionError:
            r[EDIT[col]] = old
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
                err = store.save(req["row"], req["col"], req.get("value", ""))
            except Exception as e:  # noqa: BLE001
                err = f"저장 오류: {e}"
            body = {"ok": err is None, "error": err, "saved_at": datetime.now().strftime("%H:%M:%S")}
            self._send(200, json.dumps(body, ensure_ascii=False).encode(), "application/json; charset=utf-8")
    return H


def status() -> None:
    _, rows = read()
    done = [r for r in rows if r.get(EDIT["v"])]
    print(f"완료 {len(done)}/{len(rows)} · O {sum(r[EDIT['v']] == 'O' for r in done)} · X {sum(r[EDIT['v']] == 'X' for r in done)}")


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
