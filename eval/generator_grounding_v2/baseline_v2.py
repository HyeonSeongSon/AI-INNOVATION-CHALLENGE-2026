"""
v2 사전 등록 잠금 — v1 생성 전에 한 번 돌린다. 이미 있으면 덮어쓰지 않는다(변경은 AMENDMENTS 로).

기록: purpose_prompt.py(v1 해시여야 함), persona_fit.py · product_fields.py, fit 설정, 게이트 파일 4개,
사전 등록 v2 파일(grounding_def_v2 · measure_v2 · report_v2 · PREREG_v2.md), 검증기 effort.
"""

import json
import sys
from datetime import datetime, timezone

import v2_common as vc

from app.config.settings import settings  # noqa: E402

VERIFIER_EFFORT = "medium"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    if vc.BASELINE_V2.exists():
        raise SystemExit(f"{vc.BASELINE_V2.name} 이 이미 있습니다.")
    v1_hash = json.loads((vc.V1 / "result" / "check_prompts.json").read_text(encoding="utf-8"))["purpose_prompt"]
    now_pp = vc.gg.sha256(vc.gg.PURPOSE_PROMPT)
    if now_pp != v1_hash:
        raise SystemExit("purpose_prompt.py 가 v1 해시가 아닙니다 — v1 생성 전에 잠가야 합니다")
    data = {
        "locked_at": datetime.now(timezone.utc).isoformat(),
        "purpose_prompt_v1": now_pp,
        "persona_fit": vc.gg.sha256(vc.PERSONA_FIT),
        "product_fields": vc.gg.sha256(vc.gg.PRODUCT_FIELDS),
        "fit_settings": {"model": settings.persona_fit_model_name or settings.chatgpt_model_name,
                         "reasoning_effort": settings.persona_fit_reasoning_effort},
        "gate": vc.gg.file_hashes(vc.gg.GATE_FILES),
        "prereg_v2": vc.gg.file_hashes(vc.PREREG_V2_FILES),
        "verifier_effort": VERIFIER_EFFORT,
    }
    vc.BASELINE_V2.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
