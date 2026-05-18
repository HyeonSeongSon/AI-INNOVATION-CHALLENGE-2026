import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../app/.env"), override=True)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agents.data_registration_agent.a2a_agent import router
from app.agents.data_registration_agent.workflow import build_workflow
from app.core.logging import configure_logging, get_logger

configure_logging(
    log_level=os.getenv("LOG_LEVEL", "INFO"),
    json_output=True,
    environment=os.getenv("ENVIRONMENT", "production"),
)

_logger = get_logger("data_registration_server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.graph = build_workflow()
    _logger.info("graph_compiled")
    yield


_allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
app = FastAPI(title="Data Registration Agent", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/health")
def health():
    return {"status": "ok", "agent": "data_registration_agent"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("servers.data_registration_server:app", host="0.0.0.0", port=8003, reload=True)
