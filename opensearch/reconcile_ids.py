"""
DB ↔ OpenSearch product_id 정합성 점검 (읽기 전용, 보고만 — 삭제·재색인 같은 교정은 하지 않는다)

배경: 시드 이후 등록·삭제가 한쪽에만 반영되면 건수는 같아도 ID 집합이 달라질 수 있다
(과거: DB·OS가 같은 상품에 서로 다른 product_id를 붙여 260쌍이 고아/미색인으로 갈라짐).
그래서 건수가 아니라 product_id **집합 diff 양방향**으로만 판정한다. vectordb_id는 신호로 쓰지 않는다.

표준 라이브러리만 사용한다(OS EC2에는 python3.11만 보장되고 opensearchpy·structlog는 없다).

종료코드: 0 = 일치 · 1 = 불일치 · 2 = 수집 실패/불완전(무결성 불일치 포함)

실행 구조 — 어느 한 호스트에서도 DB와 OS를 동시에 읽을 수 없으므로 수집과 비교를 분리한다.
  (DB API 8020·PG 5432는 ECS만, OS 9200은 opensearch-api EC2만 접근 가능하다.)
  opensearch/ 는 OS EC2의 /opt/opensearch-api 에만 배포된다(DB EC2에는 없음).

  1) DB EC2 (SSM) — 스크립트 없이 psql 한 줄로 수집하고 무결성 trailer를 만든다:
       sudo -u postgres psql -d ai_innovation_db -Atc "select product_id from products" \\
         | LC_ALL=C sort -u > /tmp/db_ids.txt; cat /tmp/db_ids.txt; \\
         echo "count=$(wc -l < /tmp/db_ids.txt) sha256=$(sha256sum < /tmp/db_ids.txt | cut -d' ' -f1)"
  2) OS EC2 (SSM):  python3 /opt/opensearch-api/reconcile_ids.py --collect os
  3) 두 출력을 파일로 저장해 어디서든 비교:
       python reconcile_ids.py --db-ids db_ids.txt --os-ids os_ids.txt

  무결성 trailer: 마지막 줄 `count=N sha256=<hex>`. 해시 대상은 정렬(LC_ALL=C)·중복 제거된 ID를
  줄마다 LF로 끝낸 텍스트(마지막 줄도 LF)다. 로더는 trailer와 내용이 안 맞으면(SSM 출력 한도로 잘림 등)
  종료코드 2로 끝내 잘린 목록이 "고아/미색인"으로 보이지 않게 한다. trailer가 없는 파일은 경고와 함께
  받되 결과에 "무결성 미확인"을 표시한다.

  `--collect db`(DB API 경유)는 스크립트가 DB API에 닿는 곳에서 돌릴 때의 2순위 경로다. GET /products는
  product_created_at 동률 정렬이 불안정할 수 있어 수집 distinct 수가 응답 total과 다르면 종료코드 2로 끝낸다.
  이상이 반복되면 위 psql 경로를 쓴다.

  --files : 레포 체크아웃에서 실행하는 오프라인 점검. v3(DB 시드)·v4(OS 색인) 10쌍의 ID 집합·줄 순서가
    같은지, 중복 ID가 없는지 본다. **재시드 전 필수 확인** — seed_products.py는 100건 단위 commit이
    IntegrityError try 안에 있어 파일에 중복 ID가 있으면 그 100건 묶음이 통째로 롤백되고 skip은 1로만
    집계된다. ID가 랜덤이던 때는 이 경로가 실행된 적이 없었으므로 ID 고정 이후의 새 위험이다.

  --selftest : 내장 mock으로 diff·무결성·종료코드 로직을 검증한다.

  재해 복구 직후 실행한다: restore_or_skip.sh 는 "복원 후 누락분은 DB 기준 reconcile/재색인으로 보완"한다고
  적고 있으며, 이 스크립트가 그 짝이다(누락분을 찾는 것까지만 하고 보완은 사람이 한다).

  주기 실행(cron/EventBridge) 자동화는 현재 구조에선 불가능하다. SG 규칙 추가(DB와 OS를 한 호스트에서 읽기)
  또는 opensearch-api에 ID 목록 엔드포인트 신설이 선행돼야 한다.

토큰·비밀번호는 CLI 인자로 받지 않는다(SSM 명령 문자열은 이력에 남는다). 환경변수 또는
/opt/db-api/.env · /etc/opensearch-admin.env 에서 직접 읽고, 출력·로그에는 남기지 않는다.
"""

import argparse
import base64
import hashlib
import json
import logging
import os
import re
import ssl
import sys
import tempfile
import urllib.request
from pathlib import Path

EXIT_OK, EXIT_MISMATCH, EXIT_FAILED = 0, 1, 2

# 시드(database/seed_products.py SOURCE_FILES)와 색인(index_products_v4_multivector.py DATA_FILES)이
# 같은 순서의 10개라 그대로 대응시킨다.
FILE_PAIRS: list[tuple[str, str]] = [
    ("v3_product_data_rewritten_beauty_tool.jsonl", "v4_product_data_beauty_tool.jsonl"),
    ("v3_product_data_rewritten_color_tone.jsonl", "v4_product_data_color_tone.jsonl"),
    ("v3_product_data_structured_color_tone_add.jsonl", "v4_product_data_color_tone_add.jsonl"),
    ("v3_product_data_rewritten_fragrance_body.jsonl", "v4_product_data_fragrance_body.jsonl"),
    ("v3_product_data_structured_fragrance_body_add.jsonl", "v4_product_data_fragrance_body_add.jsonl"),
    ("v3_product_data_rewritten_hair.jsonl", "v4_product_data_hair.jsonl"),
    ("v3_product_data_rewritten_inner_beauty.jsonl", "v4_product_data_inner_beauty.jsonl"),
    ("v3_product_data_structured_inner_beauty_add.jsonl", "v4_product_data_inner_beauty_add.jsonl"),
    ("v3_product_data_rewritten_living_supplies.jsonl", "v4_product_data_living_supplies.jsonl"),
    ("v3_product_data_rewritten_skincare.jsonl", "v4_product_data_skincare.jsonl"),
]

OS_INDEX = "product_v4_combined"           # 모든 상품이 갖는 필드 인덱스
OS_ADMIN_ENV_FILE = "/etc/opensearch-admin.env"
DB_ENV_FILE = "/opt/db-api/.env"
DB_PAGE_SIZE = 1000                         # 작은 page_size는 페이지마다 정렬 방식이 달라질 수 있어 1000 고정
HTTP_TIMEOUT_SEC = 60
OS_AGG_PAGE_SIZE = 500

_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_TRAILER_RE = re.compile(r"^count=(\d+) sha256=([0-9a-f]{64})$")

logger = logging.getLogger("reconcile_ids")


class CollectionError(Exception):
    """수집 실패 또는 불완전 — 종료코드 2."""


# ---------------------------------------------------------------- ID 텍스트·무결성 trailer

def canonical_text(ids: set[str]) -> str:
    """정렬(바이트 순)·중복 제거·LF 종결 텍스트. psql 경로의 `LC_ALL=C sort -u` 출력과 같다."""
    return "".join(f"{i}\n" for i in sorted(ids, key=lambda s: s.encode()))


def trailer_line(text: str) -> str:
    digest = hashlib.sha256(text.encode()).hexdigest()
    return f"count={text.count(chr(10))} sha256={digest}"


def dump_ids(ids: set[str], out=sys.stdout) -> None:
    text = canonical_text(ids)
    out.write(text)
    out.write(trailer_line(text) + "\n")


def parse_ids_text(raw: str) -> tuple[set[str], bool]:
    """(ID 집합, 무결성 검증 여부). trailer와 내용이 안 맞으면 CollectionError."""
    lines = [ln.rstrip("\r") for ln in raw.split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    verified = False
    if lines and (m := _TRAILER_RE.match(lines[-1])):
        lines.pop()
        text = "".join(f"{ln}\n" for ln in lines)
        if len(lines) != int(m.group(1)) or hashlib.sha256(text.encode()).hexdigest() != m.group(2):
            raise CollectionError("integrity_mismatch: trailer와 내용이 다릅니다(전송 중 잘렸을 수 있음)")
        verified = True
    else:
        logger.warning("trailer_missing 무결성 미확인")
    bad = [ln for ln in lines if not _ID_RE.match(ln)]
    if bad:
        raise CollectionError(f"invalid_id_line count={len(bad)} (ID 형식이 아닌 줄이 섞여 있음)")
    if not lines:
        # 수집 명령이 실패해 빈 출력이 나온 경우 trailer 해시는 유효하므로 별도로 막는다
        raise CollectionError("empty_ids: ID가 하나도 없음(수집 명령 실패 의심)")
    return set(lines), verified


def load_ids_file(path: str) -> tuple[set[str], bool]:
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as e:
        raise CollectionError(f"read_failed type={type(e).__name__} path={path}") from e
    return parse_ids_text(raw)


# ---------------------------------------------------------------- 자격 증명 (환경변수 → env 파일)

def read_secret(name: str, env_file: str) -> str:
    if value := os.environ.get(name):
        return value
    try:
        text = Path(env_file).read_text(encoding="utf-8")
    except OSError as e:
        raise CollectionError(f"secret_missing name={name} type={type(e).__name__}") from e
    if m := re.search(rf"^(?:export\s+)?{re.escape(name)}=(\S+)", text, re.M):
        return m.group(1).strip("'\"")
    raise CollectionError(f"secret_missing name={name} file={env_file}")


# ---------------------------------------------------------------- 수집

def _http_json(req: urllib.request.Request, context: ssl.SSLContext | None) -> dict:
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SEC, context=context) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (OSError, json.JSONDecodeError) as e:  # URLError·TimeoutError·SSLError·연결 끊김 모두 OSError
        # str(e)는 URL·내부 IP를 포함할 수 있어 타입만 남긴다
        raise CollectionError(f"http_failed type={type(e).__name__}") from e


def collect_os_ids(os_url: str, insecure: bool, index: str = OS_INDEX) -> set[str]:
    """product_id composite aggregation으로 distinct ID를 모두 모은다."""
    password = read_secret("OPENSEARCH_ADMIN_PASSWORD", OS_ADMIN_ENV_FILE)
    user = os.environ.get("OPENSEARCH_ADMIN_USER", "admin")
    auth = base64.b64encode(f"{user}:{password}".encode()).decode()
    context = None
    if insecure:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    ids: set[str] = set()
    after: dict | None = None
    while True:
        composite: dict = {"size": OS_AGG_PAGE_SIZE, "sources": [{"pid": {"terms": {"field": "product_id"}}}]}
        if after:
            composite["after"] = after
        body = json.dumps({"size": 0, "aggs": {"ids": {"composite": composite}}}).encode()
        req = urllib.request.Request(
            f"{os_url.rstrip('/')}/{index}/_search", data=body, method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Basic {auth}"},
        )
        agg = _http_json(req, context).get("aggregations", {}).get("ids", {})
        buckets = agg.get("buckets", [])
        ids.update(b["key"]["pid"] for b in buckets)
        after = agg.get("after_key")
        if not buckets or not after:
            break
    if not ids:
        raise CollectionError("os_empty: 인덱스가 비어 있거나 접근할 수 없음")
    logger.info("os_collected index=%s count=%d", index, len(ids))
    return ids


def collect_db_ids(db_url: str) -> set[str]:
    """DB API GET /products 페이지네이션. distinct 수가 total과 다르면 수집 불완전."""
    token = read_secret("INTERNAL_TOKEN", DB_ENV_FILE)
    ids: set[str] = set()
    page, total = 1, None
    while True:
        req = urllib.request.Request(
            f"{db_url.rstrip('/')}/api/products?page={page}&page_size={DB_PAGE_SIZE}",
            headers={"X-Internal-Token": token},
        )
        data = _http_json(req, None)
        total = data["total"]
        ids.update(item["product_id"] for item in data["items"])
        if page >= data["total_pages"]:
            break
        page += 1
    if not ids or len(ids) != total:
        raise CollectionError(
            f"db_incomplete collected={len(ids)} total={total} (동률 정렬로 행이 중복/누락됐을 수 있음, psql 경로 사용)"
        )
    logger.info("db_collected count=%d", len(ids))
    return ids


# ---------------------------------------------------------------- 비교

def compare(db_ids: set[str], os_ids: set[str], db_verified: bool, os_verified: bool) -> int:
    orphans = sorted(os_ids - db_ids)       # OS에만 있음 → 벡터검색 유령 상품
    unindexed = sorted(db_ids - os_ids)     # DB에만 있음 → 추천·검색 누락
    print(f"DB distinct={len(db_ids)} OS distinct={len(os_ids)} "
          f"OS고아={len(orphans)} DB-only미색인={len(unindexed)}")
    if not (db_verified and os_verified):
        print("주의: 무결성 미확인 입력이 있음(trailer 없음)")
    for label, items in (("OS 고아", orphans), ("DB-only 미색인", unindexed)):
        if items:
            print(f"[{label}] {len(items)}건")
            print("\n".join(f"  {i}" for i in items))
    if orphans or unindexed:
        print("결과: 불일치 (보고만 함, 교정은 하지 않음)")
        return EXIT_MISMATCH
    print("결과: 일치")
    return EXIT_OK


# ---------------------------------------------------------------- 오프라인 파일 점검

def _read_file_ids(path: Path) -> list[str]:
    ids: list[str] = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            pid = json.loads(line).get("product_id")
            if not pid:
                raise CollectionError(f"missing_product_id file={path.name} line={n}")
            ids.append(pid)
    return ids


def check_files(data_dir: Path) -> int:
    problems: list[str] = []
    seen: dict[str, str] = {}
    for v3_name, v4_name in FILE_PAIRS:
        try:
            v3, v4 = _read_file_ids(data_dir / v3_name), _read_file_ids(data_dir / v4_name)
        except OSError as e:
            raise CollectionError(f"read_failed type={type(e).__name__} dir={data_dir}") from e
        if v3 != v4:
            if set(v3) != set(v4):
                problems.append(f"{v3_name}: v3/v4 ID 집합이 다름 (v3만 {len(set(v3) - set(v4))}, v4만 {len(set(v4) - set(v3))})")
            elif len(v3) == len(v4):
                problems.append(f"{v3_name}: ID 집합은 같으나 줄 순서가 다름")
            else:
                problems.append(f"{v3_name}: v3 {len(v3)}줄 / v4 {len(v4)}줄")
        for label, ids in (("v3", v3), ("v4", v4)):
            dups = sorted({i for i in ids if ids.count(i) > 1})
            if dups:
                problems.append(f"{v3_name if label == 'v3' else v4_name}: 파일 내 중복 ID {dups[:5]}")
        for pid in set(v3):
            if pid in seen and seen[pid] != v3_name:
                problems.append(f"파일 간 중복 ID {pid}: {seen[pid]} / {v3_name}")
            seen[pid] = v3_name
        print(f"{v3_name}: {len(v3)}줄")
    print(f"전체 distinct ID {len(seen)}")
    if problems:
        print("\n".join(f"[문제] {p}" for p in problems))
        return EXIT_MISMATCH
    print("결과: v3/v4 10쌍 일치, 중복 없음")
    return EXIT_OK


# ---------------------------------------------------------------- selftest

def selftest() -> int:
    failures: list[str] = []

    def expect(name: str, got, want) -> None:
        if got != want:
            failures.append(f"{name}: got={got!r} want={want!r}")

    ids = {"A1", "B2", "C3"}
    text = canonical_text(ids)
    good = text + trailer_line(text) + "\n"
    expect("roundtrip", parse_ids_text(good), (ids, True))
    expect("crlf_tolerated", parse_ids_text(good.replace("\n", "\r\n"))[0], ids)
    for name, bad in (("truncated", good.replace("C3\n", "")),
                      ("tampered", good.replace("B2", "B9")),
                      ("bad_id_line", text + "garbage line\n")):
        try:
            parse_ids_text(bad)
            failures.append(f"{name}: CollectionError 기대")
        except CollectionError:
            pass
    expect("no_trailer_unverified", parse_ids_text(text), (ids, False))
    empty = ""
    try:
        parse_ids_text(empty + trailer_line(empty) + "\n")
        failures.append("empty_ids: CollectionError 기대")
    except CollectionError:
        pass

    expect("compare_match", compare(ids, set(ids), True, True), EXIT_OK)
    expect("compare_orphan", compare(ids, ids | {"Z9"}, True, True), EXIT_MISMATCH)
    expect("compare_unindexed", compare(ids, ids - {"A1"}, True, True), EXIT_MISMATCH)
    # 건수가 같아도 집합이 다르면 불일치여야 한다 (과거 count 비교로 PASS 오판한 사례)
    expect("same_count_diff_set", compare({"A1", "B2"}, {"A1", "C3"}, True, True), EXIT_MISMATCH)

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        for i, (v3_name, v4_name) in enumerate(FILE_PAIRS):
            rows = "".join(json.dumps({"product_id": f"P{i}_{n}"}) + "\n" for n in range(3))
            (root / v3_name).write_text(rows, encoding="utf-8")
            (root / v4_name).write_text(rows, encoding="utf-8")
        expect("files_ok", check_files(root), EXIT_OK)
        (root / FILE_PAIRS[0][1]).write_text(
            json.dumps({"product_id": "P0_0"}) + "\n" + json.dumps({"product_id": "P0_0"}) + "\n", encoding="utf-8")
        expect("files_mismatch", check_files(root), EXIT_MISMATCH)

    if failures:
        print("\n".join(f"[FAIL] {f}" for f in failures))
        return EXIT_MISMATCH
    print("selftest 통과")
    return EXIT_OK


# ---------------------------------------------------------------- CLI

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="DB-OpenSearch product_id 정합성 점검 (읽기 전용)")
    p.add_argument("--collect", choices=["db", "os"], help="한쪽 ID만 수집해 trailer와 함께 표준출력으로 덤프")
    p.add_argument("--db-ids", metavar="FILE", help="DB ID 파일(없으면 DB API로 라이브 수집)")
    p.add_argument("--os-ids", metavar="FILE", help="OS ID 파일(없으면 OS로 라이브 수집)")
    p.add_argument("--files", action="store_true", help="v3/v4 데이터 파일 10쌍 오프라인 점검")
    p.add_argument("--data-dir", default=str(Path(__file__).resolve().parent.parent / "data"),
                   help="--files 입력 디렉터리 (기본: 레포 data/)")
    p.add_argument("--selftest", action="store_true", help="내장 mock으로 로직 검증")
    p.add_argument("--os-url", default=os.environ.get("OPENSEARCH_URL", "https://localhost:9200"))
    p.add_argument("--insecure", action="store_true", help="자체 서명 인증서 허용")
    p.add_argument("--db-url", default=os.environ.get("DATABASE_API_URL", "http://localhost:8020"))
    return p


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    args = build_parser().parse_args(argv)
    try:
        if args.selftest:
            return selftest()
        if args.files:
            return check_files(Path(args.data_dir))
        if args.collect == "os":
            dump_ids(collect_os_ids(args.os_url, args.insecure))
            return EXIT_OK
        if args.collect == "db":
            dump_ids(collect_db_ids(args.db_url))
            return EXIT_OK
        db_ids, db_ok = load_ids_file(args.db_ids) if args.db_ids else (collect_db_ids(args.db_url), True)
        os_ids, os_ok = load_ids_file(args.os_ids) if args.os_ids else (collect_os_ids(args.os_url, args.insecure), True)
        return compare(db_ids, os_ids, db_ok, os_ok)
    except CollectionError as e:
        logger.error("collection_failed reason=%s", e)
        return EXIT_FAILED
    except (KeyError, TypeError, ValueError) as e:
        # 응답 형태가 다르거나 JSONL이 깨진 경우. 잡지 않으면 파이썬 기본 종료코드 1이 "불일치"와 섞인다
        logger.error("unexpected_data type=%s", type(e).__name__)
        return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
