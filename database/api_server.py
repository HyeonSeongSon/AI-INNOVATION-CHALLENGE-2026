"""
Database API Server
DB CRUD + Pipeline API (port 8020)
"""

import os
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from core.database import init_db
from routers.api_endpoints import router as db_router
from routers.pipeline_router import router as pipeline_router
from routers.conversations_router import router as conversations_router
from routers.generated_messages_router import router as generated_messages_router

# DB 테이블 초기화
init_db()

app = FastAPI(
    title="Database API",
    description="DB CRUD 및 Pipeline API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(db_router)
app.include_router(pipeline_router)
app.include_router(conversations_router)
app.include_router(generated_messages_router)


@app.get("/")
def read_root():
    return {"status": "ok", "message": "Database API is running", "version": "1.0.0"}


@app.get("/health")
def health_check():
    return {"status": "healthy", "port": 8020}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="0.0.0.0", port=8020, reload=True)
