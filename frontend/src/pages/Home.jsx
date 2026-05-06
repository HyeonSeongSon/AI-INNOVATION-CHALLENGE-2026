import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import styled from 'styled-components';
import { MessageSquare, Users, Package, Sparkles, ArrowRight, History, TrendingUp } from 'lucide-react';
import api, { pipelineApi, dbApi } from '../api';

/* --- 스타일 컴포넌트 (기존 유지) --- */
const PageContainer = styled.div`
  display: flex;
  flex-direction: column;
  gap: 24px;
  width: 100%;
  max-width: 1200px;
  margin: 0 auto;
`;

const Header = styled.div`
  margin-bottom: 10px;
`;

const Title = styled.h1`
  font-size: 24px;
  font-weight: 800;
  color: #333;
`;

const SubDesc = styled.p`
  color: #666;
  margin-top: 8px;
  font-size: 14px;
`;

/* 상단 통계 카드 */
const StatsGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
`;

const StatCard = styled.div`
  background: white;
  padding: 24px;
  border-radius: 16px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.03);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  height: 140px;
  border: 1px solid #f0f0f0;
  transition: transform 0.2s;

  &:hover {
    transform: translateY(-2px);
  }
`;

const StatHeader = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
`;

const StatIcon = styled.div`
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background-color: ${props => props.$bg || '#F5F6FA'};
  color: ${props => props.$color || '#555'};
  display: flex;
  align-items: center;
  justify-content: center;
`;

const StatLabel = styled.span`
  font-size: 14px;
  color: #888;
  font-weight: 600;
`;

const StatValue = styled.div`
  font-size: 32px;
  font-weight: 800;
  color: #333;
  
  span {
    font-size: 16px;
    font-weight: 500;
    margin-left: 4px;
    color: #888;
  }
`;

/* 배너 영역 */
const Banner = styled.div`
  width: 100%;
  padding: 20px 28px;
  background: linear-gradient(135deg, #6B4DFF 0%, #9F85FF 100%);
  border-radius: 16px;
  color: white;
  display: flex;
  justify-content: space-between;
  align-items: center;
  box-shadow: 0 8px 30px rgba(107, 77, 255, 0.2);
`;

const BannerContent = styled.div`
  display: flex;
  flex-direction: column;
  gap: 10px;
`;

const BannerTitle = styled.h2`
  font-size: 22px;
  font-weight: 800;
  display: flex;
  align-items: center;
  gap: 10px;
`;

const BannerText = styled.p`
  font-size: 15px;
  opacity: 0.9;
  line-height: 1.5;
`;

const ActionButton = styled.button`
  background-color: white;
  color: #6B4DFF;
  padding: 12px 24px;
  border-radius: 8px;
  font-weight: 700;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: all 0.2s;

  &:hover {
    background-color: #f0f0f0;
    transform: scale(1.02);
  }
`;

/* 하단 2단 레이아웃 */
const BottomSection = styled.div`
  display: grid;
  grid-template-columns: 1.4fr 0.6fr;
  gap: 24px;
  width: 100%;
  max-width: 1200px;
`;

const SectionBox = styled.div`
  background: white;
  padding: 24px;
  border-radius: 16px;
  border: 1px solid #eee;
  min-width: 0;
  overflow: hidden;
`;

const SectionHeader = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
`;

const SectionTitle = styled.h3`
  font-size: 18px;
  font-weight: bold;
  color: #333;
  display: flex;
  align-items: center;
  gap: 8px;
`;

/* 최근 생성 리스트 스타일 */
const MessageItem = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  background-color: #FAFAFA;
  border-radius: 12px;
  margin-bottom: 12px;
  border: 1px solid #f5f5f5;
  transition: background 0.2s;

  &:hover {
    background-color: #F0F0FF;
    border-color: #DEDEFE;
  }
`;

const MessageInfo = styled.div`
  display: flex;
  flex-direction: column;
  gap: 4px;
`;

const MessageTag = styled.span`
  font-size: 11px;
  font-weight: 700;
  color: #6B4DFF;
  background-color: #F0EBFF;
  padding: 4px 8px;
  border-radius: 4px;
  width: fit-content;
`;

const MessageTitle = styled.span`
  font-size: 15px;
  font-weight: 600;
  color: #333;
`;

const MessageMeta = styled.div`
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 2px;
`;

const QualityBadge = styled.span`
  font-size: 12px;
  font-weight: 700;
  color: ${props => {
    if (props.$score >= 4.0) return '#2E7D32';
    if (props.$score >= 3.0) return '#E65100';
    return '#888';
  }};
  background-color: ${props => {
    if (props.$score >= 4.0) return '#E8F5E9';
    if (props.$score >= 3.0) return '#FFF3E0';
    return '#f5f5f5';
  }};
  padding: 3px 8px;
  border-radius: 4px;
`;

const DateInfo = styled.span`
  font-size: 12px;
  color: #aaa;
`;

/* 최근 페르소나 리스트 스타일 */
const PersonaItem = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 0;
  border-bottom: 1px solid #f5f5f5;

  &:last-child {
    border-bottom: none;
  }
`;

const PersonaName = styled.span`
  font-size: 14px;
  font-weight: 600;
  color: #333;
`;

const PersonaMeta = styled.span`
  font-size: 12px;
  color: #aaa;
`;


/* --- 메인 컴포넌트 --- */
export default function Home() {
  const navigate = useNavigate();

  const [personaStats, setPersonaStats] = useState({ count: 0, list: [] });
  const [recentMessages, setRecentMessages] = useState([]);
  const [messageCount, setMessageCount] = useState(null);
  const [productCount, setProductCount] = useState(null);

  useEffect(() => {
    dbApi.get('/generated-messages', { params: { user_id: 'son', limit: 3 } })
      .then(res => {
        setRecentMessages(res.data?.items || []);
        setMessageCount(res.data?.total ?? null);
      })
      .catch(() => {});

    dbApi.get('/products', { params: { page_size: 1 } })
      .then(res => setProductCount(res.data?.total ?? null))
      .catch(() => {});
  }, []);

  const handleMessageClick = (item) => {
    navigate('/generated-messages', { state: { openMessage: item } });
  };

  const parseTag = (item) => {
    return item.purpose || item.conversation_title?.match(/\[(.+?)\]/)?.[1] || '마케팅 메시지';
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')}`;
  };

  // 페르소나 데이터 불러오기 (실제 DB 연동)
  useEffect(() => {
    const fetchPersonas = async () => {
      try {
        const response = await pipelineApi.post('/personas/list');

        // 백엔드 응답 구조에 따라 데이터 추출 (배열인지, 객체 안의 배열인지 확인)
        const data = Array.isArray(response.data) ? response.data : (response.data.personas || []);

        setPersonaStats({
          count: data.length,
          list: data.slice(0, 5)
        });
      } catch (error) {
        console.error("페르소나 데이터 로드 실패:", error);
        // 에러 시 기존 상태 유지 (0개)
      }
    };
    fetchPersonas();
  }, []);

  return (
    <PageContainer>
      <Header>
        <Title>Dashboard</Title>
        <SubDesc>아모레몰 AI 마케팅 에이전트에 오신 것을 환영합니다.</SubDesc>
      </Header>

      {/* 상단 통계 카드 */}
      <StatsGrid>
        <StatCard onClick={() => navigate('/generated-messages')} style={{ cursor: 'pointer' }}>
          <StatHeader>
            <StatLabel>생성된 메시지</StatLabel>
            <StatIcon $bg="#E0F2F1" $color="#00695C"><MessageSquare size={20} /></StatIcon>
          </StatHeader>
          <StatValue>{messageCount ?? '-'} <span>건</span></StatValue>
        </StatCard>
        
        <StatCard onClick={() => navigate('/persona')} style={{cursor: 'pointer'}}>
          <StatHeader>
            <StatLabel>등록된 페르소나</StatLabel>
            <StatIcon $bg="#F3E5F5" $color="#7B1FA2"><Users size={20} /></StatIcon>
          </StatHeader>
          {/* ✅ 실제 DB 데이터 반영 */}
          <StatValue>{personaStats.count} <span>개</span></StatValue>
        </StatCard>
        
        <StatCard onClick={() => navigate('/products')} style={{ cursor: 'pointer' }}>
          <StatHeader>
            <StatLabel>등록된 상품</StatLabel>
            <StatIcon $bg="#FFF3E0" $color="#E65100"><Package size={20} /></StatIcon>
          </StatHeader>
          <StatValue>{productCount ?? '-'} <span>개</span></StatValue>
        </StatCard>
      </StatsGrid>

      {/* 메인 배너 */}
      <Banner>
        <BannerContent>
          <BannerTitle>
            <Sparkles fill="white" size={20} />
            새로운 캠페인 메시지가 필요하신가요?
          </BannerTitle>
          <BannerText>
            브랜드 톤앤매너와 고객 페르소나를 기반으로<br/>
            가장 자연스럽고 구매 전환율이 높은 메시지를 생성해 드립니다.
          </BannerText>
        </BannerContent>
        <ActionButton onClick={() => navigate('/message')}>
          메시지 생성하기 <ArrowRight size={18} />
        </ActionButton>
      </Banner>

      {/* 하단 영역 */}
      <BottomSection>
        {/* 왼쪽: 최근 생성 이력 (하드코딩 유지 - DB에 메시지 저장 기능 없음) */}
        <SectionBox>
          <SectionHeader>
            <SectionTitle><History size={18}/> 최근 생성 메시지 내역</SectionTitle>
          </SectionHeader>
          
          {Array.from({ length: 3 }).map((_, i) => {
            const item = recentMessages[i];
            if (item) {
              return (
                <MessageItem key={item.id} onClick={() => handleMessageClick(item)} style={{cursor:'pointer'}}>
                  <MessageInfo>
                    <MessageTag>{parseTag(item)}</MessageTag>
                    <MessageTitle>"{item.title || '(제목 없음)'}"</MessageTitle>
                    <MessageMeta>
                      {item.llm_score_overall != null && (
                        <QualityBadge $score={item.llm_score_overall}>
                          품질 {Number(item.llm_score_overall).toFixed(1)}
                        </QualityBadge>
                      )}
                      <DateInfo>{formatDate(item.created_at)}</DateInfo>
                    </MessageMeta>
                  </MessageInfo>
                </MessageItem>
              );
            }
            return (
              <MessageItem key={`empty-${i}`} onClick={() => navigate('/message')} style={{cursor:'pointer', opacity:0.5}}>
                <MessageInfo>
                  <MessageTitle style={{color:'#aaa', fontStyle:'italic'}}>메시지를 생성해보세요.</MessageTitle>
                </MessageInfo>
              </MessageItem>
            );
          })}
        </SectionBox>

        {/* 오른쪽: 등록된 페르소나 목록 (실제 데이터 연동) */}
        <SectionBox>
          <SectionHeader>
            <SectionTitle><TrendingUp size={18}/> 최근 등록된 페르소나</SectionTitle>
          </SectionHeader>
          
          {personaStats.list.length > 0 ? (
            personaStats.list.map((persona, index) => (
              <PersonaItem
                key={persona.id || index}
                onClick={() => navigate('/persona', { state: { openPersonaId: persona.persona_id || persona.id } })}
                style={{ cursor: 'pointer' }}
              >
                <PersonaName>{persona.name}{persona.age ? ` · ${persona.age}세` : ''}</PersonaName>
                <PersonaMeta>{formatDate(persona.persona_created_at)}</PersonaMeta>
              </PersonaItem>
            ))
          ) : (
            <PersonaItem>
              <PersonaName style={{ color: '#bbb', fontStyle: 'italic' }}>등록된 페르소나가 없습니다.</PersonaName>
            </PersonaItem>
          )}
        </SectionBox>
      </BottomSection>
    </PageContainer>
  );
}