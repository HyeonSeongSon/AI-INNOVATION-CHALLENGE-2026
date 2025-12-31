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
  // ✅ useChat 사용 (DB 저장 대신 로컬 스토리지 사용)
  const { messages, addMessage, clearChat } = useChat();
  const { addToast } = useToast();
  
  const [isGenerating, setIsGenerating] = useState(false);
  const [selectedProduct, setSelectedProduct] = useState(null);
  const scrollRef = useRef(null);

  const [personas, setPersonas] = useState([]);
  const [config, setConfig] = useState({
    personaId: '', purpose: '신상품', category: '스킨케어', season: '환절기'
  });

  // --- 시뮬레이션 모달 상태 ---
  const [isSimModalOpen, setIsSimModalOpen] = useState(false);
  const [simProduct, setSimProduct] = useState(null); 
  const [simMessage, setSimMessage] = useState("");
  const [simLoading, setSimLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  // 스크롤 자동 이동
  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages]);

  // 페이지 로드 시 페르소나 데이터 가져오기
  useEffect(() => {
    const fetchPersonas = async () => {
      try {
        const pResponse = await api.get('/personas');
        const pData = pResponse.data.map(p => ({
          ...p, 
          // 스키마 변경 반영 (skin_types -> skin_types[0] 등 안전하게 접근)
          displayLabel: `${p.name} / ${p.age}세 / ${p.skin_types?.[0] || '피부타입미정'}`
        }));
        setPersonas(pData);
        if (pData.length > 0) setConfig(prev => ({ ...prev, personaId: pData[0].id }));
        
        // 초기 메시지 (로컬 저장소에 없을 경우에만 추가)
        if (messages.length === 0) {
           addMessage({ id: Date.now(), role: 'ai', text: '안녕하세요! 페르소나를 선택하고 맞춤 상품을 추천받아보세요.' });
        }
      } catch (err) {
        console.error("데이터 로드 실패:", err);
      }
    };
    fetchPersonas();
  }, []); // 의존성 배열 비움 (한 번만 실행)

  // 대화 초기화 (로컬 스토리지 비우기)
  const handleClearChat = () => {
    if (window.confirm("대화 내용을 모두 삭제하시겠습니까?")) {
      clearChat();
      addMessage({ id: Date.now(), role: 'ai', text: '대화가 초기화되었습니다. 새로운 타겟을 설정해주세요.' });
    }
  };

  // 추천 요청
  const handleRecommend = async () => {
    if (!config.personaId) { alert("페르소나를 먼저 선택해주세요."); return; }
    setIsGenerating(true);
    
    // 타겟 페르소나 찾기
    const targetPersona = personas.find(p => String(p.id) === String(config.personaId));
    const userPrompt = `[${config.purpose}] ${targetPersona?.name || '고객'}님에게 적합한 ${config.season} ${config.category} 제품 유형을 추천해줘.`;
    
    // 로컬 스토리지에 메시지 추가
    addMessage({ id: Date.now(), role: 'user', text: userPrompt });

    try {
      // API 호출 (persona_id는 이제 문자열(UUID)일 수 있음)
      const response = await api.post('/recommend', {
        persona_id: config.personaId, // 문자열 그대로 전송
        purpose: config.purpose,
        category: config.category, 
        season: config.season
      });
      const result = response.data; 
      
      const mappedProducts = (result.products || []).map(p => ({
          id: p.id,
          name: p.product_name || "상품명 없음",
          brand: p.brand_name || "AMORE",
          image: p.image_urls?.[0] || "https://dummyimage.com/300x300/eee/aaa",
          tags: p.tags ? Object.keys(p.tags) : ["추천템"],
          tone: "AI 매칭 완료",
          price: p.sale_price
      }));

      // AI 응답 추가
      addMessage({ 
        id: Date.now() + 1, 
        role: 'ai', 
        text: result.reasoning, 
        products: mappedProducts 
      });

    } catch (error) {
      console.error("추천 실패:", error);
      addMessage({ id: Date.now(), role: 'ai', text: `오류가 발생했습니다: ${error.message}` });
    } finally {
      setIsGenerating(false);
    }
  };

  // 상품 클릭 시 모달 열기 + 메시지 생성 시작
  const handleProductClick = async (product) => {
    setSelectedProduct(product.id);
    setSimProduct(product);
    setIsSimModalOpen(true);
    
    await generateMarketingMessage(product);
  };

  // 메시지 생성 함수 (Mock - 필요시 백엔드 API 연동 가능)
  const generateMarketingMessage = async (product) => {
    setSimLoading(true);
    try {
      const targetPersona = personas.find(p => String(p.id) === String(config.personaId));
      
      // 1.5초 대기 (AI 생성 척)
      await new Promise(r => setTimeout(r, 1500)); 
      
      // 피부 타입 정보 안전하게 가져오기
      const skinStr = Array.isArray(targetPersona?.skin_types) 
        ? targetPersona.skin_types.join(', ') 
        : (targetPersona?.skin_types || '고객');

      const msg = `[${product.brand}] ${targetPersona?.name}님을 위한 특별 제안!\n\n${config.season}철 고민이신 ${skinStr} 피부에 딱 맞는 솔루션,\n'${product.name}'을(를) 만나보세요.\n\n지금 구매 시 특별 혜택을 드립니다.`;
      
      setSimMessage(msg);
    } catch (e) {
      setSimMessage("메시지 생성 중 오류가 발생했습니다.");
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
            {personas.length > 0 ? personas.map(p => <option key={p.id} value={p.id}>{p.displayLabel || p.name}</option>) : <option value="">데이터 없음</option>}
          </Select>
        </FormGroup>
        <FormGroup><SectionLabel>Purpose</SectionLabel><Select value={config.purpose} onChange={(e) => setConfig({...config, purpose: e.target.value})}><option>신상품</option><option>프로모션</option><option>재구매유도</option></Select></FormGroup>
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
                      <CardImage><span className="brand-badge">{product.brand}</span><img src={product.image} alt={product.name} /></CardImage>
                      <CardContent><ProductName>{product.name}</ProductName><TagContainer>{product.tags?.map(t=><TagChip key={t}>{t}</TagChip>)}</TagContainer></CardContent>
                    </ProductCard>
                  ))}
                </ProductGrid>
              )}
            </MessageBubble>
          ))}
          {isGenerating && <div style={{display:'flex', gap:'8px', alignItems:'center', color:'#888', paddingLeft:'10px'}}><Sparkles size={14} className="spin"/> 분석 중...</div>}
        </ChatScroll>
        <InputArea><ShoppingBag size={20} color="#bbb" /><ChatInput placeholder="추천된 가이드에 대해 더 물어보세요" /><SendBtn><Send size={18} /></SendBtn></InputArea>
      </ChatArea>

      {/* ✅ [모달] 마케팅 메시지 생성 */}
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
                <img src={simProduct.image} alt="" style={{width:'100%', height:'100%', objectFit:'cover'}}/>
              </div>
              <div>
                <div style={{fontSize: 12, color:'#666', fontWeight:'bold'}}>{simProduct.brand}</div>
                <div style={{fontSize: 14, fontWeight:'bold', color:'#333'}}>{simProduct.name}</div>
              </div>
            </div>

            <h4 style={{margin:'0 0 10px 0', fontSize:14, color:'#555'}}>생성된 메시지 (초안)</h4>
            <GeneratedBox>
               {simLoading ? <div style={{display:'flex', alignItems:'center', gap:8, color:'#999'}}><RefreshCw size={16} className="spin"/> AI가 메시지를 작성 중입니다...</div> : simMessage}
            </GeneratedBox>

            <div style={{display:'flex', gap:10, marginTop:20}}>
              <ActionBtn onClick={() => generateMarketingMessage(simProduct)} disabled={simLoading}>
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