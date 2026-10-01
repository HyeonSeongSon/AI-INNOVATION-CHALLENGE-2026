"""
D1 문구 모집단(d1_phrases.csv)을 만든다 — 식약처 보도자료 13건의 텍스트 위반 문구 → 중복 제거 → 문장 규칙 · 제외 규칙.
LLM 호출 · 게이트 호출 없음. 결과(탐지)를 보기 전에 고정하는 파일이다.

사전 결정 (2026-09-29, 사용자):
    1. 이미지 붙임 속 문구는 넣지 않는다. 본문 · 표에 글로 적힌 문구만 쓴다.
    2. 중복 제거: 공백 · 괄호를 뗀 문자열이 같으면 한 문구다. 출처는 모두 남긴다.
       대표 표기는 기능성 오인이 아닌 첫 등장(게시일 → 원문 나열 순). 모두 기능성 오인이면 첫 등장.
    3. 복합 문구("염증개선·완화" 등)는 나누지 않고 원문 그대로 하나로 둔다.
    4. 문장 만들기: 원래 문장은 그대로, 나머지는 문구 형태별 고정 서술어 하나(아래 PREDICATES).
    5. 화장품이 아닌 기구 · 다른 제품군, 판매 · 표시 행위를 가리키는 문구는 뺀다(EXCLUDE_NOT_CLAIM).
       화장품 자체를 의약품 · 시술 이름으로 부르는 문구(탈모약 · 바르는 보톡스 등)는 의약품 오인 주장이라 넣는다.
    6. 지침 별표 1 금지 예시에 없고 흔히 쓰는 표현이라, 단독 문장으로는 위반인지가 문맥에 달린 문구는 뺀다
       (EXCLUDE_CONTEXT).
    7. 기능성 오인으로만 적발된 문구는 뺀다(플랜: 기능성 효능 유형 제외). 의약품 오인 출처가 함께 있으면 넣는다.

층(stratum):
    hedge    — 헷지형 적발 문구 4개(모두 의약품 오인). hedge_basis 에 적발 보도자료를 적는다.
    explicit — 문구(공백 제거)에 지침 별표 1 금지 예시어(GUIDELINE_ROOTS)가 들어 있다.
    subtle   — 예시어가 없다(보도자료 적발로만 근거가 있다).
category: 게이트 금지어 사전 6종 중 이 주장을 맡아야 할 카테고리. 대응 카테고리가 없으면 none(화장품 범위 이탈 등).
    층화 변수일 뿐 정답 라벨이 아니다. 정답(위반)은 보도자료 적발 사실이다.

사용법:
    python data/build_d1_phrases.py            # data/d1_phrases.csv 생성
    python data/build_d1_phrases.py --force    # 검수 열이 채워진 기존 파일도 덮어쓴다
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "enforcement_phrases_textonly_20260929.json"
OUT = HERE / "d1_phrases.csv"
FUNCTIONAL = "기능성 오인"

# 문구 형태별 고정 서술어. 헷지 층은 형태와 무관하게 HEDGE 하나.
PREDICATES = {
    "noun_phrase": "{} 효과가 있습니다.",   # 효능 명사구: 항염, 피부재생
    "condition": "{}에 효과가 있습니다.",   # 질환 · 증상 이름: 질 건조증, 염증
    "clause": "{}합니다.",                  # 격조사 논항이 있는 동작 명사로 끝남: 유산균을 질에 직접 전달
    "attribute": "{} 제품입니다.",          # 추천 · 전용 · 무첨가 등 제품 속성: 병원전용, 무자극
    "copula": "{}입니다.",                  # 화장품을 다른 이름으로 부름: 탈모약, 바르는 보톡스
}
HEDGE = "{}에 도움을 줍니다."

# 지침 별표 1 금지 예시에서 뽑은 예시어(공백 제거 · 부분 문자열 일치). 주석은 별표 1 항목.
GUIDELINE_ROOTS = [
    # 제1호 표제: 질병을 진단 · 치료 · 경감 · 처치 또는 예방
    "치료", "예방",
    # 제1호 질병 · 의학적 효능
    "아토피", "모낭충", "피로회복", "건선", "소양증", "살균", "소독", "항염", "진통", "해독", "이뇨", "항암",
    "항진균", "항바이러스", "근육이완", "통증", "면역", "항알레르기", "찰과상", "화상", "관절", "림프",
    "기저귀발진", "여드름", "기미", "주근깨", "항균",
    # 제1호 피부 관련
    "임신선", "튼살", "디톡스", "독소", "반흔", "가려움", "흔적", "흉터", "홍조", "홍반", "뾰루지", "손상",
    "피부노화", "셀룰라이트", "붓기", "다크서클", "효소", "콜라겐",
    # 제1호 모발 관련
    "발모", "육모", "양모", "탈모방지", "탈모치료", "모발", "속눈썹", "눈썹",
    # 제1호 생리활성 관련
    "혈액순환", "재생", "호르몬", "유익균", "질내산도", "질염", "세포성장", "세포활력", "유전자", "DNA",
    # 제1호 신체 개선 (피하지방 분해 · 지방볼륨생성)
    "다이어트", "체중감량", "지방", "체형", "몸매", "가슴", "얼굴크기", "윤곽", "V라인",
    # 제1호 기타
    "메디슨", "드럭", "코스메슈티컬", "치유",
    # 제4호 특정인 · 기관 지정·공인 (별표 5 다목 "의 · 약 분야의 전문가" 포함)
    "의료기관", "의사", "전문의", "병원", "약국",
    # 제4호 화장품 범위 이탈
    "무첨가", "스테로이드", "부작용", "명현", "보톡스", "레이저", "카복시", "시술", "노폐물", "필러",
    # 제4호 인체 유래 성분
    "배양액", "줄기세포", "엑소좀", "리포좀",
    # 제4호 저속 · 혐오
    "성생활", "여성크림", "윤활", "쾌감", "질보습", "질수축",
    # 제4호 사실과 다른 사용법 · 표시
    "바늘", "니들", "미세침", "MTS", "이너케어", "질내", "천연", "유기농",
    # 제4호 기타
    "식약처", "허가", "피부나이",
]

# 헷지형 적발 문구 → (문장에 쓸 명사, hedge_basis)
HEDGE_ROWS = {
    "부종에도움": ("부종", "2024-12-24 보도자료 적발 문구 '부종에 도움'(의약품 오인)"),
    "염증완화에도움": ("염증완화", "2025-08-06 보도자료 적발 문구 '염증완화에 도움'(의약품 오인)"),
    "아토피침독건선등에도좋지만": ("아토피 침독 건선 등", "2025-08-27 보도자료 적발 문구 '아토피 침독 건선 등에도 좋지만'(의약품 오인)"),
    "질염에진짜도움이되는": ("질염", "2025-09-24 보도자료 적발 문구 '질염에 진짜 도움이 되는'(의약품 오인)"),
}

# 형태(kind) · 카테고리 · 문장용 표기 수정(있으면). 키는 공백 · 괄호를 뗀 문구.
# 표기 수정은 서술어를 붙이려고 끝말만 고친 경우다. 원문은 original 열에 그대로 남는다.
ANNOT: dict[str, tuple[str, str, str | None]] = {
    "질환예방": ("noun_phrase", "medical_drug_claims", None),
    "통증완화": ("noun_phrase", "medical_drug_claims", None),
    "질건조증": ("condition", "medical_drug_claims", None),
    "항염": ("noun_phrase", "medical_drug_claims", None),
    "가려움증완화": ("noun_phrase", "medical_drug_claims", None),
    "자궁건강": ("noun_phrase", "none", None),
    "질세정·질염치료": ("noun_phrase", "medical_drug_claims", None),
    "질청소": ("noun_phrase", "none", None),
    "유산균을질에직접전달": ("clause", "none", None),
    "유해균억제": ("noun_phrase", "medical_drug_claims", None),
    "유산균활성화": ("noun_phrase", "medical_drug_claims", None),
    "국내산부인과의사및약국의사들도추천하는제품": ("copula", "false_certification", None),
    "피부재생": ("noun_phrase", "medical_drug_claims", None),
    "피부해독": ("noun_phrase", "medical_drug_claims", None),
    "면역력강화": ("noun_phrase", "medical_drug_claims", None),
    "손상된근육세포를재생": ("clause", "medical_drug_claims", None),
    "상피세포의성장촉진": ("noun_phrase", "medical_drug_claims", None),
    "마이크로니들이피부깊숙한층까지침투": ("clause", "none", None),
    "즉각적인모공수개선": ("noun_phrase", "absolute_claims", None),
    "활성산소제거": ("noun_phrase", "none", None),
    "면역력증진": ("noun_phrase", "medical_drug_claims", None),
    "혈액순환개선": ("noun_phrase", "medical_drug_claims", None),
    "항균": ("noun_phrase", "medical_drug_claims", None),
    "곰팡이박테리아억제": ("noun_phrase", "medical_drug_claims", None),
    "혈액순환증진": ("noun_phrase", "medical_drug_claims", None),
    "염증성여드름": ("condition", "medical_drug_claims", None),
    "아토피피부염의스테로이드대체제로사용": ("clause", "medical_drug_claims", None),
    "모공수개선": ("noun_phrase", "none", None),
    "10대연령의눈가로만들어줌": ("sentence", "absolute_claims", "10대 연령의 눈가로 만들어 줍니다"),
    "모공수감소": ("noun_phrase", "none", None),
    "4주만에10대눈가만들어드려요": ("sentence", "absolute_claims", None),
    "탈모방지": ("noun_phrase", "medical_drug_claims", None),
    "새로운모발성장촉진": ("noun_phrase", "medical_drug_claims", None),
    "모발굵기개선": ("noun_phrase", "medical_drug_claims", None),
    "탈모예방": ("noun_phrase", "medical_drug_claims", None),
    "염증개선·완화": ("noun_phrase", "medical_drug_claims", None),
    "모발성장촉진": ("noun_phrase", "medical_drug_claims", None),
    "염증케어": ("noun_phrase", "medical_drug_claims", None),
    "동물실험미실시": ("attribute", "none", None),
    "동물실험없이만든": ("attribute", "none", None),
    "동물실험No": ("attribute", "none", None),
    "지방분해": ("noun_phrase", "medical_drug_claims", None),
    "셀룰라이트제거": ("noun_phrase", "medical_drug_claims", None),
    "체지방감소": ("noun_phrase", "medical_drug_claims", None),
    "체중감량": ("noun_phrase", "medical_drug_claims", None),
    "노폐물배출": ("noun_phrase", "medical_drug_claims", None),
    "부종에도움": ("condition", "medical_drug_claims", None),
    "스테로이드성분없음": ("attribute", "safety_misrepresentation", "스테로이드 성분 없는"),
    "무자극": ("attribute", "safety_misrepresentation", None),
    "병원에서사용하는주사Injection성분": ("copula", "false_certification", None),
    "스테로이드성분없이부작용최소화": ("clause", "safety_misrepresentation", None),
    "세포재생": ("noun_phrase", "medical_drug_claims", None),
    "지방세포증식": ("noun_phrase", "medical_drug_claims", None),
    "근육이완": ("noun_phrase", "medical_drug_claims", None),
    "줄기세포": ("attribute", "none", None),
    "바르는보톡스": ("copula", "none", None),
    "필러시술효과": ("noun_phrase", "none", "필러 시술"),
    "00의사추천": ("attribute", "false_certification", None),
    "병원전용": ("attribute", "false_certification", None),
    "병원추천": ("attribute", "false_certification", None),
    "피부과의사추천": ("attribute", "false_certification", None),
    "병원전용화장품": ("copula", "false_certification", None),
    "피부염증감소": ("noun_phrase", "medical_drug_claims", None),
    "소염작용": ("noun_phrase", "medical_drug_claims", None),
    "염증완화에도움": ("condition", "medical_drug_claims", None),
    "피부세포재생": ("noun_phrase", "medical_drug_claims", None),
    "염증완화": ("noun_phrase", "medical_drug_claims", None),
    "MTS기기와함께사용하면서진피층끝까지침투": ("clause", "none", None),
    "피부내진피층,근막등성분을직접전달": ("clause", "none", None),
    "손상된피부개선": ("noun_phrase", "medical_drug_claims", None),
    "흉터자국옅어짐": ("noun_phrase", "medical_drug_claims", None),
    "국소적으로축적된지방연소를촉진": ("clause", "medical_drug_claims", None),
    "근육이완·피로회복": ("noun_phrase", "medical_drug_claims", None),
    "홍반감소": ("noun_phrase", "medical_drug_claims", None),
    "노폐물분해": ("noun_phrase", "medical_drug_claims", None),
    "항염진정": ("noun_phrase", "medical_drug_claims", None),
    "신진대사활성화": ("noun_phrase", "medical_drug_claims", None),
    "체내전해질공급": ("noun_phrase", "medical_drug_claims", None),
    "아토피침독건선등에도좋지만": ("condition", "medical_drug_claims", None),
    "피부세포에대한세포증식및콜라겐합속촉진효과": (
        "noun_phrase", "medical_drug_claims", "피부세포에 대한 세포증식 및 콜라겐 합속 촉진"),
    "질염에진짜도움이되는": ("condition", "medical_drug_claims", None),
    "피부면역력증진": ("noun_phrase", "medical_drug_claims", None),
    "생리통증완화": ("noun_phrase", "medical_drug_claims", None),
    "염증과가려움완화": ("noun_phrase", "medical_drug_claims", None),
    "질건조증개선": ("noun_phrase", "medical_drug_claims", None),
    "유해균생성을억제": ("clause", "medical_drug_claims", None),
    "산부인과전문의가선택또는개발": ("attribute", "false_certification", "산부인과 전문의가 선택 또는 개발한"),
    "뿌리는질유산균": ("copula", "none", None),
    "탈모약": ("copula", "medical_drug_claims", None),
    "발모제": ("copula", "medical_drug_claims", None),
    "발톱무좀치료": ("noun_phrase", "medical_drug_claims", None),
    "질염예방": ("noun_phrase", "medical_drug_claims", None),
    "가려움완화": ("noun_phrase", "medical_drug_claims", None),
    "관절염치료": ("noun_phrase", "medical_drug_claims", None),
    "염증": ("condition", "medical_drug_claims", None),
    "피로회복": ("noun_phrase", "medical_drug_claims", None),
    "여드름치료": ("noun_phrase", "medical_drug_claims", None),
    "소염효과": ("noun_phrase", "medical_drug_claims", "소염"),
    "산부인과전문의개발": ("attribute", "false_certification", None),
    "바르는질유산균": ("copula", "none", None),
}

# 결정 5: 화장품이 아닌 기구 · 다른 제품군, 판매 · 표시 행위
EXCLUDE_NOT_CLAIM = {
    "질세정기": "결정 5: 기구(질세정기)를 가리킴 — 화장품 효능 주장이 아님",
    "체내액체투여기디자인특허": "결정 5: 기구(체내액체투여기)를 가리킴 — 화장품 효능 주장이 아님",
    "러브젤": "결정 5: 다른 제품군(러브젤)을 가리킴 — 화장품 효능 주장이 아님",
    "윤활제": "결정 5: 다른 제품군(개인용 윤활제)을 가리킴 — 화장품 효능 주장이 아님",
    "MTS+화장품판매광고": "결정 5: 판매 방식(MTS 기기와 함께 판매)을 가리킴",
    "일반화장품을기능성화장품으로표시": "결정 5: 표시 행위를 가리킴(기능성 오인이기도 함)",
}
# 결정 6: 별표 1 예시에 없고 흔히 쓰는 표현 — 단독 문장으로는 위반 여부가 문맥에 달림
EXCLUDE_CONTEXT = {
    "피부진정": "결정 6: 별표 1 예시에 없는 흔한 화장품 표현(단독으로 라벨 애매)",
    "모공속피지조절": "결정 6: 별표 2 실증 대상('피부 피지분비 조절') — 실증 여부에 따라 합법",
    "모낭": "결정 6: 단어 하나(모낭). 별표 1 금지어는 '모낭충' — 단독으로 위반 주장이 아님",
    "Y존케어": "결정 6: 별표 1 예시에 없고 외음부세정제(화장품)에서 흔히 쓰는 표현 — 질 내 사용 문맥에서만 범위 이탈",
    "피부깊숙이침투하여": "결정 6: 별표 1 예시에 없는 흔한 표현 — 같은 표의 '마이크로니들이 … 침투'(포함)와 달리 기구 문맥 없음",
    "바르는피부제": "결정 6: 원문이 '바르고 씻어내는 제품 → 바르는 피부제' — 씻어내는 제품 문맥에서만 사용법 오인",
    "씻어내지않아도됨": "결정 6: 원문이 '바르고 씻어내는 제품 → 씻어내지 않아도 됨' — 씻어내는 제품 문맥에서만 사용법 오인",
}
EXCLUDE_OTHER = {
    "항염효과피부염": "원문 나열 조각이 두 표현(항염효과 · 피부염)을 붙여 적은 것 — 한 문장 규칙으로 만들 수 없음. '항염'은 따로 포함됨",
}

# 검수 때 특히 볼 곳(판단이 갈릴 수 있는 것)
NOTES = {
    "무자극": "별표 2 '무(無) oo'는 실증 대상이나, 자극 없음 단언은 '부작용이 전혀 없다'(별표 1)에 가까워 포함",
    "염증": "원문 나열 속 단어 하나 — 질환 이름 서술어('~에 효과가 있습니다')로 포함",
    "질건조증": "질환 이름 서술어로 포함",
    "10대연령의눈가로만들어줌": "끝말 '줌'을 '줍니다'로 고쳐 원래 문장으로 씀",
    "탈모약": "화장품을 의약품 이름으로 부름(결정 5 예외) — '{}입니다'",
    "발모제": "화장품을 의약품 이름으로 부름(결정 5 예외) — '{}입니다'",
    "바르는보톡스": "화장품을 시술 이름으로 부름(결정 5 예외) — '{}입니다'",
    "뿌리는질유산균": "화장품을 질 유산균 제품으로 부름(결정 5 예외) — '{}입니다'",
    "바르는질유산균": "화장품을 질 유산균 제품으로 부름(결정 5 예외) — '{}입니다'",
    "탈모방지": "기능성 오인 출처(2건)도 있으나 의약품 오인 출처가 있어 포함(결정 7)",
    "4주만에10대눈가만들어드려요": "category: 게이트 absolute_claims 예문('단 2주 만에 10년이 젊어 보이는 피부로 …')과 같은 유형",
}

COLUMNS = ["phrase_id", "text", "kind", "stratum", "category", "source", "source_ref", "hedge_basis",
           "include", "exclude_reason", "sentence_preview", "original", "text_edit", "guideline_roots", "n_sources",
           "note", "review_ok(O/X)", "review_note"]


def norm(s: str) -> str:
    """결정 2: 공백 · 괄호를 뗀다."""
    return re.sub(r"[\s()（）]", "", s)


def roots_in(text: str) -> list[str]:
    t = re.sub(r"\s", "", text)
    return [r for r in GUIDELINE_ROOTS if r in t]


def sentence_of(text: str, kind: str, stratum: str) -> str:
    if kind == "sentence":
        return text if text.endswith((".", "!", "?")) else text + "."
    return (HEDGE if stratum == "hedge" else PREDICATES[kind]).format(text)


def build() -> list[dict[str, str]]:
    data = json.loads(SRC.read_text(encoding="utf-8"))
    groups: dict[str, list[tuple[str, str, str]]] = {}
    for rel in sorted(data):
        for vtype, phrases in data[rel].items():
            for p in phrases:
                groups.setdefault(norm(p), []).append((rel, vtype, p))

    rows = []
    for key, occ in groups.items():
        non_func = [o for o in occ if o[1] != FUNCTIONAL]
        rep = (non_func or occ)[0]
        rels = list(dict.fromkeys(o[0] for o in occ))
        row = {
            "original": " / ".join(dict.fromkeys(o[2] for o in occ)),
            "source": rep[1],
            "source_ref": "; ".join(f"{r}({'·'.join(dict.fromkeys(o[1] for o in occ if o[0] == r))})" for r in rels),
            "n_sources": str(len(rels)), "hedge_basis": "", "text_edit": "", "note": NOTES.get(key, ""),
            "review_ok(O/X)": "", "review_note": "",
        }
        reason = (EXCLUDE_NOT_CLAIM.get(key) or EXCLUDE_CONTEXT.get(key) or EXCLUDE_OTHER.get(key)
                  or ("결정 7: 기능성 오인으로만 적발(기능성 효능 유형 제외)" if not non_func else ""))
        if reason:
            row.update(text=rep[2], kind="", stratum="", category="", include="X", exclude_reason=reason,
                       sentence_preview="", guideline_roots=",".join(roots_in(rep[2])))
            rows.append(row)
            continue
        if key not in ANNOT:
            raise SystemExit(f"형태 · 카테고리 표기가 없는 문구: {key} ({rep[2]})")
        kind, category, edited = ANNOT[key]
        text = rep[2]
        stratum = "subtle"
        if key in HEDGE_ROWS:
            text, row["hedge_basis"] = HEDGE_ROWS[key]
            stratum = "hedge"
            row["text_edit"] = f"헷지 서술어 규칙: 원문 '{rep[2]}' → 명사 '{text}' + '에 도움을 줍니다'"
        elif edited:
            row["text_edit"] = f"서술어를 붙이려고 끝말만 고침: '{rep[2]}' → '{edited}'"
            text = edited
        roots = roots_in(rep[2])
        if stratum != "hedge" and roots:
            stratum = "explicit"
        row.update(text=text, kind=kind, stratum=stratum, category=category, include="O", exclude_reason="",
                   sentence_preview=sentence_of(text, kind, stratum), guideline_roots=",".join(roots))
        rows.append(row)

    unused = set(ANNOT) - set(groups)
    if unused:
        raise SystemExit(f"모집단에 없는 표기 키: {sorted(unused)}")
    # phrase_id: 포함 문구 먼저(첫 게시일 순), 다음 제외 문구
    rows.sort(key=lambda r: (r["include"] != "O", r["source_ref"][:10]))
    for i, r in enumerate(rows, 1):
        r["phrase_id"] = f"P{i:03d}"
    return rows


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(OUT))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    out = Path(args.out)
    if out.exists() and not args.force:
        with open(out, encoding="utf-8-sig", newline="") as f:
            if any((r.get("review_ok(O/X)") or "").strip() for r in csv.DictReader(f)):
                raise SystemExit(f"{out} 에 검수 결과가 있습니다. 덮어쓰려면 --force")
    rows = build()
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    inc = [r for r in rows if r["include"] == "O"]
    from collections import Counter
    print(f"문구 {len(rows)}개 → 포함 {len(inc)} · 제외 {len(rows) - len(inc)}")
    for col in ("stratum", "kind", "category", "source"):
        print(f"  {col}: {dict(Counter(r[col] for r in inc).most_common())}")
    print(f"  제외 사유: {dict(Counter(r['exclude_reason'].split(':')[0] for r in rows if r['include'] != 'O'))}")
    print(f"→ {out}")


if __name__ == "__main__":
    main()
