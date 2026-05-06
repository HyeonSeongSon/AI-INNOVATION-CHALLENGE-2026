"""
상품 태그 검증 스크립트

GPT-4o-mini로 전 상품 태그 검증
출력: 원본 JSONL + tag_valid, tag_valid_reason, validation_method 필드 추가
중단 후 재실행 시 이미 처리된 항목은 건너뜀 (체크포인트)
"""

import json
import sys
import re
import time
import argparse
import os

sys.stdout.reconfigure(encoding="utf-8")

from openai import OpenAI

# .env 파일에서 환경변수 로드 (python-dotenv 없이 직접 파싱)
def load_dotenv(path=".env"):
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except FileNotFoundError:
        pass

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", "app", ".env"))

INPUT  = "c:/Users/user/Documents/GitHub/AI-INNOVATION-CHALLENGE-2026/data/product_data_251231.jsonl"
OUTPUT = "c:/Users/user/Documents/GitHub/AI-INNOVATION-CHALLENGE-2026/data/product_data_251231_validated.jsonl"

LLM_SYSTEM_PROMPT = """당신은 뷰티/라이프스타일 상품 데이터 품질 검증 전문가입니다.
상품명과 한줄 소개를 보고, 현재 붙어 있는 태그가 올바른 분류인지 판단하세요.

판단 기준:
- 태그가 상품의 실제 카테고리/용도와 일치하면 valid: true
- 태그가 상품 특성과 명백히 다른 카테고리면 valid: false
- 상품명이나 설명이 부족해 판단하기 어려우면 valid: true (관대하게)

반드시 아래 JSON 형식으로만 응답하세요 (다른 텍스트 없이):
{"valid": true, "reason": "판단 근거 한 문장"}"""


def llm_check(client: OpenAI, product_name: str, tag: str, intro: str) -> tuple[bool, str]:
    prompt = f"상품명: {product_name}\n태그: {tag}\n한줄소개: {intro[:200]}"

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=150,
        temperature=0,
        messages=[
            {"role": "system", "content": LLM_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    text = response.choices[0].message.content.strip()
    match = re.search(r'\{.*?\}', text, re.DOTALL)
    if match:
        result = json.loads(match.group())
        return bool(result.get("valid", True)), result.get("reason", "")
    return True, f"파싱 실패: {text}"


def load_checkpoint(output_path: str) -> dict:
    """이미 처리된 product_id → 결과 딕셔너리 로드"""
    done = {}
    try:
        with open(output_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    d = json.loads(line)
                    if "tag_valid" in d:
                        done[d["product_id"]] = d
    except FileNotFoundError:
        pass
    return done


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=INPUT)
    parser.add_argument("--output", default=OUTPUT)
    parser.add_argument("--delay", type=float, default=0.1, help="API 호출 간 딜레이(초)")
    parser.add_argument("--api-key", default=None, help="OpenAI API 키 (미입력 시 환경변수 OPENAI_API_KEY 사용)")
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("오류: OPENAI_API_KEY가 설정되지 않았습니다.")
        print("  방법1: python validate_product_tags.py --api-key sk-...")
        print("  방법2: .env 파일에 OPENAI_API_KEY=sk-... 추가")
        sys.exit(1)

    client = OpenAI(api_key=api_key)

    # 전체 상품 로드
    products = []
    with open(args.input, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                products.append(json.loads(line))

    # 체크포인트: 이미 처리된 항목 로드
    done = load_checkpoint(args.output)
    remaining = [p for p in products if p["product_id"] not in done]

    print(f"총 {len(products)}개 | 완료 {len(done)}개 | 남은 {len(remaining)}개\n")

    # 이어쓰기 모드로 출력 파일 오픈
    out_f = open(args.output, "a", encoding="utf-8")

    valid_count = sum(1 for d in done.values() if d.get("tag_valid") is True)
    invalid_count = sum(1 for d in done.values() if d.get("tag_valid") is False)

    try:
        for i, product in enumerate(remaining, 1):
            name = product.get("상품명", "")
            tag  = product.get("태그", "")
            intro = product.get("한줄소개") or product.get("문서", "")[:200]

            try:
                valid, reason = llm_check(client, name, tag, intro)
                method = "llm"
            except Exception as e:
                valid, reason, method = None, f"오류: {e}", "error"

            status = "✅" if valid is True else ("❌" if valid is False else "⚠️")
            if valid is True:
                valid_count += 1
            elif valid is False:
                invalid_count += 1

            product["tag_valid"] = valid
            product["tag_valid_reason"] = reason
            product["validation_method"] = method

            out_f.write(json.dumps(product, ensure_ascii=False) + "\n")
            out_f.flush()

            total_done = len(done) + i
            print(f"[{total_done:03d}/{len(products)}] {status} [{tag}] {name[:40]}")
            if valid is False:
                print(f"       └─ {reason}")

            time.sleep(args.delay)

    finally:
        out_f.close()

    total_processed = len(done) + len(remaining)
    print(f"\n{'='*60}")
    print(f"검증 완료: {total_processed}/{len(products)}개")
    print(f"  ✅ 일치:   {valid_count}개")
    print(f"  ❌ 불일치: {invalid_count}개")
    print(f"\n출력: {args.output}")


if __name__ == "__main__":
    main()
