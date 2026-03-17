from generate_product_document_prompts import build_generate_base_product_document_prompt
from typing import List

def _build_makeup_tool_extra_prompt():
    makeup_tool_extra = """
------------------------------------------------
[메이크업 도구 추가 필드]
------------------------------------------------

※ 이 서브프롬프트는 아래 tool_type에 해당하는 상품에만 적용됩니다:
   스펀지, 퍼프, 화장솜, 속눈썹

19. tool_type
    - 도구 세부 타입을 단일 값으로 작성하세요
    - 반드시 아래 선택지 중 하나를 선택하세요:
      "스펀지" | "퍼프" | "화장솜" | "속눈썹"

20. material
    - 소재를 리스트로 작성하세요 (명시된 경우만)
    - 예: ["실리콘"], ["NBR"], ["면", "극세사"]
    - 언급 없으면 빈 리스트([])로 작성하세요

21. tool_function
    - 도구 기능을 리스트로 작성하세요
    - 문서에 명시된 기능만 포함하세요
    - 아래 통제 어휘 안에서 선택하세요:
      "파운데이션 도포" | "파우더 세팅" | "블렌딩" | "컨실러 도포" |
      "치크 도포" | "하이라이터 도포" | "토너 도포" | "스킨케어 도포" |
      "화장 제거" | "클렌징"
    - 위 선택지에 없는 기능이 문서에 명시된 경우 그대로 추가하세요

22. latex_free
    - 라텍스 무함유 여부 (명시된 경우만)
    - true / false / null

23. washable
    - 세척 가능 여부 (명시된 경우만)
    - true / false / null

------------------------------------------------
[속눈썹 전용 필드 — tool_type이 "속눈썹"일 때만 작성]
tool_type이 "속눈썹"이 아니면 아래 필드를 모두 null로 작성하세요.
------------------------------------------------

24. lash_style
    - 속눈썹 스타일
    - "자연스러운" | "볼륨" | "드라마틱" | "큐트" | null

25. band_type
    - 밴드 타입
    - "투명 밴드" | "검정 밴드" | null

26. reusable
    - 재사용 가능 여부
    - true / false / null

------------------------------------------------
[출력 형식 추가]
------------------------------------------------
"tool_type": "",
"material": [],
"tool_function": [],
"latex_free": null,
"washable": null,
"lash_style": null,
"band_type": null,
"reusable": null
"""
    return makeup_tool_extra

def _build_brush_extra_prompt():
    brush_extra = """
------------------------------------------------
[브러쉬 추가 필드]
------------------------------------------------

19. brush_area
    - 브러쉬 사용 부위를 리스트로 작성하세요
    - 반드시 아래 선택지 안에서 선택하세요:
      "얼굴 전체" | "치크" | "쉐딩" | "눈" | "입술"
    - 단품은 해당 부위 하나만, 브러쉬세트는 해당하는 부위 모두 작성하세요
    - brush_area는 사용 부위를 나타내며, body_area(기본 필드)와 역할이 다릅니다.
      body_area는 항상 ["얼굴"]로 작성하고, brush_area에 세부 부위를 작성하세요.

20. tool_function
    - 브러쉬 기능을 리스트로 작성하세요
    - 문서에 명시된 기능만 포함하고, 아래 통제 어휘 안에서 선택하세요:
      "파운데이션 도포" | "파우더 세팅" | "컨투어링" |
      "블러셔 도포" | "브론저 도포" |
      "아이섀도우 도포" | "블렌딩" | "라이너 도포" | "언더라인" |
      "립 도포" | "정교한 라인 표현"
    - 위 선택지에 없는 기능이 문서에 명시된 경우 그대로 추가하세요
    - 브러쉬세트는 구성 브러쉬에 해당하는 기능을 모두 포함하세요

21. bristle_type
    - 브러쉬모 타입 (명시된 경우만)
    - "합성모" | "천연모" | "혼합모" | null

22. bristle_feel
    - 브러쉬모 감촉 및 형태 (명시된 경우만)
    - 아래 선택지 안에서 선택하세요:
      "부드러운" | "탄탄한" | "촘촘한" | "얇은" | "플랫" | "팬형"
    - 위 선택지에 없는 표현이 문서에 명시된 경우 그대로 작성하세요
    - 언급 없으면 null

23. handle_material
    - 손잡이 소재 (명시된 경우만)
    - "우드" | "메탈" | "플라스틱"
    - 위 선택지에 없는 소재가 명시된 경우 그대로 작성하세요
    - 언급 없으면 null

24. washable
    - 세척 가능 여부 (명시된 경우만)
    - true / false / null

25. included_items
    - 브러쉬세트 전용: 구성 품목을 리스트로 작성하세요
    - 예: ["파운데이션 브러쉬", "파우더 브러쉬", "아이섀도우 브러쉬 2종"]
    - 브러쉬세트가 아닌 단품은 null로 작성하세요

------------------------------------------------
[출력 형식 추가]
------------------------------------------------
"brush_area": [],
"tool_function": [],
"bristle_type": null,
"bristle_feel": null,
"handle_material": null,
"washable": null,
"included_items": null
"""
    return brush_extra

def _build_beauty_accessory_extra_prompt():
    beauty_accessory_extra = """
------------------------------------------------
[소품/용기 추가 필드]
------------------------------------------------

※ 이 서브프롬프트는 소품&도구, 용기&수저 서브카테고리 상품에 적용됩니다.

19. accessory_type
    - 소품 세부 타입을 단일 값으로 작성하세요
    - 반드시 아래 선택지 중 하나를 선택하세요:
      "용기" | "스파츄라" | "거울" | "파우치" | "기타"

20. material
    - 소재를 리스트로 작성하세요 (명시된 경우만)
    - 예: ["유리"], ["플라스틱", "실리콘"], ["스테인리스"]
    - 언급 없으면 빈 리스트([])로 작성하세요

21. tool_function
    - 도구 기능을 리스트로 작성하세요
    - 문서에 명시된 기능만 포함하고, 아래 통제 어휘 안에서 선택하세요:
      "화장품 소분" | "위생적인 덜어쓰기" | "여행 휴대" |
      "화장품 보관" | "메이크업 확인" | "제품 혼합"
    - 위 선택지에 없는 기능이 문서에 명시된 경우 그대로 추가하세요

------------------------------------------------
[용기 전용 필드 — accessory_type이 "용기"일 때만 작성]
accessory_type이 "용기"가 아니면 아래 필드를 모두 null로 작성하세요.
------------------------------------------------

22. capacity
    - 용량 (명시된 경우만)
    - 예: "50ml", "100ml"
    - 언급 없으면 null

23. airtight
    - 밀폐 여부 (명시된 경우만)
    - true / false / null

------------------------------------------------
[키트 전용 필드 — 2종 이상 구성 상품일 때만 작성]
단품이면 included_items를 null로 작성하세요.
------------------------------------------------

24. included_items
    - 키트 구성 품목을 리스트로 작성하세요
    - 예: ["스파츄라 2종", "용기 3종", "파우치 1개"]
    - 단품은 null

------------------------------------------------
[출력 형식 추가]
------------------------------------------------
"accessory_type": "",
"material": [],
"tool_function": [],
"capacity": null,
"airtight": null,
"included_items": null
"""
    return beauty_accessory_extra

def _build_beauty_device_extra_prompt():
    beauty_device_extra = """
------------------------------------------------
[뷰티디바이스 추가 필드]
------------------------------------------------

19. device_type
    - 디바이스 형태/용도 기반 세부 타입을 단일 값으로 작성하세요
    - 반드시 아래 선택지 중 하나를 선택하세요:
      "마스크형" | "핸드헬드" | "클렌징기" | "마사지기" |
      "드라이어" | "고데기" | "스타일러" | "제모기" |
      "두피케어기" | "네일램프" | "피부측정기" | "기타"
    - 기술 방식(LED, EMS 등)이 아닌 형태와 용도를 기준으로 선택하세요
      예: LED 마스크 → "마스크형", EMS 핸드헬드 기기 → "핸드헬드"

20. technology
    - 적용 기술을 리스트로 작성하세요 (명시된 경우만)
    - 아래 통제 어휘 안에서 선택하세요:
      "LED" | "EMS" | "초음파" | "갈바닉" | "열 에너지" |
      "이온토포레시스" | "진동" | "흡입" | "레이저" | "적외선"
    - 위 선택지에 없는 기술이 명시된 경우 그대로 추가하세요
    - 언급 없으면 빈 리스트([])로 작성하세요

21. skin_function
    - 디바이스가 피부/모발/두피에 직접 작용하는 기능을 리스트로 작성하세요
    - 기본 필드 function과 역할이 다릅니다:
      · function(기본): 제품이 제공하는 효과 (탄력 개선, 주름 케어 등)
      · skin_function(디바이스 전용): 디바이스 작동으로 발생하는 물리적 작용
    - 아래 통제 어휘 안에서 선택하세요:
      "성분 흡수 촉진" | "혈액 순환 촉진" | "모공 클렌징" |
      "두피 자극" | "열 자극" | "리프팅 자극" | "진정 완화"
    - 위 선택지에 없는 기능이 명시된 경우 그대로 추가하세요

22. usage_frequency
    - 권장 사용 빈도 (명시된 경우만)
    - 예: "매일" | "주 3회" | "주 1회"
    - 언급 없으면 null

23. session_time
    - 1회 사용 시간 (명시된 경우만)
    - 예: "10분", "20분"
    - 언급 없으면 null

24. intensity_levels
    - 강도 단계 수 (명시된 경우만, 숫자로 작성)
    - 예: 3
    - 언급 없으면 null

25. waterproof
    - 방수 여부 (명시된 경우만)
    - true / false / null

26. power_source
    - 전원 방식 (명시된 경우만)
    - "USB 충전" | "건전지" | "유선" | null

27. medical_certified
    - 국내 식약처(MFDS) 의료기기 인증 여부 (명시된 경우만)
    - true / false / null

------------------------------------------------
[출력 형식 추가]
------------------------------------------------
"device_type": "",
"technology": [],
"skin_function": [],
"usage_frequency": null,
"session_time": null,
"intensity_levels": null,
"waterproof": null,
"power_source": null,
"medical_certified": null
"""
    return beauty_device_extra

def build_beauty_device_category_product_prompt(extra_category: str, product_document: str, category_list: List[str]):
    extra_prompts = {
        "makeup_tool": _build_makeup_tool_extra_prompt,
        "brush": _build_brush_extra_prompt,
        "beauty_accessory": _build_beauty_accessory_extra_prompt,
        "beauty_device_extra": _build_beauty_device_extra_prompt
    }
    extra_prompt = extra_prompts[extra_category]()
    base_prompt = build_generate_base_product_document_prompt(product_document, category_list)
    return base_prompt + extra_prompt