import React, { useState } from 'react';
import styled from 'styled-components';
import { Plus, X, User, Tag, Heart, DollarSign, Trash2 } from 'lucide-react';

/* --- 스타일 컴포넌트 --- */
const Container = styled.div`
  max-width: 1200px;
  margin: 0 auto;
`;

const Header = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 30px;
`;

const Title = styled.h1`
  font-size: 24px;
  font-weight: 800;
  color: #333;
`;

const AddButton = styled.button`
  display: flex;
  align-items: center;
  gap: 8px;
  background-color: #6B4DFF;
  color: white;
  padding: 12px 20px;
  border-radius: 8px;
  border: none;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.2s;

  &:hover {
    background-color: #5a3de0;
  }
`;

/* 카드 리스트 영역 */
const Grid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); /* 반응형 그리드 */
  gap: 24px;
`;

const PersonaCard = styled.div`
  background: white;
  border-radius: 16px;
  padding: 24px;
  border: 1px solid #eee;
  box-shadow: 0 4px 12px rgba(0,0,0,0.03);
  transition: transform 0.2s, box-shadow 0.2s;
  position: relative;

  &:hover {
    transform: translateY(-4px);
    box-shadow: 0 8px 20px rgba(0,0,0,0.08);
  }
`;

const CardHeader = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  border-bottom: 1px solid #f0f0f0;
  padding-bottom: 16px;
`;

const Avatar = styled.div`
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background-color: #F0EBFF;
  color: #6B4DFF;
  display: flex;
  align-items: center;
  justify-content: center;
`;

const NameInfo = styled.div`
  display: flex;
  flex-direction: column;
`;

const Name = styled.span`
  font-size: 18px;
  font-weight: 700;
  color: #333;
`;

const Job = styled.span`
  font-size: 14px;
  color: #888;
`;

const InfoList = styled.div`
  display: flex;
  flex-direction: column;
  gap: 10px;
`;

const InfoItem = styled.div`
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
  color: #555;

  svg {
    color: #bbb;
    width: 16px;
    height: 16px;
  }
`;

const DeleteBtn = styled.button`
  position: absolute;
  top: 20px;
  right: 20px;
  background: none;
  border: none;
  color: #ddd;
  cursor: pointer;
  &:hover { color: #ff4d4d; }
`;

/* --- 모달(팝업) 스타일 --- */
const ModalOverlay = styled.div`
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
`;

const ModalBox = styled.div`
  background: white;
  width: 500px;
  max-height: 90vh;
  overflow-y: auto;
  border-radius: 16px;
  padding: 30px;
  box-shadow: 0 10px 40px rgba(0,0,0,0.2);
`;

const ModalHeader = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  h2 { font-size: 20px; font-weight: bold; }
  svg { cursor: pointer; color: #888; }
`;

const FormGroup = styled.div`
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;

  label {
    font-size: 14px;
    font-weight: 600;
    color: #333;
  }

  input, textarea, select {
    padding: 12px;
    border: 1px solid #ddd;
    border-radius: 8px;
    font-size: 14px;
    outline: none;
    &:focus { border-color: #6B4DFF; }
  }
  
  textarea { resize: vertical; min-height: 80px; }
`;

const SaveButton = styled.button`
  width: 100%;
  padding: 14px;
  background-color: #6B4DFF;
  color: white;
  font-weight: bold;
  border-radius: 8px;
  border: none;
  cursor: pointer;
  margin-top: 10px;
  &:hover { background-color: #5a3de0; }
`;

export default function Persona() {
  const [isModalOpen, setIsModalOpen] = useState(false);
  
  // 초기 페르소나 데이터 (예시)
  const [personas, setPersonas] = useState([
    { id: 1, name: '김민지', age: '24세', job: '대학생', skin: '수부지(수분부족 지성)', interest: '가성비, 비건 뷰티', price: '중저가 선호' },
    { id: 2, name: '박서준', age: '35세', job: '직장인', skin: '건성, 민감성', interest: '안티에이징, 기능성', price: '고가 브랜드 선호' },
  ]);

  // 입력 폼 상태 관리
  const [formData, setFormData] = useState({
    name: '', age: '', job: '', skin: '', interest: '', price: ''
  });

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData({ ...formData, [name]: value });
  };

  const handleAddPersona = () => {
    if (!formData.name) return alert('이름을 입력해주세요');
    
    const newPersona = {
      id: Date.now(), // 고유 ID 생성
      ...formData
    };

    setPersonas([...personas, newPersona]);
    setFormData({ name: '', age: '', job: '', skin: '', interest: '', price: '' }); // 폼 초기화
    setIsModalOpen(false); // 모달 닫기
  };

  const handleDelete = (id) => {
    if(window.confirm('정말 삭제하시겠습니까?')) {
      setPersonas(personas.filter(p => p.id !== id));
    }
  };

  return (
    <Container>
      <Header>
        <div>
          <Title>페르소나 관리</Title>
          <p style={{color: '#666', marginTop: '8px', fontSize: '14px'}}>
            마케팅 타겟이 될 가상 고객의 프로필을 정의합니다.
          </p>
        </div>
        <AddButton onClick={() => setIsModalOpen(true)}>
          <Plus size={18} /> 페르소나 추가
        </AddButton>
      </Header>

      <Grid>
        {personas.map((persona) => (
          <PersonaCard key={persona.id}>
            <DeleteBtn onClick={() => handleDelete(persona.id)}><Trash2 size={16}/></DeleteBtn>
            <CardHeader>
              <Avatar><User size={24} /></Avatar>
              <NameInfo>
                <Name>{persona.name}</Name>
                <Job>{persona.age} / {persona.job}</Job>
              </NameInfo>
            </CardHeader>
            <InfoList>
              <InfoItem><Heart /> 피부타입: {persona.skin}</InfoItem>
              <InfoItem><Tag /> 관심사: {persona.interest}</InfoItem>
              <InfoItem><DollarSign /> 가격민감도: {persona.price}</InfoItem>
            </InfoList>
          </PersonaCard>
        ))}
      </Grid>

      {/* 모달 창 */}
      {isModalOpen && (
        <ModalOverlay onClick={() => setIsModalOpen(false)}>
          <ModalBox onClick={(e) => e.stopPropagation()}>
            <ModalHeader>
              <h2>새 페르소나 생성</h2>
              <X onClick={() => setIsModalOpen(false)} />
            </ModalHeader>

            <FormGroup>
              <label>이름 (가명)</label>
              <input name="name" placeholder="예: 김아모" value={formData.name} onChange={handleInputChange} />
            </FormGroup>

            <div style={{display: 'flex', gap: '10px'}}>
              <FormGroup style={{flex: 1}}>
                <label>나이</label>
                <input name="age" placeholder="예: 28세" value={formData.age} onChange={handleInputChange} />
              </FormGroup>
              <FormGroup style={{flex: 1}}>
                <label>직업</label>
                <input name="job" placeholder="예: 마케터" value={formData.job} onChange={handleInputChange} />
              </FormGroup>
            </div>

            <FormGroup>
              <label>피부 고민/타입</label>
              <input name="skin" placeholder="예: 환절기 건조함, 붉은기" value={formData.skin} onChange={handleInputChange} />
            </FormGroup>

            <FormGroup>
              <label>쇼핑 패턴 및 선호</label>
              <textarea name="interest" placeholder="예: 올리브영 세일 기간 구매, 성분 분석 앱 사용 등" value={formData.interest} onChange={handleInputChange} />
            </FormGroup>

            <FormGroup>
              <label>가격 민감도</label>
              <select name="price" value={formData.price} onChange={handleInputChange}>
                <option value="">선택해주세요</option>
                <option value="가성비 중시">가성비 중시 (저가~중가)</option>
                <option value="가치소비 중시">가치소비 중시 (중가~고가)</option>
                <option value="프리미엄 선호">프리미엄 선호 (고가)</option>
              </select>
            </FormGroup>

            <SaveButton onClick={handleAddPersona}>저장하기</SaveButton>
          </ModalBox>
        </ModalOverlay>
      )}
    </Container>
  );
}