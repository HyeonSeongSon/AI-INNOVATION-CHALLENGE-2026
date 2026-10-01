"""
생성기 근거 개선 v3 + 최종 측정 — 하네스 공통 경로.

v1(eval/generator_grounding) · v2(eval/generator_grounding_v2) 하네스의 모듈은 import 만 한다. 두 라운드의 잠긴
파일(grounding_def · measure · report · PREREG.md, grounding_def_v2 · measure_v2 · report_v2 · PREREG_v2.md)은 고치지 않는다.
기록은 v1 의 AMENDMENTS.md 사슬에 이어 쓴다(gg_common.append_amendment).
"""

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
V2 = HERE.parent / "generator_grounding_v2"
sys.path.insert(0, str(V2))

import v2_common as vc  # noqa: E402 — v1 경로도 함께 잡는다
from v2_common import gg  # noqa: E402

RESULT = HERE / "result"
RESULT.mkdir(exist_ok=True)
FINAL = RESULT / "final"
PREREG_FINAL = HERE / "PREREG_final.md"
BASELINE_FINAL = HERE / "baseline_final.json"
GEN_CRM = gg.REPO / "backend" / "app" / "agents" / "generate_message_agent" / "services" / "generate_crm_message.py"
PURPOSE_REL = "backend/app/agents/generate_message_agent/prompts/purpose_prompt.py"

V0_COMMIT = "e967b13"  # 1라운드 전 프롬프트(LF 해시 = baseline_hashes.json 의 purpose_prompt)
V1_COMMIT = "576c89c"  # 1라운드 수정 프롬프트(해시 = baseline_v2.json 의 purpose_prompt_v1)

PURPOSE_BUILDERS = {
    "브랜드/제품 첫소개": "build_purpose_introduction_prompt",
    "신제품 홍보": "build_purpose_new_products_prompt",
    "베스트셀러 제품 소개": "build_purpose_bestseller_prompt",
    "프로모션/이벤트 소개": "build_purpose_promotion_and_event_prompt",
    "성분/효능 강조 소개": "build_purpose_ingredient_efficacy_point_prompt",
    "피부타입/고민 강조 소개": "build_purpose_skintype_and_concern_point_prompt",
    "라이프스타일/연령대 강조 소개": "build_purpose_lifestyle_and_age_point_prompt",
}


def git_prompt_module(commit: str, expected_sha: str, name: str):
    """git 의 purpose_prompt.py 를 임시 모듈로 불러 PurPosePrompts 인스턴스를 돌려준다(해시 대조, CRLF 정규화 허용)."""
    src = subprocess.run(["git", "show", f"{commit}:{PURPOSE_REL}"], cwd=gg.REPO, capture_output=True, check=True).stdout
    lf = src.replace(b"\r\n", b"\n")
    crlf = lf.replace(b"\n", b"\r\n")
    if expected_sha not in (hashlib.sha256(lf).hexdigest(), hashlib.sha256(crlf).hexdigest()):
        raise SystemExit(f"{commit} 의 purpose_prompt.py 가 기대 해시({expected_sha[:12]})와 다릅니다")
    d = tempfile.mkdtemp()
    p = Path(d) / f"{name}.py"
    p.write_bytes(src)
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.PurPosePrompts()


def v0_sha() -> str:
    return json.loads(gg.BASELINE.read_text(encoding="utf-8"))["purpose_prompt"]


def v1_sha() -> str:
    return json.loads(vc.BASELINE_V2.read_text(encoding="utf-8"))["purpose_prompt_v1"]
