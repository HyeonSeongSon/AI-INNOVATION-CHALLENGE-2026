"""
생성기 근거 개선 v2 — 하네스 공통 경로.

v1 하네스(eval/generator_grounding)의 모듈은 import 만 한다. v1 의 잠긴 파일(grounding_def · measure · report ·
PREREG.md)은 고치지 않는다. 기록은 v1 의 AMENDMENTS.md 사슬에 이어 쓴다(gg_common.append_amendment).
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
V1 = HERE.parent / "generator_grounding"
sys.path.insert(0, str(V1))

import gg_common as gg  # noqa: E402,F401 — 경로 · bootstrap · 해시 · AMENDMENTS

RESULT = HERE / "result"
RESULT.mkdir(exist_ok=True)
PREREG_V2 = HERE / "PREREG_v2.md"
BASELINE_V2 = HERE / "baseline_v2.json"
PERSONA_FIT = gg.PROMPTS_DIR / "persona_fit.py"
PREREG_V2_FILES = [HERE / "grounding_def_v2.py", HERE / "measure_v2.py", HERE / "report_v2.py", PREREG_V2]
