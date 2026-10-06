"""
최종 시험의 v0 전용 생성기 — V4 이전 동작을 그대로 쓴다(운영 코드는 건드리지 않는다).

V4 의 운영 생성기는 fitter 가 없어도 페르소나를 거르고 생성 뒤 점검 · 재생성을 하므로, v3 최종처럼 CrmMessageGenerator() 에
v0 프롬프트만 끼우면 v0 가 오염된다. 그래서 v3R 스냅숏(snapshots/generate_crm_message_v3r.py)의 CrmMessageGenerator 클래스를
그대로 불러 프롬프트 맵만 v0(e967b13)로 바꾼다. 스냅숏은 hashes_v3r.json 과 해시를 대조한다.
"""

import importlib.util
import json
import sys

import v4_common as c

SNAP = c.V3 / "snapshots" / "generate_crm_message_v3r.py"
SNAP_HASHES = c.V3 / "snapshots" / "hashes_v3r.json"
PKG = "app.agents.generate_message_agent.services._snap_v3r"


def _load_snapshot_module():
    want = json.loads(SNAP_HASHES.read_text(encoding="utf-8"))["generate_crm_message.py"]
    if c.gg.sha256(SNAP) != want:
        raise SystemExit("v3R 스냅숏 해시가 hashes_v3r.json 과 다릅니다")
    if PKG in sys.modules:
        return sys.modules[PKG]
    import app.agents.generate_message_agent.services  # noqa: F401 — 상대 import 의 부모 패키지
    spec = importlib.util.spec_from_file_location(PKG, SNAP)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[PKG] = mod
    spec.loader.exec_module(mod)
    return mod


def make_v0_generator():
    mod = _load_snapshot_module()
    gen = mod.CrmMessageGenerator()  # fitter 없음 → 원본 페르소나를 그대로 넣는 V4 이전 경로, 생성 뒤 점검 없음
    pp = c.v3.git_prompt_module(c.v3.V0_COMMIT, c.v3.v0_sha(), "purpose_prompt_v0")
    gen._purpose_prompt_map = {p: getattr(pp, b) for p, b in c.v3.PURPOSE_BUILDERS.items()}
    return gen, f"v0({c.v3.V0_COMMIT}, v3R 스냅숏 생성기)"
