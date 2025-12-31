# CRM 메시지 생성 시스템 - Tool Calling 기반 Interrupt 구현

## 📋 개요

아모레몰 CRM 메시지 생성 시스템을 **Tool Calling 방식**으로 구현하여, LLM이 필요한 툴을 스스로 선택하고 실행하도록 합니다. `recommend_products` 툴 실행 후 **Interrupt**를 발생시켜 사용자가 제품을 선택하면 계속 진행됩니다.

## 🎯 이상적인 시나리오

```
사용자: "20대 건성피부 고객에게 설화수 제품 추천해줘"
   ↓
LLM: parse_crm_message_request 툴 호출 (자동 판단)
   ↓
LLM: recommend_products 툴 호출 (자동 판단)
   ↓
[INTERRUPT 발생]
   ↓
웹 UI: 추천 제품 5개 표시
   ↓
사용자: "설화수 자음생크림" 선택 → POST 요청
   ↓
[RESUME]
   ↓
LLM: create_product_message 툴 호출 (자동 판단)
   ↓
완료: "세월의 지혜를 담은 설화수 자음생크림..."
```

## 🔑 핵심 차이점

### Tool Calling 방식의 특징
- **LLM이 스스로 툴 선택**: 워크플로우 노드가 아닌 LLM의 판단으로 툴 호출
- **자연스러운 대화 흐름**: 사용자 입력에 따라 유연하게 툴 조합
- **간단한 구조**: 복잡한 노드 그래프 대신 Agent 하나로 처리

### 입력 형식
- **JSON**: `{"persona": {"age": 20, "skin_type": "건성"}, "brand": "설화수"}`
- **자연어**: `"20대 건성피부 고객에게 설화수 제품 추천해줘"`

## 🔧 시스템 구현

### 1. State 정의

```python
from langgraph.graph import MessagesState
# Tool Calling 방식에서는 MessagesState 사용
# messages 리스트에 모든 대화 이력과 툴 호출 결과가 저장됨
```

### 2. Tool 정의

```python
from langchain_core.tools import tool
from typing import Union

@tool
def parse_crm_message_request(user_input: str) -> dict:
    """사용자 입력을 파싱하여 메시지 생성에 필요한 정보를 추출합니다.
    
    Args:
        user_input: 사용자 입력 (JSON 문자열 또는 자연어)
    
    Returns:
        {
            "persona": {
                "age_group": "20대",
                "skin_type": "건성",
                "concerns": ["주름", "탄력"],
                ...
            },
            "brand": "설화수",
            "category": "스킨케어",
            "campaign_objective": "신제품 프로모션"
        }
    """
    import json
    
    # JSON 파싱 시도
    try:
        parsed = json.loads(user_input)
        return parsed
    except json.JSONDecodeError:
        # 자연어 파싱 (LLM 사용)
        # 실제로는 LLM을 호출하여 구조화된 데이터 추출
        pass
    
    return {}


@tool
def recommend_products(persona: dict, brand: str = None, category: str = None) -> list:
    """페르소나에 맞는 제품을 추천합니다.
    
    Args:
        persona: 고객 페르소나 정보
        brand: 브랜드 필터 (옵션)
        category: 카테고리 필터 (옵션)
    
    Returns:
        추천 제품 리스트:
        [
            {
                "product_id": "PROD001",
                "name": "설화수 자음생크림",
                "brand": "설화수",
                "price": 150000,
                "category": "크림",
                "features": ["안티에이징", "탄력", "보습"],
                "image_url": "https://...",
                "match_score": 0.95,
                "match_reason": "건성피부에 적합한 고보습 제품"
            },
            {
                "product_id": "PROD002",
                "name": "설화수 윤조에센스",
                "brand": "설화수",
                "price": 120000,
                ...
            }
        ]
    """
    # OpenSearch 하이브리드 검색
    # 1. 페르소나 임베딩 벡터 생성
    # 2. 제품 검색 (벡터 유사도 + 키워드 매칭)
    # 3. 상위 5-10개 제품 반환
    pass


@tool
def create_product_message(product: dict, persona: dict, tone_guideline: dict) -> str:
    """선택된 제품에 대한 마케팅 메시지를 생성합니다.
    
    Args:
        product: 선택된 제품 정보
        persona: 고객 페르소나
        tone_guideline: 브랜드 톤 가이드라인
    
    Returns:
        생성된 마케팅 메시지 (150자 이내)
    """
    # LLM을 사용하여 메시지 생성
    # 브랜드 톤, 페르소나 특성, 제품 특징 반영
    pass
```

### 3. Agent 구성 (Tool Calling 방식)

```python
from langgraph.graph import StateGraph, MessagesState, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_openai import ChatOpenAI
import sqlite3

# 모든 툴 정의
tools = [
    parse_crm_message_request,
    recommend_products,
    create_product_message
]

# LLM에 툴 바인딩
llm = ChatOpenAI(model="gpt-4o", temperature=0)
llm_with_tools = llm.bind_tools(tools)

# Agent 노드: LLM이 툴을 선택하고 호출
def agent_node(state: MessagesState):
    """LLM이 상황에 맞는 툴을 선택"""
    response = llm_with_tools.invoke(state['messages'])
    return {"messages": [response]}

# Tool 노드: 실제 툴 실행
tool_node = ToolNode(tools)

# 조건부 엣지: 다음 단계 결정
def should_continue(state: MessagesState):
    last_message = state['messages'][-1]
    
    # 툴 호출이 없으면 종료
    if not last_message.tool_calls:
        return END
    
    # recommend_products 툴이 호출되었는지 확인
    tool_names = [tc['name'] for tc in last_message.tool_calls]
    
    if 'recommend_products' in tool_names:
        # 제품 추천 후 → Interrupt 발생시킬 노드로 이동
        return "wait_for_selection"
    
    # 다른 툴들은 바로 실행
    return "tools"

# 그래프 구성
workflow = StateGraph(MessagesState)

# 노드 추가
workflow.add_node("agent", agent_node)
workflow.add_node("tools", tool_node)
workflow.add_node("wait_for_selection", lambda state: state)  # Interrupt 지점

# 엣지 설정
workflow.set_entry_point("agent")

workflow.add_conditional_edges(
    "agent",
    should_continue,
    {
        "tools": "tools",
        "wait_for_selection": "wait_for_selection",
        END: END
    }
)

# tools 실행 후 다시 agent로
workflow.add_edge("tools", "agent")

# wait_for_selection 이후에도 agent로 (사용자 선택 반영 후)
workflow.add_edge("wait_for_selection", "agent")

# 체크포인터 설정
conn = sqlite3.connect("crm_checkpoints.db", check_same_thread=False)
memory = SqliteSaver(conn)

# 컴파일 - wait_for_selection 노드 전에 Interrupt
app = workflow.compile(
    checkpointer=memory,
    interrupt_before=["wait_for_selection"]  # 🔑 핵심!
)
```

### 4. 실행 흐름 상세

```
[사용자 입력]
    ↓
agent: LLM이 "parse_crm_message_request 툴을 써야겠다" 판단
    ↓
should_continue: "tools"로 이동
    ↓
tools: parse_crm_message_request 실행
    ↓
agent: LLM이 파싱 결과 보고 "recommend_products 툴을 써야겠다" 판단
    ↓
should_continue: "wait_for_selection"으로 이동
    ↓
[INTERRUPT 발생! - recommend_products 결과를 사용자에게 표시]
    ↓
[사용자 제품 선택 → 상태 업데이트]
    ↓
[RESUME]
    ↓
agent: LLM이 "create_product_message 툴을 써야겠다" 판단
    ↓
should_continue: "tools"로 이동
    ↓
tools: create_product_message 실행
    ↓
agent: LLM이 최종 메시지 반환
    ↓
END
```

## 🌐 FastAPI 구현

### 1. 데이터 모델

```python
from pydantic import BaseModel
from typing import Optional, Literal

class CRMRequest(BaseModel):
    user_input: str  # JSON 또는 자연어
    thread_id: Optional[str] = None


class ProductSelection(BaseModel):
    thread_id: str
    selected_product_id: str


class CRMResponse(BaseModel):
    status: Literal["needs_selection", "completed", "error"]
    thread_id: str
    recommended_products: Optional[list] = None
    final_message: Optional[str] = None
    selected_product: Optional[dict] = None
```

### 2. 헬퍼 함수

```python
def extract_tool_result(messages, tool_name: str):
    """메시지 히스토리에서 특정 툴의 결과 추출"""
    for msg in reversed(messages):
        # ToolMessage 찾기
        if hasattr(msg, 'name') and msg.name == tool_name:
            # 툴 실행 결과는 content에 저장됨
            return msg.content
    return None


def get_last_ai_message(messages):
    """마지막 AI 메시지 추출"""
    for msg in reversed(messages):
        if msg.type == 'ai' and msg.content:
            return msg.content
    return None
```

### 3. 엔드포인트

```python
from fastapi import FastAPI, HTTPException
from langchain_core.messages import HumanMessage
from uuid import uuid4
import json

app_fastapi = FastAPI()

@app_fastapi.post("/api/crm/generate", response_model=CRMResponse)
async def generate_crm_message(request: CRMRequest):
    """
    1단계: CRM 메시지 생성 시작
    - LLM이 툴을 선택하여 실행
    - recommend_products 실행 후 Interrupt 발생
    """
    thread_id = request.thread_id or f"thread-{uuid4()}"
    config = {"configurable": {"thread_id": thread_id}}
    
    try:
        # Agent 실행
        result = app.invoke(
            {"messages": [HumanMessage(content=request.user_input)]},
            config=config
        )
        
        # 상태 확인
        state = app.get_state(config)
        
        # Interrupt 확인
        if state.next and "wait_for_selection" in state.next:
            # 메시지 히스토리에서 recommend_products 결과 추출
            messages = state.values['messages']
            
            # recommend_products의 ToolMessage 찾기
            products_result = extract_tool_result(messages, 'recommend_products')
            
            if products_result:
                # JSON 파싱 (툴이 JSON 문자열로 반환한 경우)
                try:
                    products = json.loads(products_result)
                except:
                    products = products_result
                
                return CRMResponse(
                    status="needs_selection",
                    thread_id=thread_id,
                    recommended_products=products
                )
        
        # 정상 완료 (일반적으로 여기 도달하지 않음)
        final_msg = get_last_ai_message(state.values['messages'])
        return CRMResponse(
            status="completed",
            thread_id=thread_id,
            final_message=final_msg
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app_fastapi.post("/api/crm/select-product", response_model=CRMResponse)
async def select_product(request: ProductSelection):
    """
    2단계: 사용자 제품 선택 처리
    - 선택한 제품 정보를 메시지로 추가
    - Agent 재개 → create_product_message 실행
    """
    config = {"configurable": {"thread_id": request.thread_id}}
    
    try:
        # 현재 상태 확인
        state = app.get_state(config)
        
        if not state.next:
            raise HTTPException(
                status_code=400,
                detail="이미 완료되었거나 유효하지 않은 세션입니다."
            )
        
        # 추천된 제품 목록에서 선택한 제품 찾기
        messages = state.values['messages']
        products_result = extract_tool_result(messages, 'recommend_products')
        
        try:
            products = json.loads(products_result)
        except:
            products = products_result
        
        selected = next(
            (p for p in products if p['product_id'] == request.selected_product_id),
            None
        )
        
        if not selected:
            raise HTTPException(
                status_code=404,
                detail="선택한 제품을 찾을 수 없습니다."
            )
        
        # 🔑 핵심: 사용자 선택을 HumanMessage로 추가
        # LLM이 이 메시지를 보고 create_product_message 툴 호출
        selection_message = HumanMessage(
            content=f"사용자가 다음 제품을 선택했습니다: {json.dumps(selected, ensure_ascii=False)}"
        )
        
        # 상태에 메시지 추가
        app.update_state(
            config,
            {"messages": [selection_message]}
        )
        
        # Agent 재개
        result = app.invoke(None, config=config)
        
        # 최종 결과 확인
        final_state = app.get_state(config)
        final_msg = get_last_ai_message(final_state.values['messages'])
        
        return CRMResponse(
            status="completed",
            thread_id=request.thread_id,
            final_message=final_msg,
            selected_product=selected
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### 4. 대안: 커스텀 메타데이터 사용

선택한 제품을 메시지가 아닌 **메타데이터**로 전달할 수도 있습니다:

```python
# 선택한 제품을 state에 직접 저장 (MessagesState 확장 필요)
class ExtendedMessagesState(MessagesState):
    selected_product: Optional[dict] = None

# update_state 시
app.update_state(
    config,
    {
        "messages": [HumanMessage(content="사용자가 제품을 선택했습니다.")],
        "selected_product": selected
    }
)

# create_product_message 툴에서 state 접근
@tool
def create_product_message(state: ExtendedMessagesState) -> str:
    selected = state.get('selected_product')
    # ...
```

## 🖼️ 프론트엔드 구현

### React 컴포넌트

```javascript
import React, { useState } from 'react';

function CRMMessageGenerator() {
  const [input, setInput] = useState('');
  const [threadId, setThreadId] = useState(null);
  const [recommendedProducts, setRecommendedProducts] = useState(null);
  const [finalMessage, setFinalMessage] = useState(null);
  const [selectedProduct, setSelectedProduct] = useState(null);
  const [loading, setLoading] = useState(false);

  // 1단계: 초기 요청 - 제품 추천
  const handleGenerate = async () => {
    setLoading(true);
    
    try {
      const response = await fetch('/api/crm/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_input: input })
      });
      
      const data = await response.json();
      
      if (data.status === 'needs_selection') {
        // 제품 선택 UI 표시
        setThreadId(data.thread_id);
        setRecommendedProducts(data.recommended_products);
      }
    } catch (error) {
      console.error('Error:', error);
    } finally {
      setLoading(false);
    }
  };

  // 2단계: 제품 선택 - 메시지 생성
  const handleProductSelect = async (productId) => {
    setLoading(true);
    
    try {
      const response = await fetch('/api/crm/select-product', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          thread_id: threadId,
          selected_product_id: productId
        })
      });
      
      const data = await response.json();
      
      if (data.status === 'completed') {
        // 최종 메시지 표시
        setFinalMessage(data.final_message);
        setSelectedProduct(data.selected_product);
        setRecommendedProducts(null);  // 제품 선택 UI 숨김
      }
    } catch (error) {
      console.error('Error:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="crm-generator">
      {/* 입력 영역 */}
      {!recommendedProducts && !finalMessage && (
        <div className="input-section">
          <h2>CRM 메시지 생성</h2>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder='JSON 또는 자연어 입력
예시: "20대 건성피부 고객에게 설화수 제품 추천"'
            rows={4}
          />
          <button onClick={handleGenerate} disabled={loading}>
            {loading ? '생성 중...' : '제품 추천 받기'}
          </button>
        </div>
      )}

      {/* 제품 선택 영역 */}
      {recommendedProducts && (
        <div className="product-selection">
          <h2>추천 제품을 선택하세요</h2>
          <div className="product-grid">
            {recommendedProducts.map((product) => (
              <div 
                key={product.product_id} 
                className="product-card"
                onClick={() => handleProductSelect(product.product_id)}
              >
                <img src={product.image_url} alt={product.name} />
                <h3>{product.name}</h3>
                <p className="brand">{product.brand}</p>
                <p className="price">₩{product.price.toLocaleString()}</p>
                <div className="features">
                  {product.features.map((f, idx) => (
                    <span key={idx} className="tag">{f}</span>
                  ))}
                </div>
                <p className="match-reason">{product.match_reason}</p>
                <div className="match-score">
                  매칭도: {(product.match_score * 100).toFixed(0)}%
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 최종 메시지 표시 */}
      {finalMessage && (
        <div className="result-section">
          <h2>✅ 생성된 메시지</h2>
          
          <div className="selected-product-info">
            <h3>선택된 제품</h3>
            <div className="product-summary">
              <img src={selectedProduct.image_url} alt={selectedProduct.name} />
              <div>
                <h4>{selectedProduct.name}</h4>
                <p>{selectedProduct.brand}</p>
              </div>
            </div>
          </div>

          <div className="message-preview">
            <h3>마케팅 메시지</h3>
            <div className="message-box">
              {finalMessage}
            </div>
          </div>

          <button onClick={() => {
            setFinalMessage(null);
            setSelectedProduct(null);
            setThreadId(null);
            setInput('');
          }}>
            새로 생성하기
          </button>
        </div>
      )}
    </div>
  );
}

export default CRMMessageGenerator;
```

## 📊 실행 흐름 예시 (Tool Calling 방식)

### 예시 1: 자연어 입력

**사용자 입력:**
```
"30대 복합성 피부 고객에게 설화수 안티에이징 제품 추천해줘"
```

**Agent 실행 과정:**

```python
# 1단계: LLM이 parse_crm_message_request 호출
AIMessage(
    tool_calls=[{
        "name": "parse_crm_message_request",
        "args": {"user_input": "30대 복합성..."}
    }]
)

# ToolNode 실행
ToolMessage(
    name="parse_crm_message_request",
    content='{"persona": {"age_group": "30대", "skin_type": "복합성", "concerns": ["안티에이징"]}, "brand": "설화수"}'
)

# 2단계: LLM이 결과 보고 recommend_products 호출
AIMessage(
    tool_calls=[{
        "name": "recommend_products",
        "args": {
            "persona": {"age_group": "30대", ...},
            "brand": "설화수",
            "category": "안티에이징"
        }
    }]
)

# should_continue가 "wait_for_selection" 반환
# → interrupt_before 설정으로 INTERRUPT 발생!
```

**1단계 API 응답:**
```json
{
  "status": "needs_selection",
  "thread_id": "thread-abc123",
  "recommended_products": [
    {
      "product_id": "SULWHASOO_001",
      "name": "설화수 자음생크림",
      "price": 150000,
      "features": ["안티에이징", "탄력", "보습"],
      "match_score": 0.94,
      "match_reason": "30대 복합성 피부의 안티에이징에 최적"
    },
    ...
  ]
}
```

**사용자 선택:**
```json
{
  "thread_id": "thread-abc123",
  "selected_product_id": "SULWHASOO_001"
}
```

**선택 후 상태 업데이트:**
```python
# HumanMessage 추가
app.update_state(
    config,
    {"messages": [HumanMessage(
        content='사용자가 다음 제품을 선택: {"product_id": "SULWHASOO_001", "name": "설화수 자음생크림", ...}'
    )]}
)

# Agent 재개
# 3단계: LLM이 create_product_message 호출
AIMessage(
    tool_calls=[{
        "name": "create_product_message",
        "args": {
            "product": {"name": "설화수 자음생크림", ...},
            "persona": {"age_group": "30대", ...},
            ...
        }
    }]
)

# ToolNode 실행
ToolMessage(
    name="create_product_message",
    content="세월의 지혜를 담은 설화수 자음생크림으로 30대 피부의 탄력을 되찾으세요. 복합성 피부에 최적화된 밸런스 케어로 피부 본연의 아름다움을 지켜드립니다. ✨"
)

# 4단계: LLM이 최종 응답
AIMessage(
    content="메시지가 생성되었습니다: 세월의 지혜를 담은..."
)
```

**2단계 API 응답:**
```json
{
  "status": "completed",
  "thread_id": "thread-abc123",
  "final_message": "세월의 지혜를 담은 설화수 자음생크림으로...",
  "selected_product": {
    "product_id": "SULWHASOO_001",
    "name": "설화수 자음생크림"
  }
}
```

### 예시 2: JSON 입력

**사용자 입력:**
```json
{
  "persona": {
    "age_group": "20대",
    "skin_type": "건성",
    "concerns": ["보습", "진정"]
  },
  "brand": "라네즈",
  "category": "크림"
}
```

**Agent 실행:**
```
1. LLM: "이미 JSON이니까 파싱 건너뛰고 바로 recommend_products"
   → recommend_products(persona={...}, brand="라네즈", category="크림")

2. [INTERRUPT]

3. 사용자 선택: "라네즈 워터뱅크 크림"

4. LLM: create_product_message(product={...}, persona={...})

5. 완료
```

### 메시지 히스토리 전체 예시

```python
[
    HumanMessage(content="30대 복합성 피부에게..."),
    AIMessage(tool_calls=[{"name": "parse_crm_message_request", ...}]),
    ToolMessage(name="parse_crm_message_request", content='{"persona": ...}'),
    AIMessage(tool_calls=[{"name": "recommend_products", ...}]),
    # ← 여기서 INTERRUPT
    HumanMessage(content='사용자가 제품 선택: {"product_id": "SULWHASOO_001", ...}'),
    AIMessage(tool_calls=[{"name": "create_product_message", ...}]),
    ToolMessage(name="create_product_message", content="세월의 지혜를..."),
    AIMessage(content="메시지가 생성되었습니다...")
]
```

## 🎯 핵심 포인트

### 1. Tool Calling 방식의 Interrupt

```python
def should_continue(state: MessagesState):
    last_message = state['messages'][-1]
    
    if not last_message.tool_calls:
        return END
    
    tool_names = [tc['name'] for tc in last_message.tool_calls]
    
    # 특정 툴 호출 시 Interrupt 노드로 이동
    if 'recommend_products' in tool_names:
        return "wait_for_selection"
    
    return "tools"
```

- LLM이 `recommend_products` 툴을 호출하면
- `should_continue`가 `"wait_for_selection"` 반환
- `interrupt_before=["wait_for_selection"]`로 중단

### 2. 툴 결과는 ToolMessage에 저장

```python
# Agent가 툴을 호출하면
AIMessage(tool_calls=[{"name": "recommend_products", "args": {...}}])

# ToolNode가 실행하면
ToolMessage(
    name="recommend_products",
    content='[{"product_id": "P001", ...}]'  # JSON 문자열
)
```

### 3. 사용자 선택을 HumanMessage로 전달

```python
# 사용자가 제품 선택하면
selection_message = HumanMessage(
    content=f"사용자가 다음 제품을 선택했습니다: {json.dumps(selected)}"
)

app.update_state(config, {"messages": [selection_message]})
```

- LLM이 이 메시지를 읽고
- `create_product_message` 툴을 호출하도록 유도

### 4. LLM이 자동으로 툴 순서 결정

```
사용자: "20대 건성피부에게 설화수 추천"
   ↓
LLM 판단: "먼저 파싱이 필요하네" → parse_crm_message_request 호출
   ↓
LLM 판단: "이제 제품 검색하자" → recommend_products 호출
   ↓
[INTERRUPT]
   ↓
사용자 선택: "자음생크림"
   ↓
LLM 판단: "선택된 제품으로 메시지 만들자" → create_product_message 호출
```

## ⚠️ 주의사항

### 1. 툴 결과 형식 통일

```python
@tool
def recommend_products(...) -> str:  # 반드시 str 반환
    """..."""
    products = [...]
    return json.dumps(products, ensure_ascii=False)  # JSON 문자열로 변환
```

### 2. LLM 프롬프트 최적화

LLM이 올바른 순서로 툴을 호출하도록 System Prompt 설정:

```python
system_prompt = """
당신은 CRM 메시지 생성 전문가입니다.

작업 순서:
1. 사용자 입력을 먼저 parse_crm_message_request 툴로 파싱
2. 파싱 결과로 recommend_products 툴 호출하여 제품 추천
3. 사용자가 제품을 선택하면 create_product_message 툴로 메시지 생성

각 단계를 반드시 순서대로 진행하세요.
"""

llm_with_tools = llm.bind_tools(tools).bind(system=system_prompt)
```

### 3. 툴 간 데이터 전달

Tool Calling 방식에서는 **메시지 히스토리**를 통해 데이터 전달:

```python
@tool
def create_product_message(conversation_history: str) -> str:
    """선택된 제품으로 메시지 생성
    
    Args:
        conversation_history: 이전 대화 내역 (자동으로 LLM이 전달)
    """
    # LLM이 대화 히스토리를 분석하여 필요한 정보 추출
    # - 파싱된 페르소나 정보
    # - 선택된 제품 정보
    pass
```

또는 **명시적으로 필요한 파라미터 정의**:

```python
@tool
def create_product_message(
    product_name: str,
    product_features: list,
    customer_age: str,
    customer_skin_type: str,
    brand: str
) -> str:
    """제품 정보와 고객 정보를 받아 메시지 생성"""
    # LLM이 이전 대화에서 필요한 값을 추출하여 인자로 전달
    pass
```

## ✅ 완성도 체크리스트

### 기본 구현
- [ ] `parse_crm_message_request` 툴 구현 (JSON/자연어 파싱)
- [ ] `recommend_products` 툴 구현 (OpenSearch 연동)
- [ ] `create_product_message` 툴 구현 (LLM 기반 메시지 생성)
- [ ] LangGraph Agent 구성 (Tool Calling 방식)
- [ ] `should_continue` 조건부 엣지 구현
- [ ] SQLite 체크포인터 설정

### API 구현
- [ ] FastAPI 엔드포인트 `/api/crm/generate`
- [ ] FastAPI 엔드포인트 `/api/crm/select-product`
- [ ] 툴 결과 추출 헬퍼 함수 (`extract_tool_result`)
- [ ] 에러 핸들링 (세션 만료, 잘못된 제품 ID)

### 프론트엔드
- [ ] React 컴포넌트 구현
- [ ] 제품 선택 UI
- [ ] 최종 메시지 표시
- [ ] 로딩 상태 관리

### LLM 최적화
- [ ] System Prompt 작성 (툴 호출 순서 가이드)
- [ ] 툴 Docstring 최적화
- [ ] 툴 간 데이터 전달 설계

### 테스트
- [ ] JSON 입력 테스트
- [ ] 자연어 입력 테스트
- [ ] 여러 브랜드 테스트
- [ ] Interrupt 재개 테스트
- [ ] 동시 세션 테스트

## 🚀 Tool Calling 방식의 장점

### 1. 유연성
- LLM이 상황에 따라 툴 호출 순서 조정
- 예: JSON 입력 시 파싱 스킵 가능

### 2. 확장성
- 새 툴 추가만으로 기능 확장
- 그래프 구조 변경 불필요

### 3. 자연스러운 대화
- 사용자와의 자연스러운 인터랙션
- 중간에 질문/답변 가능

## 💡 고급 기능 제안

### 1. 다중 제품 선택
사용자가 여러 제품을 비교하고 싶을 때:

```python
@tool
def compare_products(product_ids: list[str]) -> str:
    """여러 제품을 비교 분석합니다."""
    pass

# Interrupt 후
사용자: "PROD001과 PROD002를 비교해줘"
LLM: compare_products 호출
```

### 2. 메시지 수정 요청
생성된 메시지를 사용자가 수정 요청:

```python
@tool
def revise_message(original_message: str, revision_request: str) -> str:
    """메시지를 수정합니다.
    
    Args:
        original_message: 원본 메시지
        revision_request: 수정 요청사항 (예: "더 짧게", "이모지 추가")
    """
    pass
```

### 3. A/B 테스트 버전 생성
한 제품에 대해 여러 버전의 메시지 생성:

```python
@tool
def generate_message_variations(product: dict, count: int = 3) -> list:
    """제품에 대한 여러 버전의 메시지를 생성합니다."""
    pass
```

### 4. 실시간 메시지 미리보기
Streaming을 활용한 실시간 메시지 생성:

```python
# FastAPI에서 SSE (Server-Sent Events) 사용
from fastapi.responses import StreamingResponse

@app.post("/api/crm/stream-message")
async def stream_message():
    async def generate():
        async for chunk in app.astream(...):
            yield f"data: {json.dumps(chunk)}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")
```

## 🎨 프론트엔드 UX 개선

### 제품 카드 디자인
```javascript
function ProductCard({ product, onSelect, isSelected }) {
  return (
    <div className={`product-card ${isSelected ? 'selected' : ''}`}>
      <div className="product-image">
        <img src={product.image_url} alt={product.name} />
        <div className="match-badge">
          {(product.match_score * 100).toFixed(0)}% 매칭
        </div>
      </div>
      
      <h3>{product.name}</h3>
      <p className="brand">{product.brand}</p>
      <p className="price">₩{product.price.toLocaleString()}</p>
      
      <div className="features">
        {product.features.map(f => (
          <span className="tag">{f}</span>
        ))}
      </div>
      
      <p className="match-reason">{product.match_reason}</p>
      
      <button onClick={() => onSelect(product.product_id)}>
        선택하기
      </button>
    </div>
  );
}
```

### 진행 상태 표시
```javascript
function ProgressIndicator({ step }) {
  const steps = [
    { id: 1, label: '요청 분석', icon: '🔍' },
    { id: 2, label: '제품 추천', icon: '🎯' },
    { id: 3, label: '제품 선택', icon: '✨' },
    { id: 4, label: '메시지 생성', icon: '📝' }
  ];
  
  return (
    <div className="progress-bar">
      {steps.map(s => (
        <div className={`step ${step >= s.id ? 'active' : ''}`}>
          <span className="icon">{s.icon}</span>
          <span className="label">{s.label}</span>
        </div>
      ))}
    </div>
  );
}
```

## 📝 다음 단계 로드맵

### Phase 1: MVP (2주)
- [ ] 기본 3개 툴 구현
- [ ] Tool Calling Agent 구성
- [ ] 기본 FastAPI 엔드포인트
- [ ] 간단한 React UI

### Phase 2: 최적화 (1주)
- [ ] LLM 프롬프트 튜닝
- [ ] 응답 속도 최적화
- [ ] 에러 핸들링 강화
- [ ] 로깅 및 모니터링

### Phase 3: 고급 기능 (2주)
- [ ] 메시지 수정 기능
- [ ] A/B 테스트 버전 생성
- [ ] 다중 제품 비교
- [ ] 실시간 스트리밍

### Phase 4: 프로덕션 준비 (1주)
- [ ] 성능 테스트
- [ ] 보안 검토
- [ ] 문서화
- [ ] 배포 자동화