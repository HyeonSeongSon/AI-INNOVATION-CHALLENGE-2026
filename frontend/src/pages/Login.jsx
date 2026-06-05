import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import styled from 'styled-components';
import { User, Lock } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

const Container = styled.div`
  display: flex;
  justify-content: center;
  align-items: center;
  width: 100vw;
  height: 100vh;
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
  padding: 12px 12px 12px 40px;
  border: 1px solid ${({ $hasError }) => ($hasError ? '#FF5252' : '#E0E0E0')};
  border-radius: 8px;
  font-size: 14px;
  outline: none;
  transition: border-color 0.2s;

  &:focus {
    border-color: ${({ $hasError }) => ($hasError ? '#FF5252' : '#7C4DFF')};
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

const ErrorMessage = styled.p`
  font-size: 13px;
  color: #FF5252;
  text-align: left;
  margin-top: -12px;
`;

const LoginButton = styled.button`
  width: 100%;
  padding: 14px;
  margin-top: 10px;
  background-color: ${({ disabled }) => (disabled ? '#B0BEC5' : '#7C4DFF')};
  color: white;
  font-size: 16px;
  font-weight: bold;
  border: none;
  border-radius: 8px;
  cursor: ${({ disabled }) => (disabled ? 'not-allowed' : 'pointer')};
  transition: background-color 0.2s;

  &:hover:not(:disabled) {
    background-color: #651FFF;
  }
`;

export default function Login() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [id, setId] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleLogin = async () => {
    if (!id || !password) {
      setError('이메일과 비밀번호를 입력해주세요.');
      return;
    }
    setError('');
    setIsLoading(true);
    try {
      await login(id, password);
      navigate('/');
    } catch {
      setError('이메일 또는 비밀번호가 올바르지 않습니다.');
    } finally {
      setIsLoading(false);
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
            placeholder="이메일"
            value={id}
            $hasError={!!error}
            onChange={(e) => { setId(e.target.value); setError(''); }}
          />
        </InputWrapper>

        <InputWrapper>
          <IconWrapper><Lock /></IconWrapper>
          <Input
            type="password"
            placeholder="비밀번호"
            value={password}
            $hasError={!!error}
            onChange={(e) => { setPassword(e.target.value); setError(''); }}
            onKeyDown={(e) => e.key === 'Enter' && handleLogin()}
          />
        </InputWrapper>

        {error && <ErrorMessage>{error}</ErrorMessage>}

        <LoginButton onClick={handleLogin} disabled={isLoading}>
          {isLoading ? '로그인 중...' : 'LOGIN'}
        </LoginButton>
      </LoginBox>
    </Container>
  );
}
