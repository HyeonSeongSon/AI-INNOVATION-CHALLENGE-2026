# backend/main.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import json
import os
from datetime import datetime

# 만든 모듈 임포트
from persona_categorizer import analyze_persona_logic

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 파일 경로 설정 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
CUSTOM_PERSONAS_FILE = os.path.join(DATA_DIR, "custom_personas.json")
HISTORY_FILE = os.path.join(DATA_DIR, "categorization_history.json")

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# --- [UPDATE] 화이트보드 내용을 반영한 데이터 모델 ---
class PersonaInput(BaseModel):
    id: Optional[int] = None
    # 1. 기본 정보
    name: str
    age: str
    gender: str = "무관"        # New
    job: str
    skinTone: str = ""         # New (21호, 23호, 쿨톤 등)
    
    # 2. 피부 프로필
    skinType: List[str]
    concerns: List[str]
    sensitivity: str = "중"    # New (상/중/하)
    
    # 3. 상세 선호 (Preferences)
    preferredIngredients: str = "" # New (콤마로 구분된 문자열)
    avoidedIngredients: str = ""   # New
    allergies: str = ""            # New
    preferredTexture: str = ""     # New (점성: 묽은, 꾸덕한)
    preferredScent: str = ""       # New
    preferredBrands: str = ""      # New
    
    # 4. 라이프스타일
    sleep: str
    stress: int = 3                # New (0~5 레벨)
    diet: str
    exercise: str = ""             # New (주 n회)
    
    # 5. 쇼핑
    budget: str

# --- 헬퍼 함수 ---
def load_json(filepath):
    if not os.path.exists(filepath): return []
    with open(filepath, "r", encoding="utf-8") as f:
        try: return json.load(f)
        except: return []

def save_json(filepath, new_data):
    data = load_json(filepath)
    data.append(new_data)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# --- API 엔드포인트 ---
@app.get("/personas")
def get_personas():
    return load_json(CUSTOM_PERSONAS_FILE)

@app.post("/personas")
def create_persona(persona: PersonaInput):
    data = persona.dict()
    if not data.get("id"): data["id"] = int(datetime.now().timestamp())
    save_json(CUSTOM_PERSONAS_FILE, data)
    return {"message": "저장 완료", "data": data}

@app.post("/analyze")
def analyze_endpoint(persona: PersonaInput):
    try:
        input_data = persona.dict()
        result = analyze_persona_logic(input_data) # 로직 실행
        result["analyzed_at"] = datetime.now().isoformat()
        save_json(HISTORY_FILE, result)
        return result
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)