from fastapi import HTTPException
from models.persona import PersonaInput

def validate_persona_logic(data: PersonaInput):
    """
    페르소나 데이터의 논리적 오류를 검증합니다.
    문제가 있을 경우 즉시 400 에러를 발생시켜 불필요한 LLM 호출을 막습니다.
    """
    
    # 1. 수치 범위 검증 (0~100%)
    if not (0 <= data.moistureLevel <= 100):
        raise HTTPException(status_code=400, detail="수분도는 0~100 사이여야 합니다.")
    
    if not (0 <= data.oilLevel <= 100):
        raise HTTPException(status_code=400, detail="유분도는 0~100 사이여야 합니다.")

    # 2. 나이 검증 (숫자 변환 시도 및 비상식적 나이 차단)
    if data.age:
        try:
            # "20대", "28세" 등에서 숫자만 추출 시도
            age_str = ''.join(filter(str.isdigit, str(data.age)))
            if age_str:
                age_num = int(age_str)
                if age_num < 10 or age_num > 100:
                    raise HTTPException(status_code=400, detail="유효하지 않은 나이입니다 (10~100세).")
        except ValueError:
            pass # 숫자가 없는 문자열(예: "모름")인 경우 패스

    # 3. 필수 선택 체크
    if not data.skinType:
        raise HTTPException(status_code=400, detail="피부 타입은 필수 입력값입니다.")

    return True