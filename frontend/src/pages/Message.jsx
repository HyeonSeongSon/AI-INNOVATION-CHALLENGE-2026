import React, { useState, useRef, useEffect } from 'react';
import styled, { css } from 'styled-components';
import { 
  Send, Settings, Sparkles, Wand2, ShoppingBag, 
  Tag, CheckCircle, ChevronRight, Bot 
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';

/* --- [1] 레이아웃 및 사이드바 스타일 (기존 유지 + 일부 수정) --- */
const Container = styled.div`
  display: flex;
  height: calc(100vh - 100px);
  gap: 24px;
  max-width: 1400px;
  margin: 0 auto;
`;

const Sidebar = styled.div`
  width: 340px;
  background: white;
  border-radius: 24px;
  border: 1px solid #eee;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 24px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.02);
`;

const SidebarHeader = styled.div`
  display: flex; align-items: center; gap: 10px; padding-bottom: 20px; border-bottom: 1px solid #f0f0f0;
  h3 { font-size: 18px; font-weight: 800; color: #111; }
`;

const SectionLabel = styled.label`
  font-size: 12px; font-weight: 700; color: #888; margin-bottom: 8px; display: block; text-transform: uppercase; letter-spacing: 0.5px;
`;

const FormGroup = styled.div` display: flex; flex-direction: column; `;

const Input = styled.input`
  padding: 14px; border: 1px solid #e0e0e0; border-radius: 12px; font-size: 14px; outline: none; transition: 0.2s;
  &:focus { border-color: #6B4DFF; box-shadow: 0 0 0 3px rgba(107, 77, 255, 0.1); }
`;

const Select = styled.select`
  padding: 14px; border: 1px solid #e0e0e0; border-radius: 12px; font-size: 14px; outline: none; background: white; cursor: pointer; transition: 0.2s;
  &:focus { border-color: #6B4DFF; }
`;

const GenerateButton = styled.button`
  margin-top: auto;
  background: linear-gradient(135deg, #111 0%, #333 100%);
  color: white; padding: 18px; border-radius: 16px; border: none;
  font-weight: 700; font-size: 16px; cursor: pointer;
  display: flex; justify-content: center; align-items: center; gap: 10px;
  transition: all 0.2s;
  
  &:hover { transform: translateY(-2px); box-shadow: 0 8px 20px rgba(0,0,0,0.2); }
  &:disabled { background: #eee; color: #aaa; cursor: not-allowed; transform: none; box-shadow: none; }
`;

/* --- [2] 채팅 및 상품 추천 영역 스타일 (신규 추가) --- */
const ChatArea = styled.div`
  flex: 1;
  background: #F8F9FA; /* 채팅 배경색 */
  border-radius: 24px;
  border: 1px solid #eee;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
`;

const ChatHeader = styled.div`
  padding: 20px 30px;
  background: white;
  border-bottom: 1px solid #eee;
  display: flex; justify-content: space-between; align-items: center;
  z-index: 10;
  h2 { font-size: 16px; font-weight: 700; color: #333; display: flex; align-items: center; gap: 8px; }
`;

const ChatScroll = styled.div`
  flex: 1;
  padding: 30px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 24px;

  /* 스크롤바 커스텀 */
  &::-webkit-scrollbar { width: 6px; }
  &::-webkit-scrollbar-thumb { background-color: #ddd; border-radius: 3px; }
`;

/* 채팅 말풍선 스타일 */
const MessageBubble = styled.div`
  display: flex;
  flex-direction: column;
  max-width: 800px;
  align-self: ${props => props.$isUser ? 'flex-end' : 'flex-start'};
  
  ${props => props.$isUser ? css`
    align-items: flex-end;
    .bubble {
      background: #333; color: white;
      border-radius: 20px 20px 4px 20px;
      padding: 12px 20px;
    }
  ` : css`
    align-items: flex-start;
    .bubble {
      background: white; color: #333;
      border: 1px solid #eee;
      border-radius: 20px 20px 20px 4px;
      padding: 16px 24px;
      box-shadow: 0 2px 10px rgba(0,0,0,0.03);
    }
  `}

  .sender { font-size: 12px; color: #888; margin-bottom: 6px; margin-left: 4px; display: flex; align-items: center; gap: 4px; }
`;

/* 상품 그리드 (3개 나열) */
const ProductGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-top: 16px;
  width: 100%;
`;

const ProductCard = styled.div`
  background: white;
  border: 1px solid #eee;
  border-radius: 16px;
  overflow: hidden;
  transition: all 0.2s;
  cursor: pointer;
  position: relative;

  &:hover {
    transform: translateY(-4px);
    box-shadow: 0 10px 20px rgba(0,0,0,0.05);
    border-color: #6B4DFF;
  }

  ${props => props.$selected && css`
    border: 2px solid #6B4DFF;
    box-shadow: 0 0 0 4px rgba(107, 77, 255, 0.1);
  `}
`;

const CardImage = styled.div`
  height: 140px;
  background: #f0f0f0;
  display: flex; align-items: center; justify-content: center;
  position: relative;
  
  img {
    width: 100%; height: 100%; object-fit: cover;
  }
  
  /* 브랜드 뱃지 */
  .brand-badge {
    position: absolute; top: 10px; left: 10px;
    background: rgba(0,0,0,0.7); color: white;
    font-size: 10px; font-weight: 700;
    padding: 4px 8px; border-radius: 4px;
  }
`;

const CardContent = styled.div`
  padding: 16px;
`;

const ProductName = styled.div`
  font-weight: 700; font-size: 15px; color: #222; margin-bottom: 8px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
`;

const TagContainer = styled.div`
  display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px;
`;

const TagChip = styled.span`
  font-size: 11px; color: #555; background: #f5f5f5;
  padding: 4px 8px; border-radius: 4px; font-weight: 500;
`;

const MarketingPoint = styled.div`
  font-size: 12px; color: #666; line-height: 1.4;
  padding-top: 10px; border-top: 1px dashed #eee;
  
  strong { color: #6B4DFF; font-weight: 600; }
`;

/* 하단 입력바 */
const InputArea = styled.div`
  padding: 20px;
  background: white;
  border-top: 1px solid #eee;
  display: flex; gap: 12px; align-items: center;
`;

const ChatInput = styled.input`
  flex: 1; padding: 14px 20px; border: 1px solid #ddd; border-radius: 30px; font-size: 14px; outline: none;
  &:focus { border-color: #6B4DFF; }
`;

const SendBtn = styled.button`
  width: 44px; height: 44px; border-radius: 50%; background: #6B4DFF; color: white; border: none; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  &:hover { background: #5a3de0; }
`;

/* --- [3] 메인 컴포넌트 --- */
export default function Message() {
  const navigate = useNavigate();
  const [isGenerating, setIsGenerating] = useState(false);
  const [messages, setMessages] = useState([
    { id: 1, type: 'ai', text: '안녕하세요! 어떤 고객에게 보낼 상품을 찾고 계신가요? 왼쪽에서 설정을 완료해주세요.' }
  ]);
  const [selectedProduct, setSelectedProduct] = useState(null);
  const scrollRef = useRef(null);

  const [config, setConfig] = useState({
    persona: '김민지/20대/수부지/가성비',
    category: '스킨케어',
    season: '환절기'
  });

  // 스크롤 자동 이동
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  // AI 추천 생성 핸들러
  const handleRecommend = () => {
    setIsGenerating(true);
    
    // 1. 사용자 요청 메시지 추가
    setMessages(prev => [...prev, { 
      id: Date.now(), 
      type: 'user', 
      text: `${config.persona.split('/')[2]} 고민이 있는 ${config.persona.split('/')[1]} 고객을 위한 ${config.season} ${config.category} 추천해줘.` 
    }]);

    // 2. AI 응답 (상품 카드 3개) 시뮬레이션
    setTimeout(() => {
      const mockProducts = [
        {
          id: 101,
          brand: "LANEIGE",
          name: "워터뱅크 블루 히알루로닉 크림",
          image: "https://images.unsplash.com/photo-1620916566398-39f1143ab7be?auto=format&fit=crop&q=80&w=300&h=300",
          tags: ["#수분폭탄", "#속건조해결", "#20대추천"],
          tone: "청량하고 산뜻한"
        },
        {
          id: 102,
          brand: "IOPE",
          name: "스템3 앰플 (알란토인 콤플렉스)",
          image: "https://images.unsplash.com/photo-1608248597279-f99d160bfbc8?auto=format&fit=crop&q=80&w=300&h=300",
          tags: ["#피부장벽", "#진정케어", "#집중회복"],
          tone: "전문적이고 신뢰감 있는"
        },
        {
          id: 103,
          brand: "ETUDE",
          name: "순정 약산성 5.5 진정 토너",
          image: "https://images.unsplash.com/photo-1556228720-1957be98f39c?auto=format&fit=crop&q=80&w=300&h=300",
          tags: ["#민감성필수", "#가성비갑", "#순한성분"],
          tone: "친근하고 순한"
        }
      ];

      setMessages(prev => [...prev, { 
        id: Date.now() + 1, 
        type: 'ai', 
        text: `분석된 페르소나에 맞춰 가장 반응이 좋을 상품 3가지를 선정했습니다.`,
        products: mockProducts 
      }]);
      setIsGenerating(false);
    }, 1500);
  };

  const handleProductSelect = (product) => {
    setSelectedProduct(product.id);
    if(window.confirm(`'${product.name}' 상품으로 메시지 생성을 진행할까요?`)) {
       // 추후 메시지 생성 로직 연결
       alert('메시지 생성 페이지로 이동합니다 (구현 예정)');
    }
  };

  return (
    <Container>
      {/* --- Sidebar (설정 영역) --- */}
      <Sidebar>
        <SidebarHeader>
          <Settings size={20} />
          <h3>Target Config</h3>
        </SidebarHeader>

        <FormGroup>
          <SectionLabel>Target Persona</SectionLabel>
          <Select value={config.persona} onChange={(e) => setConfig({...config, persona: e.target.value})}>
            <option>김민지/20대/수부지/가성비</option>
            <option>박서준/30대/건성/기능성</option>
            <option>최미란/40대/탄력/프리미엄</option>
          </Select>
        </FormGroup>

        <FormGroup>
          <SectionLabel>Product Category</SectionLabel>
          <Input 
            value={config.category} 
            onChange={(e) => setConfig({...config, category: e.target.value})} 
            placeholder="예: 수분크림, 립스틱"
          />
        </FormGroup>

        <FormGroup>
          <SectionLabel>Season / Keyword</SectionLabel>
          <Input 
            value={config.season} 
            onChange={(e) => setConfig({...config, season: e.target.value})} 
            placeholder="예: 환절기, 발렌타인데이"
          />
        </FormGroup>

        <GenerateButton onClick={handleRecommend} disabled={isGenerating}>
          {isGenerating ? 'AI가 상품 분석 중...' : '상품 추천받기'}
          <Wand2 size={18} className={isGenerating ? 'spin' : ''} />
        </GenerateButton>
      </Sidebar>

      {/* --- Chat Area (상품 추천 결과) --- */}
      <ChatArea>
        <ChatHeader>
          <h2><Bot size={20} color="#6B4DFF"/> AI Merchandiser Agent</h2>
          <div style={{fontSize:'12px', color:'#888'}}>Powered by Amore GPT</div>
        </ChatHeader>

        <ChatScroll ref={scrollRef}>
          {messages.map((msg) => (
            <MessageBubble key={msg.id} $isUser={msg.type === 'user'}>
              <div className="sender">
                {msg.type === 'ai' ? <><Sparkles size={12}/> AI Agent</> : 'Me'}
              </div>
              
              {/* 텍스트 메시지 */}
              {msg.text && <div className="bubble">{msg.text}</div>}

              {/* 상품 추천 카드 그리드 (AI 메시지에만 포함) */}
              {msg.products && (
                <ProductGrid>
                  {msg.products.map(product => (
                    <ProductCard 
                      key={product.id} 
                      onClick={() => handleProductSelect(product)}
                      $selected={selectedProduct === product.id}
                    >
                      <CardImage>
                        <span className="brand-badge">{product.brand}</span>
                        <img src={product.image} alt={product.name} />
                        {selectedProduct === product.id && 
                          <div style={{position:'absolute', inset:0, background:'rgba(107, 77, 255, 0.2)', display:'flex', alignItems:'center', justifyContent:'center'}}>
                            <CheckCircle color="white" fill="#6B4DFF" size={32}/>
                          </div>
                        }
                      </CardImage>
                      <CardContent>
                        <ProductName>{product.name}</ProductName>
                        <TagContainer>
                          {product.tags.map(tag => <TagChip key={tag}>{tag}</TagChip>)}
                        </TagContainer>
                        <MarketingPoint>
                          브랜드 톤: <strong>{product.tone}</strong>
                          <br />
                          마케팅: 20대 수부지 취향 저격
                        </MarketingPoint>
                      </CardContent>
                    </ProductCard>
                  ))}
                </ProductGrid>
              )}
            </MessageBubble>
          ))}
          {isGenerating && (
            <div style={{display:'flex', gap:'8px', alignItems:'center', color:'#888', paddingLeft:'10px'}}>
              <Sparkles size={14} className="spin"/> 상품 데이터를 분석하고 있습니다...
            </div>
          )}
        </ChatScroll>

        <InputArea>
          <ShoppingBag size={20} color="#bbb" />
          <ChatInput placeholder="추천된 상품에 대해 더 물어보세요 (예: 더 저렴한 건 없어?)" />
          <SendBtn><Send size={18} /></SendBtn>
        </InputArea>
      </ChatArea>
    </Container>
  );
}