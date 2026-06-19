"""22차 부하테스트 — CloudWatch에서 인프라 레벨 지표를 수집.

ECS CPU/Memory, OpenSearch EC2 CPU(+ _nodes/stats SSM 스냅샷은 별도 실행),
DB 풀 고갈 로그 키워드(CloudWatch Logs Insights)를 한 번에 모아 JSON으로 저장한다.

사용법:
    python fetch_metrics.py --start 2026-06-18T05:00:00Z --end 2026-06-18T05:30:00Z \\
        --output results/metrics_20260618.json

옵션은 전부 인자로 받는다(하드코딩 금지) — 기본값은 이 프로젝트의 현재 리소스 이름.
"""

import argparse
import json
from datetime import datetime, timezone

import boto3

DEFAULT_CLUSTER = "ai-innovation-cluster"
DEFAULT_SERVICES = [
    "ai-innovation-recommend",
    "ai-innovation-generate",
    "ai-innovation-crm",
    "ai-innovation-backend",
]
DEFAULT_LOG_GROUP = "/ecs/ai-innovation"
DEFAULT_OPENSEARCH_INSTANCE_ID = "i-0603d62e9349ea0a9"
DEFAULT_OPENSEARCH_API_INSTANCE_ID = ""  # 25차부터 별도 인스턴스 — 매 테스트 시 현재 ID로 넘겨야 함
DB_POOL_KEYWORDS = "QueuePool|TimeoutError|SQLSTATE|OperationalError|too many clients|remaining connection|PoolTimeout"


def fetch_ecs_metric(cloudwatch, cluster: str, service: str, metric: str, start: datetime, end: datetime) -> dict:
    response = cloudwatch.get_metric_statistics(
        Namespace="AWS/ECS",
        MetricName=metric,
        Dimensions=[
            {"Name": "ClusterName", "Value": cluster},
            {"Name": "ServiceName", "Value": service},
        ],
        StartTime=start,
        EndTime=end,
        Period=60,
        Statistics=["Average", "Maximum"],
    )
    datapoints = sorted(response["Datapoints"], key=lambda d: d["Timestamp"])
    return {
        "datapoint_count": len(datapoints),
        "average_of_averages": (
            sum(d["Average"] for d in datapoints) / len(datapoints) if datapoints else None
        ),
        "max": max((d["Maximum"] for d in datapoints), default=None),
    }


def fetch_ec2_cpu(cloudwatch, instance_id: str, start: datetime, end: datetime) -> dict:
    response = cloudwatch.get_metric_statistics(
        Namespace="AWS/EC2",
        MetricName="CPUUtilization",
        Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
        StartTime=start,
        EndTime=end,
        Period=60,
        Statistics=["Average", "Maximum"],
    )
    datapoints = sorted(response["Datapoints"], key=lambda d: d["Timestamp"])
    return {
        "datapoint_count": len(datapoints),
        "average_of_averages": (
            sum(d["Average"] for d in datapoints) / len(datapoints) if datapoints else None
        ),
        "max": max((d["Maximum"] for d in datapoints), default=None),
    }


def fetch_db_pool_log_matches(logs_client, log_group: str, start: datetime, end: datetime) -> dict:
    query = f'fields @timestamp, @message | filter @message like /{DB_POOL_KEYWORDS}/ | sort @timestamp desc | limit 100'
    start_query = logs_client.start_query(
        logGroupName=log_group,
        startTime=int(start.timestamp()),
        endTime=int(end.timestamp()),
        queryString=query,
    )
    query_id = start_query["queryId"]

    import time

    for _ in range(30):
        result = logs_client.get_query_results(queryId=query_id)
        if result["status"] in ("Complete", "Failed", "Cancelled"):
            break
        time.sleep(1)
    else:
        result = {"status": "Timeout", "results": []}

    matches = [
        {field["field"]: field["value"] for field in row}
        for row in result.get("results", [])
    ]
    return {"status": result.get("status"), "match_count": len(matches), "matches": matches}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, help="ISO8601, 예: 2026-06-18T05:00:00Z")
    parser.add_argument("--end", required=True, help="ISO8601")
    parser.add_argument("--cluster", default=DEFAULT_CLUSTER)
    parser.add_argument("--services", nargs="+", default=DEFAULT_SERVICES)
    parser.add_argument("--log-group", default=DEFAULT_LOG_GROUP)
    parser.add_argument("--opensearch-instance-id", default=DEFAULT_OPENSEARCH_INSTANCE_ID)
    parser.add_argument("--opensearch-api-instance-id", default=DEFAULT_OPENSEARCH_API_INSTANCE_ID)
    parser.add_argument("--region", default="ap-northeast-2")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    start = datetime.fromisoformat(args.start.replace("Z", "+00:00")).astimezone(timezone.utc)
    end = datetime.fromisoformat(args.end.replace("Z", "+00:00")).astimezone(timezone.utc)

    cloudwatch = boto3.client("cloudwatch", region_name=args.region)
    logs_client = boto3.client("logs", region_name=args.region)

    result = {
        "window": {"start": args.start, "end": args.end},
        "ecs": {},
        "opensearch_ec2_cpu": fetch_ec2_cpu(cloudwatch, args.opensearch_instance_id, start, end),
        "opensearch_note": (
            "이 프로젝트의 OpenSearch는 AWS 관리형 서비스가 아니라 EC2 자체 호스팅이라 "
            "AWS/OpenSearch 네임스페이스(JVMMemoryPressure/SearchRate 등)는 존재하지 않는다. "
            "EC2 레벨 CPUUtilization으로 대체했고, 노드 자체의 JVM/스레드풀 상태는 "
            "fetch_opensearch_node_stats.sh(SSM)로 별도 수집해야 한다."
        ),
        "db_pool_log_matches": fetch_db_pool_log_matches(logs_client, args.log_group, start, end),
    }

    if args.opensearch_api_instance_id:
        result["opensearch_api_ec2_cpu"] = fetch_ec2_cpu(
            cloudwatch, args.opensearch_api_instance_id, start, end
        )

    for service in args.services:
        result["ecs"][service] = {
            "CPUUtilization": fetch_ecs_metric(cloudwatch, args.cluster, service, "CPUUtilization", start, end),
            "MemoryUtilization": fetch_ecs_metric(cloudwatch, args.cluster, service, "MemoryUtilization", start, end),
        }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"메트릭 저장 완료: {args.output}")


if __name__ == "__main__":
    main()
