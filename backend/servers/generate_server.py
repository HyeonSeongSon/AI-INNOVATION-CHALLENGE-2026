import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../app/.env"), override=True)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agents.generate_message_agent.a2a_agent import router
from app.core.logging import configure_logging

configure_logging(
    log_level=os.getenv("LOG_LEVEL", "INFO"),
    json_output=True,
    environment=os.getenv("ENVIRONMENT", "production"),
)

app = FastAPI(title="Generate Message Agent", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/health")
def health():
    return {"status": "ok", "agent": "generate_message_agent"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("servers.generate_server:app", host="0.0.0.0", port=8002, reload=True)
