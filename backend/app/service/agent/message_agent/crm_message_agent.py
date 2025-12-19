from ...module.llm_service import LLMService
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from typing import TypedDict, List, Optional
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from pathlib import Path
import yaml

class State(TypedDict):
  messages: List[HumanMessage]

class CRMMessageAgent:
  def __init__(self):
    self.model = self.create_llm()

  def create_llm(self):
    # 프론트에서 값 전달해줄 예정
    get_model_value =  {
      "model_type": "openai",
      "model_name": "gpt-4o-mini",
      "temperature": 0.7,
      "max_tokens": 4096
    }
    
    return LLMService(
      get_model_value['model_type'],
      get_model_value['model_name'],
      get_model_value['temperature'],
      get_model_value['max_tokens']
    )
  
  def llm(self):
    test = "안녕"
    response = self.model.invoke(message=test)
    return response

#========================================================================================================================
# 노드
#========================================================================================================================

# 작성해야할 노드 및 툴
def persona_to_tag(self):
  pass

def recommend(self):
  pass

def product_document_search(self):
  pass

def create_message(self):
  pass

#========================================================================================================================
# 그래프 빌드
#========================================================================================================================
def build(self):
  pass

#========================================================================================================================
# 그래프 실행
#========================================================================================================================
def run(self):
  pass

if __name__ == "__main__":
  agent = CRMMessageAgent()
  print(agent.llm())