"""
메시지 품질 검사 서비스

3단계 품질 검증:
1. Rule-based Check (동기, 비용 0)
2. LLM-as-a-Judge (비동기, LLM 1회 호출)
3. Groundedness Check (동기, 비용 0)
"""

import re
import os
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
from ..prompts.quality_check_prompt import build_quality_check_prompt
from ....core.logging import get_logger
from ....core.langsmith_config import traced
import yaml

# .env 파일 로드
load_dotenv(os.path.join(os.path.dirname(__file__), "../../../.env"))

logger = get_logger("quality_check")


# ============================================================
# LLM 구조화 출력 모델
# ============================================================

class LLMJudgeOutput(BaseModel):
    """LLM-as-a-Judge 구조화된 출력"""
    accuracy: int = Field(..., ge=1, le=5, description="정확성: 상품 정보가 정확하게 반영되었는지 (1-5)")
    tone: int = Field(..., ge=1, le=5, description="톤: 브랜드 톤에 부합하는지 (1-5)")
    personalization: int = Field(..., ge=1, le=5, description="개인화: 페르소나에 맞춤화되었는지 (1-5)")
    naturalness: int = Field(..., ge=1, le=5, description="자연스러움: 문장이 자연스럽고 읽기 좋은지 (1-5)")
    safety: int = Field(..., ge=1, le=5, description="안전성: 금지 표현이 없고 과장이 없는지 (1-5)")
    passed: bool = Field(..., description="전체 통과 여부 (모든 항목 3점 이상이면 True)")
    feedback: str = Field(..., description="종합 피드백 (한글, 2-3문장)")


# ============================================================
# 품질 검사 서비스 클래스
# ============================================================

class QualityChecker:
    """마케팅 메시지 품질 검사 서비스"""

    def __init__(self):
        """초기화: LLM 클라이언트, brand_tone YAML 로드"""
        api_key = os.getenv("OPENAI_API_KEY")
        chat_gpt_model_name = os.getenv("CHATGPT_MODEL_NAME")

        if not api_key:
            raise ValueError("OPENAI_API_KEY가 .env 파일에 설정되어 있지 않습니다.")

        self.llm = ChatOpenAI(
            model=chat_gpt_model_name,
            temperature=0,
            api_key=api_key,
            request_timeout=30,
        )
        self.judge = self.llm.with_structured_output(LLMJudgeOutput)

        # brand_tone YAML 로드
        if os.environ.get("APP_ROOT"):
            root_dir = Path(os.environ.get("APP_ROOT"))
            data_path = root_dir / "agents" / "crm_agent" / "prompts" / "brand_tone.yaml"
        else:
            root_dir = Path(__file__).resolve().parents[1]
            data_path = root_dir / "prompts" / "brand_tone.yaml"

        self.brand_tones = self._load_yaml(data_path)

        logger.info(
            "quality_checker_initialized",
            model=chat_gpt_model_name,
        )

    def _load_yaml(self, file_path) -> Dict[str, Any]:
        """YAML 파일 로드"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error("yaml_load_failed", file_path=str(file_path), error=str(e), exc_info=True)
            return {}

    # ============================================================
    # Public: 3단계 품질 검사 오케스트레이션
    # ============================================================

    @traced(name="quality_check", run_type="chain")
    async def check_quality(
        self,
        message: Dict[str, Any],
        product: Dict[str, Any],
        persona_info: Dict[str, Any],
        purpose: str,
        brand_name: str,
    ) -> Dict[str, Any]:
        """
        메시지 품질 검사 (3단계 순차 실행, 실패 시 단락)

        Returns:
            QualityCheckResult dict
        """
        result = {
            "passed": False,
            "failed_stage": None,
            "failure_reason": None,
            "rule_check_passed": False,
            "rule_check_issues": [],
            "llm_judge_passed": False,
            "llm_judge_scores": None,
            "groundedness_passed": False,
            "groundedness_result": None,
        }

        # Stage 1: Rule-based Check
        logger.info("stage1_rule_check_started")
        passed, issues = self._run_rule_check(message, brand_name)
        result["rule_check_passed"] = passed
        result["rule_check_issues"] = issues
        if not passed:
            result["failed_stage"] = "rule_check"
            result["failure_reason"] = f"규칙 기반 검사 실패: {'; '.join(issues)}"
            logger.warning("stage1_failed", issues=issues)
            return result
        logger.info("stage1_passed")

        # Stage 2: LLM-as-a-Judge
        logger.info("stage2_llm_judge_started")
        passed, scores = await self._run_llm_judge(
            message, product, persona_info, purpose, brand_name
        )
        result["llm_judge_passed"] = passed
        result["llm_judge_scores"] = scores
        if not passed:
            result["failed_stage"] = "llm_judge"
            result["failure_reason"] = f"LLM 평가 미통과: {scores.get('feedback', '') if scores else '평가 실패'}"
            logger.warning("stage2_failed", scores=scores)
            return result
        logger.info("stage2_passed", scores=scores)

        # Stage 3: Groundedness Check
        logger.info("stage3_groundedness_started")
        passed, groundedness = self._run_groundedness_check(message, product)
        result["groundedness_passed"] = passed
        result["groundedness_result"] = groundedness
        if not passed:
            result["failed_stage"] = "groundedness"
            result["failure_reason"] = f"사실 확인 실패: {'; '.join(groundedness.get('issues', []))}"
            logger.warning("stage3_failed", issues=groundedness.get("issues", []))
            return result
        logger.info("stage3_passed")

        # 전체 통과
        result["passed"] = True
        logger.info("quality_check_all_passed")
        return result

    # ============================================================
    # Stage 1: Rule-based Check (동기, 비용 0)
    # ============================================================

    def _run_rule_check(
        self,
        message: Dict[str, Any],
        brand_name: str,
    ) -> Tuple[bool, List[str]]:
        """
        규칙 기반 품질 검사

        검사 항목:
        - 제목/본문 존재 및 길이 검증
        - 상품명/브랜드명 포함 여부
        - 금지 표현 키워드 매칭
        """
        issues = []
        title = message.get("title", "")
        msg_body = message.get("message", "")
        product_name = message.get("product_name", "")
        brand = message.get("brand", "")

        # 1. 포맷 검증
        if not title:
            issues.append("제목이 비어있습니다")
        if not msg_body:
            issues.append("메시지 본문이 비어있습니다")

        # 2. 길이 검증
        if title and len(title) < 5:
            issues.append(f"제목이 너무 짧습니다 ({len(title)}자, 최소 5자)")
        if title and len(title) > 40:
            issues.append(f"제목이 너무 깁니다 ({len(title)}자, 최대 40자)")
        if msg_body and len(msg_body) < 20:
            issues.append(f"메시지가 너무 짧습니다 ({len(msg_body)}자, 최소 20자)")
        if msg_body and len(msg_body) > 350:
            issues.append(f"메시지가 너무 깁니다 ({len(msg_body)}자, 최대 350자)")

        # 3. 필수 요소 포함 확인
        full_text = f"{title} {msg_body}"
        if product_name and product_name not in full_text:
            issues.append(f"상품명 '{product_name}'이(가) 메시지에 포함되지 않았습니다")
        if brand and brand not in full_text:
            issues.append(f"브랜드명 '{brand}'이(가) 메시지에 포함되지 않았습니다")

        # 4. 금지 표현 검사
        forbidden = self._extract_forbidden_expressions(brand_name)
        for expr in forbidden:
            expr_stripped = expr.strip()
            if expr_stripped and expr_stripped in full_text:
                issues.append(f"금지 표현 감지: '{expr_stripped}'")

        passed = len(issues) == 0
        return passed, issues

    def _extract_forbidden_expressions(self, brand_name: str) -> List[str]:
        """
        brand_tone.yaml에서 해당 브랜드의 '7. 금지 표현' 항목 추출

        Returns:
            금지 표현 키워드 리스트
        """
        brand_tones = self.brand_tones.get("brand_ton_prompt", {})

        # 브랜드 톤 텍스트 찾기 (대소문자 무시)
        tone_text = brand_tones.get(brand_name)
        if tone_text is None:
            for key, value in brand_tones.items():
                if key.lower() == brand_name.lower():
                    tone_text = value
                    break

        if not tone_text:
            return []

        # "7. 금지 표현" 이후의 내용 추출
        lines = tone_text.split('\n')
        found_section = False
        expressions = []

        for line in lines:
            line_stripped = line.strip()
            if "7. 금지 표현" in line_stripped or "7." in line_stripped and "금지" in line_stripped:
                found_section = True
                # 같은 줄에 내용이 있는 경우
                after_label = line_stripped.split("금지 표현")[-1].strip()
                if after_label:
                    expressions.extend([e.strip() for e in after_label.split(",")])
                continue
            if found_section:
                if line_stripped and not line_stripped.startswith("8."):
                    expressions.extend([e.strip() for e in line_stripped.split(",")])
                if line_stripped.startswith("8.") or (not line_stripped and expressions):
                    break

        return [e for e in expressions if e]

    # ============================================================
    # Stage 2: LLM-as-a-Judge (비동기, LLM 호출)
    # ============================================================

    @traced(name="llm_judge", run_type="llm")
    async def _run_llm_judge(
        self,
        message: Dict[str, Any],
        product: Dict[str, Any],
        persona_info: Dict[str, Any],
        purpose: str,
        brand_name: str,
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        LLM-as-a-Judge 평가

        with_structured_output(LLMJudgeOutput) 사용
        통과 기준: 모든 항목 3점 이상
        """
        try:
            brand_tone = self._get_brand_tone(brand_name)
            product_text = self._format_product_info(product)
            persona_text = self._format_persona_info(persona_info)

            prompt_messages = build_quality_check_prompt(
                brand_name=brand_name,
                product_name=message.get("product_name", ""),
                product_info=product_text,
                persona_info=persona_text,
                purpose=purpose,
                brand_tone=brand_tone,
                title=message.get("title", ""),
                message=message.get("message", ""),
            )

            result: LLMJudgeOutput = await self.judge.ainvoke(prompt_messages)

            scores = {
                "accuracy": result.accuracy,
                "tone": result.tone,
                "personalization": result.personalization,
                "naturalness": result.naturalness,
                "safety": result.safety,
                "overall": round(
                    (result.accuracy + result.tone + result.personalization
                     + result.naturalness + result.safety) / 5.0, 2
                ),
                "feedback": result.feedback,
            }

            return result.passed, scores

        except Exception as e:
            logger.error("llm_judge_failed", error=str(e), exc_info=True)
            return False, {"feedback": f"LLM 평가 중 오류: {str(e)}"}

    def _get_brand_tone(self, brand_name: str) -> str:
        """브랜드톤 가져오기"""
        brand_tones = self.brand_tones.get("brand_ton_prompt", {})

        if brand_name in brand_tones:
            return brand_tones[brand_name]

        for key, value in brand_tones.items():
            if key.lower() == brand_name.lower():
                return value

        logger.warning("brand_tone_not_found", brand_name=brand_name)
        return "친근하면서도 전문적이고 신뢰감 있는 어조"

    def _format_product_info(self, product: Dict[str, Any]) -> str:
        """상품 정보를 텍스트로 포맷팅"""
        sections = []

        if product.get("product_name"):
            sections.append(f"상품명: {product['product_name']}")
        if product.get("brand"):
            sections.append(f"브랜드: {product['brand']}")
        if product.get("product_tag"):
            sections.append(f"카테고리: {product['product_tag']}")
        if product.get("sale_price"):
            sections.append(f"가격: {product['sale_price']:,}원")
        if product.get("skin_type"):
            skin_types = product["skin_type"]
            if isinstance(skin_types, list):
                sections.append(f"적합 피부타입: {', '.join(skin_types)}")
        if product.get("skin_concerns"):
            concerns = product["skin_concerns"]
            if isinstance(concerns, list):
                sections.append(f"타겟 고민: {', '.join(concerns)}")
        if product.get("preferred_ingredients"):
            ingredients = product["preferred_ingredients"]
            if isinstance(ingredients, list):
                sections.append(f"주요 성분: {', '.join(ingredients)}")

        return "\n".join(sections)

    def _format_persona_info(self, persona_info: Dict[str, Any]) -> str:
        """페르소나 정보를 텍스트로 포맷팅"""
        sections = []

        if persona_info.get("이름"):
            sections.append(f"이름: {persona_info['이름']}")
        if persona_info.get("나이"):
            sections.append(f"나이: {persona_info['나이']}세")
        if persona_info.get("성별"):
            sections.append(f"성별: {persona_info['성별']}")
        if persona_info.get("피부타입"):
            skin_type = persona_info["피부타입"]
            if isinstance(skin_type, list):
                sections.append(f"피부타입: {', '.join(skin_type)}")
        if persona_info.get("고민_키워드"):
            concerns = persona_info["고민_키워드"]
            if isinstance(concerns, list):
                sections.append(f"피부 고민: {', '.join(concerns)}")
        if persona_info.get("선호_성분"):
            ingredients = persona_info["선호_성분"]
            if isinstance(ingredients, list):
                sections.append(f"선호 성분: {', '.join(ingredients)}")
        if persona_info.get("기피_성분"):
            avoided = persona_info["기피_성분"]
            if isinstance(avoided, list):
                sections.append(f"기피 성분: {', '.join(avoided)}")
        if persona_info.get("가치관"):
            values = persona_info["가치관"]
            if isinstance(values, list):
                sections.append(f"가치관: {', '.join(values)}")

        return "\n".join(sections)

    # ============================================================
    # Stage 3: Groundedness Check (동기, 비용 0)
    # ============================================================

    def _run_groundedness_check(
        self,
        message: Dict[str, Any],
        product: Dict[str, Any],
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Groundedness 검증: 메시지 내 사실 정보가 상품 데이터와 일치하는지 확인

        검사 항목:
        - 가격 정보 일치 여부
        - 피부타입 언급 시 실제 데이터와 일치 여부
        """
        issues = []
        checked_fields = []
        msg_text = f"{message.get('title', '')} {message.get('message', '')}"

        # 1. 가격 검증
        sale_price = product.get("sale_price")
        if sale_price:
            checked_fields.append("sale_price")
            price_patterns = re.findall(r'[\d,]+원', msg_text)
            for price_str in price_patterns:
                try:
                    mentioned_price = int(price_str.replace(",", "").replace("원", ""))
                    if mentioned_price != sale_price:
                        issues.append(
                            f"가격 불일치: 메시지 '{price_str}' vs 실제 {sale_price:,}원"
                        )
                except ValueError:
                    pass

        # 2. 피부타입 검증
        actual_skin_types = product.get("skin_type", [])
        if actual_skin_types:
            checked_fields.append("skin_type")
            common_skin_types = ["건성", "지성", "복합성", "민감성", "중성", "수분부족"]
            for skin_type in common_skin_types:
                if skin_type in msg_text and skin_type not in actual_skin_types:
                    issues.append(
                        f"피부타입 불일치: '{skin_type}'이(가) 메시지에 언급되었으나 "
                        f"실제 적합 피부타입은 {actual_skin_types}"
                    )

        is_grounded = len(issues) == 0
        result = {
            "is_grounded": is_grounded,
            "issues": issues,
            "checked_fields": checked_fields,
        }
        return is_grounded, result


# ============================================================
# 싱글톤 패턴
# ============================================================

_checker_instance = None


def get_quality_checker() -> QualityChecker:
    """QualityChecker 인스턴스를 가져오거나 생성 (싱글톤 패턴)"""
    global _checker_instance
    if _checker_instance is None:
        _checker_instance = QualityChecker()
    return _checker_instance
