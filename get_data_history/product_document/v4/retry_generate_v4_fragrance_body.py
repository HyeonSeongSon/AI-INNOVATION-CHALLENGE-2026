import asyncio
import json
import sys
from pathlib import Path

# 기존 경로 및 환경 설정 유지
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from get_data_history.product_document.v4.prompts_group_a import build_group_a_prompt
from get_data_history.product_document.v4.prompts_group_c import build_group_c_prompt
from backend.app.core.llm_factory import get_llm
from backend.app.config.settings import Settings
from langchain_core.messages import HumanMessage

# 상속받은 설정 (기존 스크립트와 동일하게 유지)
DATA_DIR    = Path(__file__).parent.parent.parent.parent / "data"
OUTPUT_DIR  = Path(__file__).parent
INPUT_FILE  = DATA_DIR / "v3_product_data_rewritten_fragrance_body.jsonl"
OUTPUT_FILE = OUTPUT_DIR / "v4_product_data_fragrance_body.jsonl"
CONCURRENCY = 5  # 재시도시에는 안정성을 위해 약간 낮춤

# ──────────────────────────────────────────────
# 1. 재시도 대상 리스트 설정
# ──────────────────────────────────────────────
# 여기에 실패했던 product_id를 넣으세요.
RETRY_PRODUCT_IDS = {
    "A20251200063", 
    "A20251200064"
}

# 또는 failed_v4_fragrance_body.jsonl 파일에서 자동으로 읽어오고 싶다면 아래 주석을 해제하세요.
# def load_failed_ids():
#     failed_path = OUTPUT_DIR / "failed_v4_fragrance_body.jsonl"
#     if not failed_path.exists(): return set()
#     with open(failed_path, "r", encoding="utf-8") as f:
#         return {json.loads(line)["product_id"] for line in f if line.strip()}
# RETRY_PRODUCT_IDS = load_failed_ids()

# ──────────────────────────────────────────────
# 기존 함수들 (resolve_group, validate_response 등은 원본과 동일하게 유지)
# ──────────────────────────────────────────────
from run_generate_v4_fragrance_body import (
    resolve_group, validate_response, parse_llm_json, 
    build_input_document, _call_llm_and_validate, generate_product
)

# _call_llm_and_validate나 generate_product 내부 로직이 
# run_generate_v4_fragrance_body.py에 정의되어 있으므로 임포트해서 사용합니다.

async def main() -> None:
    if not RETRY_PRODUCT_IDS:
        print("재시도할 product_id가 없습니다.")
        return

    # 1. 전체 데이터 중 대상만 로드
    todo = []
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        for line in f:
            p = json.loads(line)
            if p.get("product_id") in RETRY_PRODUCT_IDS:
                todo.append(p)

    print(f"재시도 대상: {len(todo)}개 (입력된 ID: {len(RETRY_PRODUCT_IDS)}개)")

    if not todo:
        print("입력 파일에서 해당 ID들을 찾을 수 없습니다.")
        return

    # 2. LLM 처리 실행
    semaphore = asyncio.Semaphore(CONCURRENCY)
    tasks = [
        generate_product(p, semaphore, i + 1, len(todo))
        for i, p in enumerate(todo)
    ]
    results = await asyncio.gather(*tasks)

    succeeded = [r for r, ok in results if ok]
    failed = [r for r, ok in results if not ok]

    # 3. 결과 기록 (기존 파일에 Append)
    if succeeded:
        with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
            for r in succeeded:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"\n성공 {len(succeeded)}건 기존 파일({OUTPUT_FILE.name})에 추가 완료.")

    if failed:
        # 실패 리스트는 덮어쓰지 않고 기록 확인용으로 출력
        print(f"여전히 실패한 ID: {[r['product_id'] for r in failed]}")

if __name__ == "__main__":
    async def run_retry():
        # 원본 스크립트에서 llm 객체를 가져오기 위해 전역 설정 확인 필요
        # 만약 import 시 문제가 발생한다면 llm 정의를 이 파일에 복사해서 사용하세요.
        await main()

    asyncio.run(run_retry())