from dataclasses import dataclass

from ..agents.generate_message_agent.services.generate_crm_message import CrmMessageGenerator as GenCrmGenerator
from ..agents.generate_message_agent.services.quality_check import QualityChecker as GenQualityChecker
from ..agents.generate_message_agent.services.apply_feedback import ApplyFeedback as GenApplyFeedback

from ..agents.recommend_product_agent.services.recommend_product_in_persona import ProductRecommender as RecommendProductRecommender

from ..agents.data_registration_agent.services.product_registration import ProductRegistrationService as DataRegService
from ..agents.shared.persona.persona_client import PersonaClient as SharedPersonaClient

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
