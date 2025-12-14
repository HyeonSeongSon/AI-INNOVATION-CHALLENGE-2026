from pydantic import BaseModel, Field
from typing import List, Optional

# 프론트엔드의 데이터 구조와 100% 일치시킵니다.
class PersonaInput(BaseModel):
    # --- [1] 기본 정보 ---
    name: Optional[str] = None       # 페르소나 이름 (식별용)
    age: Optional[str] = None        # 나이 (문자열 or 숫자)
    gender: Optional[str] = None     # 성별
    occupation: Optional[str] = None # 직업
    
    # --- [2] 피부 프로필 ---
    skinType: str                    # 피부 타입 (건성, 지성 등)
    skinTone: Optional[str] = None   # 피부 톤 (밝음, 어두움 등) - 추가됨
    skinConcerns: List[str] = []     # 피부 고민 (트러블, 주름 등)
    sensitivityLevel: str = "중"     # 민감도
    moistureLevel: int = 50          # 수분도 (0~100)
    oilLevel: int = 50               # 유분도 (0~100)
    
    # --- [3] 성분 및 텍스처 선호 ---
    preferredIngredients: List[str] = [] # 선호 성분
    avoidedIngredients: List[str] = []   # 기피 성분
    texturePreference: List[str] = []    # 제형 선호 (젤, 크림 등) - 추가됨
    preferredScent: List[str] = []       # 향 선호 - 추가됨
    priceRange: Optional[str] = None     # 가격대
    
    # --- [4] 라이프스타일 ---
    sleepHours: Optional[str] = None      # 수면 시간
    stressLevel: Optional[str] = None     # 스트레스 수준
    dietQuality: Optional[str] = None     # 식습관 - 추가됨
    exerciseFrequency: Optional[str] = None # 운동 빈도 - 추가됨
    
    # --- [5] 환경 및 습관 ---
    location: Optional[str] = None        # 거주 지역 - 추가됨
    climate: Optional[str] = None         # 기후 (건조, 습함) - 추가됨
    screenTime: Optional[str] = None      # 디지털 기기 사용 시간 - 추가됨
    makeupFrequency: Optional[str] = None # 메이크업 빈도 - 추가됨
    
    # --- [6] 가치관 및 특수사항 ---
    naturalOrganic: bool = False          # 천연/유기농 선호
    veganCrueltyFree: bool = False        # 비건/크루얼티프리
    ecoPackaging: bool = False            # 친환경 패키지 - 추가됨
    multiFunctionPreference: bool = False # 다기능 제품 선호 - 추가됨
    pregnancyLactation: bool = False      # 임신/수유 여부 - 추가됨

    

# 분석 결과 모델 (LLM/Rule-Base 결과 반환용)
class CategoryResult(BaseModel):
    primary_category: str                 # 메인 추천 카테고리 (필수)
    secondary_category: Optional[str] = None # 서브 추천 카테고리
    confidence_score: float               # 신뢰도 점수 (0.0 ~ 100.0 or 0.0 ~ 1.0)
    keywords: List[str] = []              # 매칭된 주요 키워드
    reasoning: str                        # 추천 사유 (AI 에이전트가 생성한 문장)