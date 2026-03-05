import React, { useState, useRef, useEffect } from 'react';
import styled, { css } from 'styled-components';
import { 
  Send, Settings, Sparkles, Wand2, ShoppingBag, 
  Tag, Bot, Trash2, X, Copy, RefreshCw, Check, MessageCircle, Image as ImageIcon, ExternalLink 
} from 'lucide-react';

// ✅ API 및 Context
import api, { pipelineApi } from '../api';
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

const MessageBubble = styled.div` 
  display: flex; 
  flex-direction: column; 
  max-width: ${props => props.$wide ? '100%' : '800px'}; 
  align-self: ${props => props.$isUser ? 'flex-end' : 'flex-start'}; 
  ${props => props.$isUser ? css` 
    align-items: flex-end; 
    .bubble { background: #333; color: white; border-radius: 20px 20px 4px 20px; padding: 12px 20px; white-space: pre-line; } 
  ` : css` 
    align-items: flex-start; 
    .bubble { background: white; color: #333; border: 1px solid #eee; border-radius: 20px 20px 20px 4px; padding: 16px 24px; box-shadow: 0 2px 10px rgba(0,0,0,0.03); white-space: pre-line; line-height: 1.6; } 
  `} 
  .sender { font-size: 12px; color: #888; margin-bottom: 6px; margin-left: 4px; display: flex; align-items: center; gap: 4px; } 
`;

const ProductGrid = styled.div` display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-top: 16px; width: 100%; `;
const ProductCard = styled.div` 
  background: white; border: 1px solid #eee; border-radius: 16px; overflow: hidden; transition: all 0.2s; cursor: pointer; position: relative; display: flex; flex-direction: column; height: 480px; 
  &:hover { transform: translateY(-4px); box-shadow: 0 10px 20px rgba(0,0,0,0.05); border-color: #6B4DFF; } 
  ${props => props.$selected && css` border: 2px solid #6B4DFF; box-shadow: 0 0 0 4px rgba(107, 77, 255, 0.1); `} 
`;
const CardImage = styled.div` 
  height: 180px; width: 100%; background: #f9f9f9; display: flex; align-items: center; justify-content: center; position: relative; overflow: hidden; border-bottom: 1px solid #f0f0f0; 
  img { width: 100%; height: 100%; object-fit: contain; padding: 10px; transition: 0.3s; } 
  &:hover img { transform: scale(1.05); } 
  .placeholder { color: #ccc; display: flex; flex-direction: column; align-items: center; gap: 8px; font-size: 12px; }
  .brand-badge { position: absolute; top: 10px; left: 10px; background: rgba(0,0,0,0.7); color: white; font-size: 10px; font-weight: 700; padding: 4px 8px; border-radius: 4px; z-index: 2; } 
`;
const CardContent = styled.div` padding: 16px; flex: 1; display: flex; flex-direction: column; justify-content: space-between; `;
const ProductName = styled.div` font-weight: 700; font-size: 15px; color: #222; margin-bottom: 8px; line-height: 1.3; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; `;
const OneLineReview = styled.div` font-size: 14px; color: #444; background: #f0f4ff; padding: 12px; border-radius: 8px; margin-bottom: 12px; line-height: 1.6; border-left: 4px solid #6B4DFF; font-weight: 500; display: -webkit-box; -webkit-line-clamp: 5; -webkit-box-orient: vertical; overflow: hidden; flex: 1; `; 
const TagContainer = styled.div` display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; `;
const TagChip = styled.span` font-size: 10px; color: #555; background: #f0f0f0; padding: 4px 8px; border-radius: 4px; font-weight: 600; `;
const ProductLinkBtn = styled.a` display: flex; align-items: center; justify-content: center; gap: 6px; font-size: 13px; font-weight: 700; color: #6B4DFF; background: #fff; border: 1px solid #6B4DFF; padding: 10px; border-radius: 8px; text-decoration: none; transition: 0.2s; margin-top: auto; &:hover { background: #6B4DFF; color: white; } `;
const InputArea = styled.div` padding: 20px; background: white; border-top: 1px solid #eee; display: flex; gap: 12px; align-items: center; `;
const ChatInput = styled.input` flex: 1; padding: 14px 20px; border: 1px solid #ddd; border-radius: 30px; font-size: 14px; outline: none; &:focus { border-color: #6B4DFF; } `;
const SendBtn = styled.button` width: 44px; height: 44px; border-radius: 50%; background: #6B4DFF; color: white; border: none; cursor: pointer; display: flex; align-items: center; justify-content: center; &:hover { background: #5a3de0; } `;

/* --- 시뮬레이션 모달 스타일 --- */
const ModalOverlay = styled.div` position: fixed; top: 0; left: 0; right: 0; bottom: 0; background-color: rgba(0, 0, 0, 0.6); display: flex; justify-content: center; align-items: center; z-index: 1000; backdrop-filter: blur(5px); `;
const ModalBox = styled.div` background: white; width: 600px; max-height: 90vh; overflow-y: auto; border-radius: 24px; padding: 30px; box-shadow: 0 20px 60px rgba(0,0,0,0.3); position: relative; `;
const GeneratedBox = styled.div` background: #f8f9fa; border: 1px solid #eee; border-radius: 12px; padding: 20px; margin-top: 15px; min-height: 120px; line-height: 1.6; color: #444; font-size: 15px; display: flex; flex-direction: column; gap: 10px; `;

// ✅ 제목(Title) 스타일 정의
const GeneratedTitle = styled.div` font-size: 18px; font-weight: 800; color: #111; margin-bottom: 8px; padding-bottom: 12px; border-bottom: 1px solid #e0e0e0; line-height: 1.4; `;
const GeneratedContent = styled.div` white-space: pre-line; `;

const ActionBtn = styled.button` flex: 1; padding: 12px; border-radius: 12px; border: none; font-weight: 700; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 8px; transition: 0.2s; background: ${props => props.$primary ? '#6B4DFF' : '#f0f0f0'}; color: ${props => props.$primary ? 'white' : '#555'}; &:hover { transform: translateY(-2px); filter: brightness(0.95); } &:disabled { opacity: 0.6; cursor: not-allowed; } `;

/* --- [2] 메인 컴포넌트 --- */
export default function Message() {
  // ✅ 만드신 ChatContext를 사용합니다.
  const { messages, addMessage, clearChat } = useChat();
  const { addToast } = useToast();
  
  const [isGenerating, setIsGenerating] = useState(false);
  const [selectedProduct, setSelectedProduct] = useState(null);
  const scrollRef = useRef(null);

  const [personas, setPersonas] = useState([]);
  const [config, setConfig] = useState({
    personaId: '', purpose: '신제품 홍보', category: '립스틱', brand: '이니스프리'
  });

  const [currentThreadId, setCurrentThreadId] = useState(null);
  const [isSimModalOpen, setIsSimModalOpen] = useState(false);
  const [simProduct, setSimProduct] = useState(null); 
  
  // ✅ 제목/본문 분리 상태
  const [simMessage, setSimMessage] = useState("");
  const [simTitle, setSimTitle] = useState(""); 
  
  const [simLoading, setSimLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages]);

  useEffect(() => {
    const fetchPersonas = async () => {
      try {
        const response = await pipelineApi.post('/personas/list');
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

  const handleRecommend = async () => {
    if (!config.personaId) { alert("페르소나를 먼저 선택해주세요."); return; }
    setIsGenerating(true);
    
    const targetPersona = personas.find(p => String(p.persona_id) === String(config.personaId));
    
    const userInput = JSON.stringify({
        persona_id: config.personaId,
        purpose: config.purpose,
        product_categories: [config.category], 
        brand: config.brand, 
        persona_detail: targetPersona 
    });
    
    const displayPrompt = `[${config.purpose}] ${targetPersona?.name || '고객'}님을 위한 ${config.brand} ${config.category} 추천 부탁해.`;
    addMessage({ id: Date.now(), role: 'user', text: displayPrompt });

    try {
      const response = await api.post('/crm/generate', {
        user_input: userInput,
        thread_id: currentThreadId 
      });
      
      const result = response.data;
      if (result.thread_id) setCurrentThreadId(result.thread_id);

      const mappedProducts = (result.recommended_products || []).map(p => ({
          id: p.product_id, 
          name: p.product_name || "상품명 없음",
          brand: p.brand || "AMORE",
          image: p.image_url || null, 
          tags: p.keywords || ["AI추천"],
          price: p.sale_price,
          productUrl: p.product_url || p.url || "#", 
          oneLineReview: p.one_line_review || p.description || p.summary || "맞춤 솔루션 아이템입니다."
      }));

      const analysis = result.persona_analysis || {};
      const summary = analysis.summary || "고객님의 페르소나를 분석했습니다.";
      const keyNeeds = (analysis.key_needs || []).join(", ");
      
      let aiText = `🔎 **분석 결과:**\n${summary}\n\n`;
      if (keyNeeds) aiText += `💡 **핵심 니즈:** ${keyNeeds}\n\n`;
      aiText += `이러한 분석을 바탕으로 **${mappedProducts.length}개의 맞춤 솔루션 상품**을 추천해 드립니다.\n원하시는 상품을 선택하여 마케팅 메시지를 생성해보세요.`;

      addMessage({ 
        id: Date.now() + 1, 
        role: 'ai', 
        text: aiText, 
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
    await generateMarketingMessage(product.id);
  };

  // ✅ 제목/본문 분리 로직 적용
  const generateMarketingMessage = async (productId) => {
    setSimLoading(true);
    setSimMessage(""); 
    setSimTitle(""); 

    try {
      if (!currentThreadId) {
        alert("세션 정보가 없습니다. 제품 추천을 다시 받아주세요.");
        setSimLoading(false); return; 
      }

      const response = await api.post('/crm/select-product', {
        thread_id: currentThreadId,
        selected_product_id: productId
      });

      const result = response.data;
      
      if (result.final_message) {
          if (typeof result.final_message === 'object') {
             // 1. 객체일 경우 (제목 + 본문)
             setSimTitle(result.final_message.title || result.final_message.headline || "AI 마케팅 메시지");
             setSimMessage(result.final_message.message || result.final_message.content || JSON.stringify(result.final_message));
          } else {
             // 2. 문자열일 경우
             setSimTitle("AI 마케팅 메시지");
             setSimMessage(result.final_message);
          }
      } else {
          setSimTitle("생성 실패");
          setSimMessage("메시지를 생성하지 못했습니다.");
      }

    } catch (e) {
      console.error("메시지 생성 에러:", e);
      setSimTitle("오류 발생");
      setSimMessage(`오류 발생: ${e.response?.data?.detail || e.message}`);
    } finally {
      setSimLoading(false);
    }
  };

  // ✅ 제목도 같이 복사되게 수정
  const handleCopy = () => {
    const textToCopy = simTitle ? `[${simTitle}]\n\n${simMessage}` : simMessage;
    navigator.clipboard.writeText(textToCopy);
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
            <option>시즌 특가</option>
          </Select>
        </FormGroup>

        <FormGroup><SectionLabel>Category</SectionLabel><Input value={config.category} onChange={(e) => setConfig({...config, category: e.target.value})} /></FormGroup>
        <FormGroup><SectionLabel>Brand</SectionLabel><Input value={config.brand} onChange={(e) => setConfig({...config, brand: e.target.value})} /></FormGroup>
        
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
            <MessageBubble key={msg.id || idx} $isUser={msg.role === 'user'} $wide={msg.products && msg.products.length > 0}>
              <div className="sender">{msg.role === 'ai' ? <><Sparkles size={12}/> AI Agent</> : 'Me'}</div>
              {msg.text && <div className="bubble">{msg.text}</div>}
              {msg.products && msg.products.length > 0 && (
                <ProductGrid>
                  {msg.products.map(product => (
                    <ProductCard key={product.id} onClick={() => handleProductClick(product)} $selected={selectedProduct === product.id}>
                      <CardImage>
                        <span className="brand-badge">{product.brand}</span>
                        {product.image ? (
                           <img src={product.image} alt={product.name} onError={(e) => { e.target.style.display='none'; e.target.nextSibling.style.display='flex'; }} />
                        ) : null}
                        <div className="placeholder" style={{display: product.image ? 'none' : 'flex'}}>
                           <ImageIcon size={24} color="#ddd"/>
                           <span>No Image</span>
                        </div>
                      </CardImage>
                      <CardContent>
                        <ProductName>{product.name}</ProductName>
                        <OneLineReview>{product.oneLineReview}</OneLineReview>
                        <TagContainer>{product.tags?.slice(0, 3).map((t,i)=><TagChip key={i}>{t}</TagChip>)}</TagContainer>
                        <ProductLinkBtn href={product.productUrl} target="_blank" onClick={(e) => e.stopPropagation()}>
                          <ExternalLink size={14}/> 구매하러 가기
                        </ProductLinkBtn>
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
            
            <div style={{marginBottom: 20, padding: 15, background: '#fff', border: '1px solid #eee', borderRadius: 12, display:'flex', gap: 15, alignItems:'start'}}>
              <div style={{width: 60, height: 60, background: '#f5f5f5', borderRadius: 8, overflow:'hidden', flexShrink: 0}}>
                {simProduct.image ? 
                   <img src={simProduct.image} alt="" style={{width:'100%', height:'100%', objectFit:'cover'}} onError={(e)=>e.target.style.display='none'}/>
                   : <ImageIcon size={20} color="#ccc"/>
                }
              </div>
              <div style={{flex: 1}}>
                <div style={{fontSize: 12, color:'#666', fontWeight:'bold'}}>{simProduct.brand}</div>
                <div style={{fontSize: 14, fontWeight:'bold', color:'#333', marginBottom: 6}}>{simProduct.name}</div>
                
                {/* ✅ [추가됨] 모달창에 한줄평 표시 */}
                {simProduct.oneLineReview && (
                  <div style={{
                    fontSize: '12px', 
                    color: '#444', 
                    background: '#f0f4ff', 
                    padding: '6px 8px', 
                    borderRadius: '6px', 
                    lineHeight: '1.4',
                    borderLeft: '3px solid #6B4DFF',
                    marginBottom: 4,
                    display: 'inline-block'
                  }}>
                    💡 {simProduct.oneLineReview}
                  </div>
                )}

                <a href={simProduct.productUrl} target="_blank" style={{fontSize:12, color:'#6B4DFF', textDecoration:'none', display:'flex', alignItems:'center', gap:4, marginTop:4}}>
                  <ExternalLink size={12}/> 상품 페이지로 이동
                </a>
              </div>
            </div>

            <h4 style={{margin:'0 0 10px 0', fontSize:14, color:'#555'}}>생성된 메시지 (AI Agent)</h4>
            
            {/* ✅ [수정완료] 제목(GeneratedTitle)과 본문(GeneratedContent) 분리 표시 */}
            <GeneratedBox>
               {simLoading ? (
                 <div style={{display:'flex', alignItems:'center', gap:8, color:'#999'}}><RefreshCw size={16} className="spin"/> AI가 메시지를 작성 중입니다...</div>
               ) : (
                 <>
                   {simTitle && <GeneratedTitle>{simTitle}</GeneratedTitle>}
                   <GeneratedContent>{simMessage}</GeneratedContent>
                 </>
               )}
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
