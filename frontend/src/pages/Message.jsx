import React, { useState, useRef, useEffect } from 'react';
import styled, { css } from 'styled-components';
import { 
  Send, Settings, Sparkles, Wand2, ShoppingBag, 
  Tag, Bot, Trash2, X, Copy, RefreshCw, Check, MessageCircle 
} from 'lucide-react';

// ✅ API 및 Context
import api from '../api';
import { useChat } from '../context/ChatContext';
import { useToast } from '../components/Toast';

/* --- [1] 스타일 컴포넌트 --- */
const Container = styled.div` display: flex; height: calc(100vh - 100px); gap: 24px; max-width: 1400px; margin: 0 auto; `;
const Sidebar = styled.div` width: 340px; background: white; border-radius: 24px; border: 1px solid #eee; padding: 24px; display: flex; flex-direction: column; gap: 24px; box-shadow: 0 4px 20px rgba(0,0,0,0.02); `;
const SidebarHeader = styled.div` display: flex; align-items: center; gap: 10px; padding-bottom: 20px; border-bottom: 1px solid #f0f0f0; h3 { font-size: 18px; font-weight: 800; color: #111; } `;
const SectionLabel = styled.label` font-size: 12px; font-weight: 700; color: #888; margin-bottom: 8px; display: block; text-transform: uppercase; letter-spacing: 0.5px; `;
const FormGroup = styled.div` display: flex; flex-direction: column; `;
const Input = styled.input` padding: 14px; border: 1px solid #e0e0e0; border-radius: 12px; font-size: 14px; outline: none; transition: 0.2s; &:focus { border-color: #6B4DFF; box-shadow: 0 0 0 3px rgba(107, 77, 255, 0.1); } `;
const Select = styled.select` padding: 14px; border: 1px solid #e0e0e0; border-radius: 12px; font-size: 14px; outline: none; background: white; cursor: pointer; transition: 0.2s; &:focus { border-color: #6B4DFF; } `;
const GenerateButton = styled.button` margin-top: auto; background: linear-gradient(135deg, #111 0%, #333 100%); color: white; padding: 18px; border-radius: 16px; border: none; font-weight: 700; font-size: 16px; cursor: pointer; display: flex; justify-content: center; align-items: center; gap: 10px; transition: all 0.2s; &:hover { transform: translateY(-2px); box-shadow: 0 8px 20px rgba(0,0,0,0.2); } &:disabled { background: #eee; color: #aaa; cursor: not-allowed; transform: none; box-shadow: none; } `;
const ChatArea = styled.div` flex: 1; background: #F8F9FA; border-radius: 24px; border: 1px solid #eee; display: flex; flex-direction: column; overflow: hidden; position: relative; `;
const ChatHeader = styled.div` padding: 20px 30px; background: white; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; align-items: center; z-index: 10; h2 { font-size: 16px; font-weight: 700; color: #333; display: flex; align-items: center; gap: 8px; } `;
const ResetButton = styled.button` background: none; border: none; cursor: pointer; color: #999; display: flex; align-items: center; gap: 6px; font-size: 12px; padding: 8px 12px; border-radius: 8px; transition: 0.2s; &:hover { background: #fee; color: #ff4d4d; } `;
const ChatScroll = styled.div` flex: 1; padding: 30px; overflow-y: auto; display: flex; flex-direction: column; gap: 24px; &::-webkit-scrollbar { width: 6px; } &::-webkit-scrollbar-thumb { background-color: #ddd; border-radius: 3px; } `;
const MessageBubble = styled.div` display: flex; flex-direction: column; max-width: 800px; align-self: ${props => props.$isUser ? 'flex-end' : 'flex-start'}; ${props => props.$isUser ? css` align-items: flex-end; .bubble { background: #333; color: white; border-radius: 20px 20px 4px 20px; padding: 12px 20px; white-space: pre-line; } ` : css` align-items: flex-start; .bubble { background: white; color: #333; border: 1px solid #eee; border-radius: 20px 20px 20px 4px; padding: 16px 24px; box-shadow: 0 2px 10px rgba(0,0,0,0.03); white-space: pre-line; line-height: 1.6; } `} .sender { font-size: 12px; color: #888; margin-bottom: 6px; margin-left: 4px; display: flex; align-items: center; gap: 4px; } `;
const ProductGrid = styled.div` display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-top: 16px; width: 100%; `;
const ProductCard = styled.div` background: white; border: 1px solid #eee; border-radius: 16px; overflow: hidden; transition: all 0.2s; cursor: pointer; position: relative; &:hover { transform: translateY(-4px); box-shadow: 0 10px 20px rgba(0,0,0,0.05); border-color: #6B4DFF; } ${props => props.$selected && css` border: 2px solid #6B4DFF; box-shadow: 0 0 0 4px rgba(107, 77, 255, 0.1); `} `;
const CardImage = styled.div` height: 140px; background: #f0f0f0; display: flex; align-items: center; justify-content: center; position: relative; img { width: 100%; height: 100%; object-fit: cover; } .brand-badge { position: absolute; top: 10px; left: 10px; background: rgba(0,0,0,0.7); color: white; font-size: 10px; font-weight: 700; padding: 4px 8px; border-radius: 4px; } `;
const CardContent = styled.div` padding: 16px; `;
const ProductName = styled.div` font-weight: 700; font-size: 15px; color: #222; margin-bottom: 8px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; `;
const TagContainer = styled.div` display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; `;
const TagChip = styled.span` font-size: 11px; color: #555; background: #f5f5f5; padding: 4px 8px; border-radius: 4px; font-weight: 500; `;
const InputArea = styled.div` padding: 20px; background: white; border-top: 1px solid #eee; display: flex; gap: 12px; align-items: center; `;
const ChatInput = styled.input` flex: 1; padding: 14px 20px; border: 1px solid #ddd; border-radius: 30px; font-size: 14px; outline: none; &:focus { border-color: #6B4DFF; } `;
const SendBtn = styled.button` width: 44px; height: 44px; border-radius: 50%; background: #6B4DFF; color: white; border: none; cursor: pointer; display: flex; align-items: center; justify-content: center; &:hover { background: #5a3de0; } `;

/* --- [1-2] 시뮬레이션 모달 스타일 --- */
const ModalOverlay = styled.div` position: fixed; top: 0; left: 0; right: 0; bottom: 0; background-color: rgba(0, 0, 0, 0.6); display: flex; justify-content: center; align-items: center; z-index: 1000; backdrop-filter: blur(5px); `;
const ModalBox = styled.div` background: white; width: 600px; max-height: 90vh; overflow-y: auto; border-radius: 24px; padding: 30px; box-shadow: 0 20px 60px rgba(0,0,0,0.3); position: relative; `;
const GeneratedBox = styled.div` background: #f8f9fa; border: 1px solid #eee; border-radius: 12px; padding: 20px; margin-top: 15px; min-height: 120px; white-space: pre-line; line-height: 1.6; color: #444; font-size: 15px; `;
const ActionBtn = styled.button` flex: 1; padding: 12px; border-radius: 12px; border: none; font-weight: 700; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 8px; transition: 0.2s; background: ${props => props.$primary ? '#6B4DFF' : '#f0f0f0'}; color: ${props => props.$primary ? 'white' : '#555'}; &:hover { transform: translateY(-2px); filter: brightness(0.95); } &:disabled { opacity: 0.6; cursor: not-allowed; } `;

/* --- [2] 메인 컴포넌트 --- */
export default function Message() {
  const { messages, addMessage, clearChat } = useChat();
  const { addToast } = useToast();
  
  const [isGenerating, setIsGenerating] = useState(false);
  const [selectedProduct, setSelectedProduct] = useState(null);
  const scrollRef = useRef(null);

  const [personas, setPersonas] = useState([]);
  
  // ✅ 기본 설정
  const [config, setConfig] = useState({
    personaId: '', purpose: '신제품 홍보', category: '스킨케어', season: '환절기'
  });

  const [currentThreadId, setCurrentThreadId] = useState(null);

  const [isSimModalOpen, setIsSimModalOpen] = useState(false);
  const [simProduct, setSimProduct] = useState(null); 
  const [simMessage, setSimMessage] = useState("");
  const [simLoading, setSimLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages]);

  // ✅ 페르소나 데이터 로드
  useEffect(() => {
    const fetchPersonas = async () => {
      try {
        const response = await api.get('/pipeline/personas');
        const rawData = Array.isArray(response.data) ? response.data : response.data.personas || [];
        
        const pData = rawData.map(p => ({
          ...p,
          persona_id: p.persona_id || p.id,
          displayLabel: `${p.name} / ${p.age}세 / ${Array.isArray(p.skin_type) ? p.skin_type[0] : (p.skin_type || '정보없음')}`
        }));
        
        setPersonas(pData);
        
        if (pData.length > 0) setConfig(prev => ({ ...prev, personaId: pData[0].persona_id }));
        
        if (messages.length === 0) {
           addMessage({ id: Date.now(), role: 'ai', text: '안녕하세요! 페르소나를 선택하고 맞춤 상품을 추천받아보세요.' });
        }
      } catch (err) {
        console.error("데이터 로드 실패:", err);
      }
    };
    fetchPersonas();
  }, []); 

  const handleClearChat = () => {
    if (window.confirm("대화 내용을 모두 삭제하시겠습니까?")) {
      clearChat();
      setCurrentThreadId(null);
      addMessage({ id: Date.now(), role: 'ai', text: '대화가 초기화되었습니다. 새로운 타겟을 설정해주세요.' });
    }
  };

  /* -------------------------------------------
     1단계: 상품 추천 요청 (CRM API 호출)
  ------------------------------------------- */
  const handleRecommend = async () => {
    if (!config.personaId) { alert("페르소나를 먼저 선택해주세요."); return; }
    setIsGenerating(true);
    
    const targetPersona = personas.find(p => String(p.persona_id) === String(config.personaId));
    
    // CRM API 호출용 데이터 구성
    const userInput = JSON.stringify({
        persona_id: config.personaId,
        purpose: config.purpose,
        product_categories: [config.category], 
        season: config.season,
        persona_detail: targetPersona 
    });
    
    const displayPrompt = `[${config.purpose}] ${targetPersona?.name || '고객'}님을 위한 ${config.season} ${config.category} 추천 부탁해.`;
    
    addMessage({ id: Date.now(), role: 'user', text: displayPrompt });

    try {
      const response = await api.post('/crm/generate', {
        user_input: userInput,
        thread_id: currentThreadId 
      });
      
      const result = response.data;
      
      // ✅ [중요] thread_id 저장 로직 강화
      console.log("👉 [DEBUG] 1단계 서버 응답:", result);
      
      if (result.thread_id) {
          console.log("✅ thread_id 저장됨:", result.thread_id);
          setCurrentThreadId(result.thread_id);
      } else {
          console.error("🚨 서버 응답에 thread_id가 없습니다!");
      }

      const mappedProducts = (result.recommended_products || []).map(p => ({
          id: p.product_id, 
          name: p.product_name || "상품명 없음",
          brand: p.brand || "AMORE",
          image: p.image_url || "https://dummyimage.com/300x300/eee/aaa",
          tags: p.keywords || ["AI추천"],
          price: p.sale_price,
          oneLineReview: p.description ? (p.description.length > 50 ? p.description.substring(0, 50) + "..." : p.description) : "맞춤 솔루션 아이템"
      }));

      addMessage({ 
        id: Date.now() + 1, 
        role: 'ai', 
        text: `분석 결과, ${mappedProducts.length}개의 상품이 추천되었습니다.\n원하시는 상품을 선택하시면 마케팅 메시지를 생성해 드립니다.`, 
        products: mappedProducts 
      });

    } catch (error) {
      console.error("추천 실패:", error);
      const errMsg = error.response?.data?.detail || error.message;
      addMessage({ id: Date.now(), role: 'ai', text: `오류가 발생했습니다: ${errMsg}` });
    } finally {
      setIsGenerating(false);
    }
  };

  const handleProductClick = async (product) => {
    setSelectedProduct(product.id);
    setSimProduct(product);
    setIsSimModalOpen(true);
    // 모달 열릴 때 메시지 생성 시작
    await generateMarketingMessage(product.id);
  };

  /* -------------------------------------------
     2단계: 마케팅 메시지 생성 (CRM API 호출)
  ------------------------------------------- */
  const generateMarketingMessage = async (productId) => {
    setSimLoading(true);
    setSimMessage(""); 

    try {
      // ✅ [중요] thread_id 검증 로직 추가 (없으면 요청 막음)
      if (!currentThreadId) {
        alert("세션 정보가 없습니다. 제품 추천을 다시 받아주세요.");
        console.error("🚨 [ERROR] currentThreadId가 null입니다. 요청을 중단합니다.");
        setSimLoading(false);
        return; // ⛔️ 실행 중단
      }

      console.log(`🚀 메시지 생성 요청 (Thread: ${currentThreadId}, Product: ${productId})`);

      const response = await api.post('/crm/select-product', {
        thread_id: currentThreadId, // 저장된 ID 전송
        selected_product_id: productId
      });

      const result = response.data;
      
      let finalMsg = "";
      if (result.final_message) {
          if (typeof result.final_message === 'string') {
              finalMsg = result.final_message;
          } else {
              finalMsg = result.final_message.message || JSON.stringify(result.final_message);
          }
      } else {
          finalMsg = "메시지를 생성하지 못했습니다.";
      }
      
      setSimMessage(finalMsg);

    } catch (e) {
      console.error("메시지 생성 에러:", e);
      setSimMessage(`오류 발생: ${e.response?.data?.detail || e.message}`);
    } finally {
      setSimLoading(false);
    }
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(simMessage);
    setCopied(true);
    addToast("클립보드에 복사되었습니다.", "success");
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Container>
      <Sidebar>
        <SidebarHeader><Settings size={20} /><h3>Target Config</h3></SidebarHeader>
        <FormGroup>
          <SectionLabel>Target Persona</SectionLabel>
          <Select value={config.personaId} onChange={(e) => setConfig({...config, personaId: e.target.value})}>
            {personas.length > 0 ? personas.map(p => <option key={p.persona_id} value={p.persona_id}>{p.displayLabel}</option>) : <option value="">데이터 없음</option>}
          </Select>
        </FormGroup>
        
        <FormGroup>
          <SectionLabel>Purpose</SectionLabel>
          <Select value={config.purpose} onChange={(e) => setConfig({...config, purpose: e.target.value})}>
            <option>브랜드/제품 첫소개</option>
            <option>신제품 홍보</option>
            <option>베스트셀러 제품 소개</option>
            <option>프로모션/이벤트 소개</option>
            <option>성분/효능 강조 소개</option>
            <option>피부타입/고민 강조 소개</option>
            <option>라이프스타일/연령대 강조 소개</option>
          </Select>
        </FormGroup>

        <FormGroup><SectionLabel>Category</SectionLabel><Input value={config.category} onChange={(e) => setConfig({...config, category: e.target.value})} /></FormGroup>
        <FormGroup><SectionLabel>Season</SectionLabel><Input value={config.season} onChange={(e) => setConfig({...config, season: e.target.value})} /></FormGroup>
        <GenerateButton onClick={handleRecommend} disabled={isGenerating}>
          {isGenerating ? 'AI가 분석 중...' : '맞춤 제품 추천받기'} <Wand2 size={18} className={isGenerating ? 'spin' : ''} />
        </GenerateButton>
      </Sidebar>
      <ChatArea>
        <ChatHeader>
          <div><h2 style={{margin:0}}><Bot size={20} color="#6B4DFF"/> AI Merchandiser Agent</h2><div style={{fontSize:'12px', color:'#888', marginTop: 4}}>Powered by Amore GPT</div></div>
          <ResetButton onClick={handleClearChat}><Trash2 size={14} /> 대화 초기화</ResetButton>
        </ChatHeader>
        <ChatScroll ref={scrollRef}>
          {(messages || []).map((msg, idx) => (
            <MessageBubble key={msg.id || idx} $isUser={msg.role === 'user'}>
              <div className="sender">{msg.role === 'ai' ? <><Sparkles size={12}/> AI Agent</> : 'Me'}</div>
              {msg.text && <div className="bubble">{msg.text}</div>}
              {msg.products && msg.products.length > 0 && (
                <ProductGrid>
                  {msg.products.map(product => (
                    <ProductCard key={product.id} onClick={() => handleProductClick(product)} $selected={selectedProduct === product.id}>
                      <CardImage><span className="brand-badge">{product.brand}</span><img src={product.image} alt={product.name} onError={(e)=>e.target.style.display='none'} /></CardImage>
                      <CardContent>
                        <ProductName>{product.name}</ProductName>
                        <div style={{fontSize: '12px', color: '#666', marginBottom: '10px', height: '32px', overflow: 'hidden', textOverflow: 'ellipsis', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical'}}>
                          {product.oneLineReview}
                        </div>
                        <TagContainer>{product.tags?.slice(0, 3).map((t,i)=><TagChip key={i}>{t}</TagChip>)}</TagContainer>
                      </CardContent>
                    </ProductCard>
                  ))}
                </ProductGrid>
              )}
            </MessageBubble>
          ))}
          {isGenerating && <div style={{display:'flex', gap:'8px', alignItems:'center', color:'#888', paddingLeft:'10px'}}><Sparkles size={14} className="spin"/> 분석 중...</div>}
        </ChatScroll>
        <InputArea><ShoppingBag size={20} color="#bbb" /><ChatInput placeholder="추천된 가이드에 대해 더 물어보세요" disabled /><SendBtn disabled><Send size={18} /></SendBtn></InputArea>
      </ChatArea>

      {isSimModalOpen && simProduct && (
        <ModalOverlay onClick={() => setIsSimModalOpen(false)}>
          <ModalBox onClick={e => e.stopPropagation()}>
            <div style={{display:'flex', justifyContent:'space-between', marginBottom:20, alignItems:'center'}}>
              <div style={{display:'flex', alignItems:'center', gap:10}}>
                <MessageCircle size={24} color="#6B4DFF"/>
                <h2 style={{margin:0, fontSize:20}}>마케팅 메시지 생성</h2>
              </div>
              <button onClick={() => setIsSimModalOpen(false)} style={{background:'none', border:'none', cursor:'pointer'}}><X size={24} color="#999"/></button>
            </div>
            
            <div style={{marginBottom: 20, padding: 15, background: '#fff', border: '1px solid #eee', borderRadius: 12, display:'flex', gap: 15, alignItems:'center'}}>
              <div style={{width: 60, height: 60, background: '#f5f5f5', borderRadius: 8, overflow:'hidden'}}>
                <img src={simProduct.image} alt="" style={{width:'100%', height:'100%', objectFit:'cover'}} onError={(e)=>e.target.style.display='none'}/>
              </div>
              <div>
                <div style={{fontSize: 12, color:'#666', fontWeight:'bold'}}>{simProduct.brand}</div>
                <div style={{fontSize: 14, fontWeight:'bold', color:'#333'}}>{simProduct.name}</div>
              </div>
            </div>

            <h4 style={{margin:'0 0 10px 0', fontSize:14, color:'#555'}}>생성된 메시지 (AI Agent)</h4>
            <GeneratedBox>
               {simLoading ? <div style={{display:'flex', alignItems:'center', gap:8, color:'#999'}}><RefreshCw size={16} className="spin"/> AI가 메시지를 작성 중입니다...</div> : simMessage}
            </GeneratedBox>

            <div style={{display:'flex', gap:10, marginTop:20}}>
              <ActionBtn onClick={() => generateMarketingMessage(simProduct.id)} disabled={simLoading}>
                <RefreshCw size={16}/> 다시 생성
              </ActionBtn>
              <ActionBtn $primary onClick={handleCopy} disabled={simLoading}>
                {copied ? <Check size={16}/> : <Copy size={16}/>} {copied ? '복사됨' : '복사하기'}
              </ActionBtn>
            </div>
          </ModalBox>
        </ModalOverlay>
      )}

    </Container>
  );
}