import React from 'react';
import { useNavigate } from 'react-router-dom'; // 페이지 이동 훅 추가
import styled from 'styled-components';
import { MessageSquare, Users, Zap, Sparkles, ArrowRight, History, TrendingUp } from 'lucide-react';

/* --- 스타일 컴포넌트 --- */
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
  padding: 30px;
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
  grid-template-columns: 1.4fr 0.6fr; /* 7:3 비율로 조정 */
  gap: 24px;
`;

const SectionBox = styled.div`
  background: white;
  padding: 24px;
  border-radius: 16px;
  border: 1px solid #eee;
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

const PersonaInfo = styled.span`
  font-size: 13px;
  color: #888;
`;

/* 인기 페르소나 랭킹 스타일 */
const RankItem = styled.div`
  display: flex;
  align-items: center;
  padding: 12px 0;
  border-bottom: 1px solid #f5f5f5;

  &:last-child {
    border-bottom: none;
  }
`;

const RankNumber = styled.span`
  font-size: 16px;
  font-weight: 800;
  color: ${props => props.$top ? '#6B4DFF' : '#bbb'};
  width: 30px;
`;

const RankName = styled.span`
  font-size: 14px;
  font-weight: 600;
  color: #444;
  flex: 1;
`;

const RankCount = styled.span`
  font-size: 12px;
  color: #999;
  background: #f5f5f5;
  padding: 2px 8px;
  border-radius: 10px;
`;


/* --- 메인 컴포넌트 --- */
export default function Home() {
  const navigate = useNavigate();

  return (
    <PageContainer>
      <Header>
        <Title>Dashboard</Title>
        <SubDesc>아모레몰 AI 마케팅 에이전트에 오신 것을 환영합니다.</SubDesc>
      </Header>

      {/* 상단 통계 카드 */}
      <StatsGrid>
        <StatCard>
          <StatHeader>
            <StatLabel>오늘 생성된 메시지</StatLabel>
            <StatIcon $bg="#E0F2F1" $color="#00695C"><MessageSquare size={20} /></StatIcon>
          </StatHeader>
          <StatValue>24 <span>건</span></StatValue>
        </StatCard>
        
        <StatCard>
          <StatHeader>
            <StatLabel>등록된 페르소나</StatLabel>
            <StatIcon $bg="#F3E5F5" $color="#7B1FA2"><Users size={20} /></StatIcon>
          </StatHeader>
          <StatValue>8 <span>개</span></StatValue>
        </StatCard>
        
        <StatCard>
          <StatHeader>
            <StatLabel>AI 최적화 상태</StatLabel>
            <StatIcon $bg="#FFF3E0" $color="#E65100"><Zap size={20} /></StatIcon>
          </StatHeader>
          <StatValue style={{fontSize: '24px', color: '#E65100'}}>Optimal</StatValue>
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
        {/* 왼쪽: 최근 생성 이력 */}
        <SectionBox>
          <SectionHeader>
            <SectionTitle><History size={18}/> 최근 생성 내역</SectionTitle>
          </SectionHeader>
          
          <MessageItem>
            <MessageInfo>
              <MessageTag>설화수 / 프로모션</MessageTag>
              <MessageTitle>"어머니, 이번 추석엔 피부 건강을 선물하세요"</MessageTitle>
              <PersonaInfo>Target: 구매력 높은 50대 여성</PersonaInfo>
            </MessageInfo>
          </MessageItem>

          <MessageItem>
            <MessageInfo>
              <MessageTag>라네즈 / 신제품 알림</MessageTag>
              <MessageTitle>"건조한 환절기, 워터뱅크로 수분 장벽 지키기 💧"</MessageTitle>
              <PersonaInfo>Target: 20대 수부지 대학생</PersonaInfo>
            </MessageInfo>
          </MessageItem>

          <MessageItem>
            <MessageInfo>
              <MessageTag>헤라 / 재구매 유도</MessageTag>
              <MessageTitle>"블랙쿠션 다 쓰셨나요? VIP 전용 혜택 확인하세요"</MessageTitle>
              <PersonaInfo>Target: 30대 오피스 뷰티 고관여층</PersonaInfo>
            </MessageInfo>
          </MessageItem>
        </SectionBox>

        {/* 오른쪽: 인기 페르소나 랭킹 */}
        <SectionBox>
          <SectionHeader>
            <SectionTitle><TrendingUp size={18}/> 인기 타겟 페르소나</SectionTitle>
          </SectionHeader>
          
          <RankItem>
            <RankNumber $top>1</RankNumber>
            <RankName>20대 수부지 대학생</RankName>
            <RankCount>42건</RankCount>
          </RankItem>
          <RankItem>
            <RankNumber $top>2</RankNumber>
            <RankName>30대 뷰티 고관여</RankName>
            <RankCount>35건</RankCount>
          </RankItem>
          <RankItem>
            <RankNumber>3</RankNumber>
            <RankName>40대 럭셔리 선호</RankName>
            <RankCount>18건</RankCount>
          </RankItem>
          <RankItem>
            <RankNumber>4</RankNumber>
            <RankName>트러블 케어 입문자</RankName>
            <RankCount>12건</RankCount>
          </RankItem>
          <RankItem>
            <RankNumber>5</RankNumber>
            <RankName>비건 뷰티 선호</RankName>
            <RankCount>9건</RankCount>
          </RankItem>
        </SectionBox>
      </BottomSection>
    </PageContainer>
  );
}