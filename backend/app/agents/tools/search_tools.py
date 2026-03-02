from langchain_core.tools import tool
import httpx
import os

DB_API_BASE_URL = os.getenv("DATABASE_API_URL", "http://localhost:8020") + "/api"


@tool
async def get_all_personas() -> str:
    """
    데이터베이스에 저장된 모든 페르소나 목록을 조회합니다.
    사용자가 페르소나 목록을 보여달라고 하거나, 어떤 페르소나가 있는지 물어볼 때 사용하세요.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(f"{DB_API_BASE_URL}/personas/list")
        response.raise_for_status()
        personas = response.json()

    if not personas:
        return "현재 등록된 페르소나가 없습니다."

    lines = [f"총 {len(personas)}명의 페르소나가 등록되어 있습니다.\n"]
    for p in personas:
        line = f"- [{p['persona_id']}] {p['name']}"
        if p.get("age") and p.get("gender"):
            line += f" ({p['age']}세, {p['gender']})"
        if p.get("occupation"):
            line += f" / {p['occupation']}"
        if p.get("skin_type"):
            line += f" / 피부타입: {', '.join(p['skin_type'])}"
        lines.append(line)

    return "\n".join(lines)
