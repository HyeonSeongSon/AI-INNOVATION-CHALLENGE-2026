import json
import os
from datetime import datetime
from models.persona import PersonaInput, CategoryResult
from services.category_matcher import CategoryMatcher

# 전역 메모리 캐시 (서버 재시작 전까지 유지)
CACHE = {}

class PersonaService:
    def __init__(self):
        self.matcher = CategoryMatcher()

    async def create_persona_category(self, persona: PersonaInput) -> CategoryResult:
        # [업그레이드 1] 캐싱 로직
        # 입력 데이터를 고유 키로 변환 (딕셔너리는 해시 불가능하므로 문자열로 변환)
        input_key = str(sorted(persona.dict().items()))
        
        if input_key in CACHE:
            print(f"🚀 [Cache Hit] {persona.name}님의 분석 결과를 캐시에서 반환합니다.")
            return CACHE[input_key]

        # 캐시에 없으면 분석 실행
        result = await self.matcher.analyze(persona)
        
        # [업그레이드 2] 히스토리 저장
        await self.save_history(persona, result)
        
        # 결과 캐싱
        CACHE[input_key] = result
        return result

    async def save_history(self, persona: PersonaInput, result: CategoryResult):
        """분석 기록을 로그 파일에 저장"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "user_name": persona.name,
            "input_summary": f"{persona.age}/{persona.skinType}/{persona.skinConcerns}",
            "ai_result": result.dict()
        }
        
        # logs 폴더 자동 생성
        os.makedirs("logs", exist_ok=True)
        
        # 이어쓰기 모드('a')로 저장
        try:
            with open(f"logs/persona_history.json", "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"Log Save Error: {e}")