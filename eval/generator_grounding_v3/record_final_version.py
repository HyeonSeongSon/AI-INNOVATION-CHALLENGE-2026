"""
최종 버전 확정 기록 — final_main.py(잠긴 측정 도구)는 이 기록을 읽기만 하므로 쓰기는 여기서 한다.

    python record_final_version.py --version v3r      # v3R 개발 판정(compare.json) 통과 시
    python record_final_version.py --version v1       # 2회 안에 통과가 없을 때(기존 규칙)
    python record_final_version.py --check            # 기록 없이, 마지막 기록과 현재 파일 해시 대조만

- new_hashes 에는 final_main.FINAL_VERSION_FILES 4개만 final_main.rel() 경로로 넣는다. make_generator 가 new_hashes 의
  키를 하나씩 현재 해시와 비교하므로, 목록 밖 키가 있으면 항상 불일치로 멈춘다.
- 운영 서버(generate_server.py) 해시 등 참고 값은 content JSON 안에만 넣는다.
- 최종 버전 규칙 변경(v1 → v3R, v1 대비 품질 요건 제외)은 PREREG_final.md 를 고치지 않고 이 기록에만 남긴다.
"""

import argparse
import json
import sys

import v3_common as v3
from v3_common import gg

import final_main as fm  # noqa: E402
import main_v3 as mv3  # noqa: E402

SERVER = gg.REPO / "backend" / "servers" / "generate_server.py"


def current() -> dict[str, str]:
    return {fm.rel(p): gg.sha256(p) for p in fm.FINAL_VERSION_FILES}


def check() -> None:
    """make_generator 와 같은 비교(생성 없음) + 측정 도구 잠금 대조."""
    fv = fm.final_version()
    now = current()
    bad = [k for k, v in fv["hashes"].items() if now.get(k) != v]
    extra = [k for k in fv["hashes"] if k not in now]
    fm.check_lock()
    if bad or extra:
        raise SystemExit(f"최종 버전 기록(AMENDMENTS {fv['entry']})과 다름: {bad} · 목록 밖 키 {extra}")
    print(f"최종 버전 기록 대조 통과: version={fv['version']} (AMENDMENTS {fv['entry']}) · 측정 도구 잠금 통과")


def record(version: str) -> None:
    fm.check_lock()
    if any(e["kind"] == fm.KIND_FINAL_VERSION for e in gg.amendments_entries()):
        raise SystemExit("이미 '최종 버전 확정' 기록이 있습니다")
    if mv3.is_v3r(version):
        cmp = json.loads((mv3.DEV / version / "compare.json").read_text(encoding="utf-8"))
        if not cmp.get("passed"):
            raise SystemExit(f"{version} 개발 판정 미통과 — 최종 버전으로 기록할 수 없습니다")
        rec = mv3._recorded(version)  # 측정한 파일 그대로인지(생성 전 기록 대조)
        now = mv3.hashes_now()
        bad = [k for k in now if rec.get(k) != now[k]]
        if bad:
            raise SystemExit(f"측정한 {version} 와 현재 파일이 다릅니다: {bad}")
        content = {"version": version,
                   "rule_change": "PREREG_final 의 '최종 버전 = v1' 을 'v3R 이 v2 대비 동시 판정을 통과하면 v3R' 로 바꿈"
                                  "(사용자 결정, 최종 측정 결과 보기 전). v1 대비 품질 요건은 이번 게이트에서 제외했고 v1 은 보고용으로만 씀.",
                   "dev_compare": {k: cmp[k] for k in ("gates", "primary", "all9")},
                   "server_sha": gg.sha256(SERVER),
                   "deploy": "운영 서버 lifespan 에 PersonaFitter 주입(측정 구성과 배포 구성 일치). 피드백 재작성 루프는 측정 밖."}
    elif version == "v1":
        content = {"version": "v1", "rule_change": "v3R 이 2회 안에 통과하지 못해 기존 규칙대로 v1",
                   "server_sha": gg.sha256(SERVER),
                   "deploy": "FINAL_VERSION_FILES 를 576c89c 시점으로 되돌리고 운영 fit 주입은 하지 않음"}
    else:
        raise SystemExit("version 은 v3r · v3r2 · v1 중 하나")
    gg.append_amendment(fm.KIND_FINAL_VERSION, json.dumps(content, ensure_ascii=False), current())
    print("기록함:", content["version"])
    check()


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--version")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        check()
    elif a.version:
        record(a.version)
    else:
        ap.error("--version 또는 --check")


if __name__ == "__main__":
    main()
