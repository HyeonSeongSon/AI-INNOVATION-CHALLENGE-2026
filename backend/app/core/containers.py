from dataclasses import dataclass

from ..agents.generate_message_agent.services.generate_crm_message import CrmMessageGenerator as GenCrmGenerator
from ..agents.generate_message_agent.services.quality_check import QualityChecker as GenQualityChecker
from ..agents.generate_message_agent.services.apply_feedback import ApplyFeedback as GenApplyFeedback

from ..agents.recommend_product_agent.services.recommend_product_in_persona import ProductRecommender as RecommendProductRecommender

from ..agents.data_registration_agent.services.product_registration import ProductRegistrationService as DataRegService
from ..agents.shared.persona.persona_client import PersonaClient as SharedPersonaClient

from ..agents.marketing_assistant.services.quality_check import QualityChecker as MktQualityChecker
from ..agents.marketing_assistant.services.recommend_product import ProductRecommender as MktProductRecommender
from ..agents.marketing_assistant.services.orchestrator import Orchestrator
from ..agents.marketing_assistant.services.generate_crm_message import CrmMessageGenerator as MktCrmGenerator
from ..agents.marketing_assistant.services.parse_request import MultiValueParser as MktParser
from ..agents.marketing_assistant.services.product_client import ProductClient as MktProductClient
from ..agents.marketing_assistant.services.apply_feedback import ApplyFeedback as MktApplyFeedback
from ..agents.marketing_assistant.services.product_registration import ProductRegistrationService as MktRegService

from ..agents.crm_agent.services.recommend_products import ProductRecommender as CrmProductRecommender
from ..agents.crm_agent.services.create_product_message import ProductMessageGenerator
from ..agents.crm_agent.services.parse_crm_request import MultiValueParser as CrmParser
from ..agents.crm_agent.services.quality_check import QualityChecker as CrmQualityChecker

from ..agents.supervisor.services.supervisor import Supervisor


@dataclass
class GenerateMessageServices:
    generator: GenCrmGenerator
    checker: GenQualityChecker
    applier: GenApplyFeedback


@dataclass
class RecommendProductServices:
    recommender: RecommendProductRecommender


@dataclass
class DataRegistrationServices:
    registration: DataRegService
    persona_client: SharedPersonaClient


@dataclass
class MarketingAssistantServices:
    quality_checker: MktQualityChecker
    recommender: MktProductRecommender
    orchestrator: Orchestrator
    crm_generator: MktCrmGenerator
    parser: MktParser
    product_client: MktProductClient
    applier: MktApplyFeedback
    registration: MktRegService
    persona_client: SharedPersonaClient
    supervisor: Supervisor
    crm_recommender: CrmProductRecommender
    crm_generator_old: ProductMessageGenerator
    crm_parser: CrmParser
    crm_checker: CrmQualityChecker
