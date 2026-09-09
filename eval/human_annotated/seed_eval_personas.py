"""
human_annotated_eval_data_set.jsonl의 60개 페르소나를 DB에 심고,
검색 쿼리 4종(need/preference/retrieval/persona)을 LLM으로 생성해 저장한다.

build_pool.py의 get_product_search_queries(persona_id, user_id=...)가
이 데이터를 읽어가므로, build_pool.py 실행 전에 반드시 먼저 돌려야 한다.

이미 personas/search_queries 행이 있으면 스킵한다(재실행해도 LLM을 다시 안 부름).

사용법:
    python seed_eval_personas.py
    python seed_eval_personas.py --concurrency 3
"""

import argparse
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "backend"))

from dotenv import load_dotenv
load_dotenv(_ROOT / "backend" / "app" / ".env")

os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"

sys.stdout.reconfigure(encoding="utf-8")

from sqlalchemy import text as sa_text
from langchain_core.messages import HumanMessage

from backend.app.config.settings import settings
from backend.app.core.llm_factory import get_llm
from backend.app.core.security import hash_password
from backend.app.core.database import get_db
from backend.app.agents.shared.persona.generate_persona_and_query import generate_search_query
from backend.app.agents.shared.persona.persona_client import PersonaClient

BASE_DIR = Path(__file__).parent
PERSONA_FILE = BASE_DIR / "human_annotated_eval_data_set.jsonl"

TEST_USER_EMAIL = "eval-pool-test@internal.local"
TEST_USER_PASSWORD = "eval-pool-test-only-not-for-login"

DEFAULT_CONCURRENCY = 5


def load_jsonl(path: Path) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def ensure_test_user() -> str:
    """평가용 테스트 계정을 찾거나 만들고 user_id(UUID 문자열)를 반환."""
    with next(get_db()) as db:
        row = db.execute(
            sa_text("SELECT id FROM users WHERE email = :e"), {"e": TEST_USER_EMAIL}
        ).fetchone()
        if row:
            return str(row[0])

        user_id = str(uuid.uuid4())
        db.execute(
            sa_text(
                "INSERT INTO users (id, email, password_hash, role) "
                "VALUES (:id, :email, :ph, 'user')"
            ),
            {"id": user_id, "email": TEST_USER_EMAIL, "ph": hash_password(TEST_USER_PASSWORD)},
        )
        db.commit()
        return user_id


def ensure_persona(persona_id: str, name: str, user_id: str) -> bool:
    """personas 행이 없으면 만든다. 새로 만들었으면 True, 이미 있었으면 False."""
    with next(get_db()) as db:
        row = db.execute(
            sa_text("SELECT persona_id FROM personas WHERE persona_id = :pid"),
            {"pid": persona_id},
        ).fetchone()
        if row:
            return False
        db.execute(
            sa_text(
                "INSERT INTO personas (persona_id, name, user_id) VALUES (:pid, :name, :uid)"
            ),
            {"pid": persona_id, "name": name[:200], "uid": user_id},
        )
        db.commit()
        return True


async def seed_one(
    record: dict,
    user_id: str,
    llm,
    persona_client: PersonaClient,
    semaphore: asyncio.Semaphore,
    done_ref: list,
    total: int,
) -> None:
    persona_id = record["persona_id"]
    info = record["information"]
    name = (info.splitlines()[0].strip() if info else persona_id) or persona_id

    async with semaphore:
        try:
            created = ensure_persona(persona_id, name, user_id)

            existing = await persona_client.get_existing_product_search_query(persona_id, user_id=user_id)
            done_ref[0] += 1
            if existing:
                print(f"[{done_ref[0]}/{total}] {persona_id} — 이미 존재, 스킵")
                return

            search_query = await generate_search_query([HumanMessage(content=info)], llm)
            await persona_client.save_product_search_query(persona_id, search_query, user_id=user_id)
            print(f"[{done_ref[0]}/{total}] {persona_id} — 생성 완료 (신규 persona={created})")
        except Exception as e:
            done_ref[0] += 1
            print(f"[{done_ref[0]}/{total}] {persona_id} 실패 — {type(e).__name__}")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    args = parser.parse_args()

    records = load_jsonl(PERSONA_FILE)
    print(f"페르소나 {len(records)}건")

    user_id = ensure_test_user()
    print(f"테스트 계정: {TEST_USER_EMAIL} (user_id={user_id})")
    print("-" * 70)

    llm = get_llm(settings.chatgpt_model_name, temperature=settings.llm_temperature_persona)
    persona_client = PersonaClient()
    semaphore = asyncio.Semaphore(args.concurrency)
    done_ref = [0]

    try:
        await asyncio.gather(
            *(seed_one(r, user_id, llm, persona_client, semaphore, done_ref, len(records)) for r in records)
        )
    finally:
        await persona_client.aclose()

    print("-" * 70)
    print("완료")


if __name__ == "__main__":
    asyncio.run(main())
