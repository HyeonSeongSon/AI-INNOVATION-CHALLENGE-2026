from generate_product_document_prompts import build_generate_base_product_document_prompt

def _build_nail_color_extra_prompt():
    nail_color_extra = """

## [네일 컬러 추가 필드]

※ 카테고리 구분 기준
  - 네일컬러: color_family, nail_finish 작성 / coat_type, coat_function은 반드시 null
  - 탑&베이스코트: coat_type, coat_function 작성 / color_family는 빈 리스트([]), nail_finish는 해당 시만 작성

1. nail_finish
    - 네일 마무리 질감 (탑&베이스코트는 광택 효과 명시 시만 작성, 없으면 null)
    - "크림" | "글리터" | "펄" | "매트" | "젤 룩" | "메탈릭" | "미러" | "홀로그램" | "듀오크롬" | "오로라" | "시어"
    - 복수 선택 가능: ["펄", "글리터"]

2. color_family
    - 색상 계열 (탑&베이스코트는 빈 리스트)
    - 단일 색상으로 분류 불가능한 경우 "멀티컬러" 사용
    - 예: ["레드", "핑크", "누드", "코랄", "버건디", "네이비", "블랙", "화이트",
           "브라운", "그레이", "퍼플", "올리브", "멀티컬러"]

3. coat_type
    - 탑&베이스코트 전용 / 네일컬러는 반드시 null
    - "탑코트" | "베이스코트" | "탑&베이스 겸용"

4. coat_function
    - 탑&베이스코트 전용 / 네일컬러는 반드시 null
    - 예: ["지속력 향상", "광택 부여", "칩핑 방지", "네일 보호", "발색 베이스"]

5. quick_dry
    - 속건성 여부
    - true / false / null (언급 없는 경우)

6. wear_time
    - 지속력 (명시된 경우만 작성)
    - 숫자 + 단위로 정규화: "7일", "14일" ("최대", "약" 등 수식어 제거)
    - 언급 없으면 null

7. coat_count
    - 권장 도포 횟수 (명시된 경우만 작성)
    - 예: 2
    - 언급 없으면 null

8. free_of
    - 무함유 성분 기준만 작성 (비건·크루얼티프리는 base의 value 필드에 작성)
    - 예: ["5free", "10free", "파라벤프리"]
    - 언급 없으면 빈 리스트

---

## [출력 형식 추가]

"nail_finish": null,
"color_family": [],
"coat_type": null,
"coat_function": null,
"quick_dry": null,
"wear_time": null,
"coat_count": null,
"free_of": []
"""
    return nail_color_extra

def _build_nail_care_extra():
    nail_care_extra = """
------------------------------------------------
[네일 케어 추가 필드]
------------------------------------------------

※ 카테고리 구분 기준
  - 큐티클&영양: cuticle_function 작성 / remover_type, remover_form은 반드시 null
  - 네일 리무버: remover_type, remover_form 작성 / cuticle_function은 반드시 null

1. care_product_type
    - 케어 제품 세부 타입을 단일 값으로 작성
    - 겸용 제품은 주된 용도를 기준으로 선택하세요
    - "큐티클 오일" | "큐티클 크림" | "네일 오일" | "네일 세럼" |
      "네일 크림" | "핸드&네일 크림" | "네일 리무버"

2. remover_type
    - 네일 리무버 전용 / 리무버가 아니면 반드시 null
    - 성분 기준과 용도 기준 복수 선택 가능
    - 성분 기준: "아세톤" | "논아세톤"
    - 용도 기준: "젤 네일 전용" | "일반 네일 전용" | "겸용"
    - 예: ["아세톤", "젤 네일 전용"]

3. remover_form
    - 네일 리무버 전용 / 리무버가 아니면 반드시 null
    - "리무버액" | "패드" | "버블 리무버" | "크림" | "젤"

4. cuticle_function
    - 큐티클&영양 전용 / 리무버는 반드시 null
    - 네일·큐티클에 특화된 기능만 작성하세요
    - 일반 보습·진정 등 범용 기능은 base의 function 필드에 작성하세요
    - 예: ["큐티클 연화", "각질 케어", "손톱 강화", "손톱 성장 촉진", "영양 공급"]

5. nail_concern
    - 제품이 타겟하는 네일 상태 고민 (CRM 필터링용)
    - base의 concern 필드와 역할이 다릅니다:
      · concern (base): 고객이 인식하는 고민 — 검색/추천 매칭용
      · nail_concern (서브): 제품이 직접 타겟하는 네일 상태 — 세부 필터링용
    - 예: ["갈라짐", "부서짐", "건조한 큐티클", "착색", "약한 손톱", "거스러미"]

------------------------------------------------
[출력 형식 추가]
------------------------------------------------
"care_product_type": "",
"remover_type": null,
"remover_form": null,
"cuticle_function": null,
"nail_concern": []
"""
    return nail_care_extra

def _build_nail_tool_extra():
    nail_tool_extra = """
------------------------------------------------
[네일 도구&키트 추가 필드]
------------------------------------------------

19. tool_type
    - 도구 세부 타입을 단일 값으로 작성
    - 복수 도구 구성(키트)인 경우 주된 도구 타입 또는 "키트"로 작성
    - "파일&버퍼" | "네일 클리퍼" | "큐티클 푸셔" | "큐티클 니퍼" |
      "네일 드릴" | "UV/LED 램프" | "네일 브러시" | "키트"

20. included_items
    - 2개 이상의 도구가 하나의 상품으로 구성된 경우만 작성
    - 단일 도구 단품은 null
    - 예: ["파일", "버퍼", "큐티클 푸셔", "오렌지 스틱"]

21. compatible_with
    - 호환 네일 타입 (명시된 경우만 작성)
    - 예: ["젤 네일", "아크릴", "자연 손톱"]
    - 언급 없으면 빈 리스트([])

22. grit_level
    - 파일&버퍼 전용: 그릿(거칠기) 수준
    - 문서에 명시된 그릿 수치를 그대로 작성
    - 예: "100/180", "180/240"
    - 파일&버퍼가 아니거나 언급 없으면 null

23. material
    - 도구 소재 (명시된 경우만 작성)
    - 복합 소재인 경우 리스트로 작성
    - 예: ["스테인리스", "플라스틱"], ["세라믹"], ["강화유리"]
    - 언급 없으면 빈 리스트([])

24. professional_grade
    - 전문가용 여부
    - 문서에 "살롱용", "프로페셔널", "전문가용" 표현이 명시된 경우만 true
    - 명시 없으면 null (추측하지 마세요)
    - true / false / null

------------------------------------------------
[출력 형식 추가]
------------------------------------------------
"tool_type": "",
"included_items": null,
"compatible_with": [],
"grit_level": null,
"material": [],
"professional_grade": null
"""
    return nail_tool_extra

def build_nail_category_product_prompt(extra_category, product_document, category_list):
    extra_prompts = {
        "nail_color": _build_nail_color_extra_prompt,
        "nail_care": _build_nail_care_extra,
        "nail_tool": _build_nail_tool_extra
    }
    extra_prompt = extra_prompts[extra_category]()
    base_prompt = build_generate_base_product_document_prompt(product_document, category_list)
    return base_prompt + extra_prompt
