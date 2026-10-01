"""
사전 등록 잠금 — 코드를 고치기 전에 한 번 돌린다(1단계 끝).

기록: purpose_prompt.py(수정 전 기준 해시), backend 게이트 파일 4개, 사전 등록 파일(grounding_def.py · measure.py ·
report.py · PREREG.md), 측정 정의 값(POPULARITY_MIN_REVIEWS · GENERATION_EXCLUDED_FIELDS).
이미 잠겨 있으면 덮어쓰지 않는다(--force 금지 — 잠금 뒤 변경은 AMENDMENTS.md 로).
"""

import json
import sys
from datetime import datetime, timezone

import gg_common as gg
import grounding_def as gd


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    if gg.BASELINE.exists():
        raise SystemExit(f"{gg.BASELINE.name} 이 이미 있습니다. 잠금 뒤 변경은 AMENDMENTS.md 에 남깁니다.")
    if "(잠금 전에 결과를 여기에 적습니다)" in (gg.HERE / "PREREG.md").read_text(encoding="utf-8"):
        raise SystemExit("PREREG.md 의 '잠금 전 검증기 시험 결과'가 비어 있습니다. 시험 결과를 적은 뒤 잠급니다.")
    data = {
        "locked_at": datetime.now(timezone.utc).isoformat(),
        "purpose_prompt": gg.sha256(gg.PURPOSE_PROMPT),
        "gate": gg.file_hashes(gg.GATE_FILES),
        "prereg": gg.file_hashes(gg.PREREG_FILES),
        "constants": {"POPULARITY_MIN_REVIEWS": gd.POPULARITY_MIN_REVIEWS,
                      "GENERATION_EXCLUDED_FIELDS": sorted(gd.GENERATION_EXCLUDED_FIELDS)},
    }
    gg.BASELINE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"→ {gg.BASELINE}")


if __name__ == "__main__":
    main()
