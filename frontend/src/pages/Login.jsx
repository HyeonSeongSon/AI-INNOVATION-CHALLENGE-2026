import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import styled from 'styled-components';
import { User, Lock } from 'lucide-react';

const Container = styled.div`
  display: flex;
  justify-content: center; /* 여기가 _ 가 아니라 - 이어야 합니다! */
  align-items: center;
  width: 100vw;            /* 가로를 화면 꽉 차게 설정 */
  height: 100vh;           /* 세로를 화면 꽉 차게 설정 */
  background-color: #F5F6FA;
`;

const LoginBox = styled.div`
  background: white;
  width: 400px;
  padding: 60px 40px;
  border-radius: 16px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05);
  text-align: center;
  display: flex;
  flex-direction: column;
  gap: 20px;
`;

const Title = styled.h1`
  font-size: 24px;
  font-weight: bold;
  color: #333;
  margin-bottom: 8px;
`;

const SubTitle = styled.p`
  font-size: 14px;
  color: #888;
  margin-bottom: 30px;
`;

const InputWrapper = styled.div`
  position: relative;
  width: 100%;
`;

const Input = styled.input`
  width: 100%;
  padding: 12px 12px 12px 40px; /* 아이콘 공간 확보 */
  border: 1px solid #E0E0E0;
  border-radius: 8px;
  font-size: 14px;
  outline: none;
  transition: border-color 0.2s;

  &:focus {
    border-color: #7C4DFF; /* 포커스 시 보라색 */
  }

  &::placeholder {
    color: #AAA;
  }
`;

const IconWrapper = styled.div`
  position: absolute;
  left: 12px;
  top: 50%;
  transform: translateY(-50%);
  color: #AAA;
  display: flex;
  align-items: center;
  
  svg {
    width: 18px;
    height: 18px;
  }
`;

const LoginButton = styled.button`
  width: 100%;
  padding: 14px;
  margin-top: 10px;
  background-color: #7C4DFF; /* 이미지의 보라색 버튼 */
  color: white;
  font-size: 16px;
  font-weight: bold;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: background-color 0.2s;

  &:hover {
    background-color: #651FFF;
  }
`;

export default function Login() {
  const navigate = useNavigate(); // 페이지 이동을 도와주는 훅
  const [id, setId] = useState('');
  const [password, setPassword] = useState('');

  const handleLogin = () => {
    // 지금은 무조건 홈으로 이동 (나중에 실제 로그인 로직 추가 가능)
    if (id && password) {
      navigate('/'); 
    } else {
      alert('아이디와 비밀번호를 입력해주세요.');
    }
  };

  return (
    <Container>
      <LoginBox>
        <div>
          <Title>로그인</Title>
          <SubTitle>계정에 로그인하세요</SubTitle>
        </div>

        <InputWrapper>
          <IconWrapper><User /></IconWrapper>
          <Input 
            type="text" 
            placeholder="ID" 
            value={id}
            onChange={(e) => setId(e.target.value)}
          />
        </InputWrapper>

        <InputWrapper>
          <IconWrapper><Lock /></IconWrapper>
          <Input 
            type="password" 
            placeholder="password" 
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleLogin()} 
          />
        </InputWrapper>

        <LoginButton onClick={handleLogin}>
          LOGIN
        </LoginButton>
      </LoginBox>
    </Container>
  );
}