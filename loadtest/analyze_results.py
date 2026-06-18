"""22차 부하테스트 — summary.jsonl + metrics_*.json을 21차 형식의 PASS/FAIL 표로 결합.

사용법:
    python analyze_results.py <result_dir> <metrics_json> > LOAD_TEST_22차_결과_<날짜>.md
"""

import json
import sys
from pathlib import Path

PASS_CRITERIA = {
    "http_200_rate": 0.90,
    "completion_rate": 0.80,
    "p50_sec": 300.0,
    "p99_sec": 600.0,
}


def percentile(data: list[float], p: float) -> float | None:
    if not data:
        return None
    data = sorted(data)
    k = (len(data) - 1) * p
    f, c = int(k), min(int(k) + 1, len(data) - 1)
    return data[f] + (data[c] - data[f]) * (k - f)


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    result_dir = Path(sys.argv[1])
    metrics_path = Path(sys.argv[2])

    records = [json.loads(line) for line in (result_dir / "summary.jsonl").read_text(encoding="utf-8").splitlines()]
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))

    total = len(records)
    http_200 = sum(1 for r in records if r["http_code"] == "200")
    completed = sum(1 for r in records if r["result_status"] == "completed")
    durations = [r["total_sec"] for r in records if r["total_sec"] is not None]

    http_200_rate = http_200 / total if total else 0.0
    completion_rate = completed / total if total else 0.0
    p50 = percentile(durations, 0.50)
    p99 = percentile(durations, 0.99)

    def verdict(value: float | None, threshold: float, higher_is_better: bool) -> str:
        if value is None:
            return "N/A"
        ok = value >= threshold if higher_is_better else value <= threshold
        return "PASS" if ok else "FAIL"

    print("## 22차 수치 결과\n")
    print("| 지표 | 결과 | 기준 | 판정 |")
    print("|------|------|------|------|")
    print(f"| HTTP 200 비율 | {http_200_rate * 100:.1f}% ({http_200}/{total}) | >= 90% | {verdict(http_200_rate, PASS_CRITERIA['http_200_rate'], True)} |")
    print(f"| 파이프라인 완료 (status=completed) | {completion_rate * 100:.1f}% ({completed}/{total}) | >= 80% | {verdict(completion_rate, PASS_CRITERIA['completion_rate'], True)} |")
    print(f"| p50 응답시간 | {p50:.1f}s | <= 300s | {verdict(p50, PASS_CRITERIA['p50_sec'], False)} |" if p50 else "| p50 | N/A | <= 300s | N/A |")
    print(f"| p99 응답시간 | {p99:.1f}s | <= 600s | {verdict(p99, PASS_CRITERIA['p99_sec'], False)} |" if p99 else "| p99 | N/A | <= 600s | N/A |")

    print("\n## 인프라 지표\n")
    print("| 서비스 | CPU 평균 | CPU 최대 | Memory 평균 | Memory 최대 |")
    print("|--------|----------|----------|--------------|--------------|")
    for service, stats in metrics.get("ecs", {}).items():
        cpu = stats.get("CPUUtilization", {})
        mem = stats.get("MemoryUtilization", {})
        print(
            f"| {service} | {cpu.get('average_of_averages', 'N/A')} | {cpu.get('max', 'N/A')} "
            f"| {mem.get('average_of_averages', 'N/A')} | {mem.get('max', 'N/A')} |"
        )

    os_cpu = metrics.get("opensearch_ec2_cpu", {})
    print(f"\nOpenSearch EC2 CPU — 평균: {os_cpu.get('average_of_averages', 'N/A')}, 최대: {os_cpu.get('max', 'N/A')}")
    print(f"\n> {metrics.get('opensearch_note', '')}")

    db_matches = metrics.get("db_pool_log_matches", {})
    print(f"\nDB 풀 고갈 로그 매칭: {db_matches.get('match_count', 'N/A')}건 (상태: {db_matches.get('status', 'N/A')})")


if __name__ == "__main__":
    main()
