import React, { useState, useEffect, createContext, useContext } from 'react';
import styled, { keyframes, css } from 'styled-components';
import { CheckCircle, AlertCircle, X, Info } from 'lucide-react';

/* --- 스타일 & 애니메이션 --- */
const slideIn = keyframes`
  from { transform: translateX(100%); opacity: 0; }
  to { transform: translateX(0); opacity: 1; }
`;

const ToastContainer = styled.div`
  position: fixed;
  top: 20px;
  right: 20px;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  gap: 10px;
`;

const ToastItem = styled.div`
  min-width: 300px;
  background: white;
  padding: 16px 20px;
  border-radius: 12px;
  box-shadow: 0 10px 30px rgba(0,0,0,0.08);
  border-left: 5px solid ${props => props.$color};
  display: flex;
  align-items: center;
  gap: 12px;
  animation: ${slideIn} 0.3s ease-out forwards;
  position: relative;
  overflow: hidden;

  ${props => props.$isClosing && css`
    opacity: 0;
    transform: translateX(100%);
    transition: all 0.3s ease-in;
  `}
`;

const Message = styled.div`
  flex: 1;
  font-size: 14px;
  font-weight: 500;
  color: #333;
  line-height: 1.4;
`;

const CloseBtn = styled.button`
  background: none; border: none; padding: 0; color: #999;
  cursor: pointer; &:hover { color: #333; }
`;

/* --- Context 로직 --- */
const ToastContext = createContext();

export const useToast = () => useContext(ToastContext);

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  // 토스트 추가 함수
  const addToast = (message, type = 'success') => {
    const id = Date.now();
    setToasts(prev => [...prev, { id, message, type }]);
    
    // 3초 후 자동 삭제
    setTimeout(() => removeToast(id), 3000);
  };

  const removeToast = (id) => {
    setToasts(prev => prev.map(t => t.id === id ? { ...t, isClosing: true } : t));
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 300);
  };

  const styles = {
    success: { color: '#00C853', icon: <CheckCircle size={20}/> },
    error: { color: '#FF3D00', icon: <AlertCircle size={20}/> },
    info: { color: '#2979FF', icon: <Info size={20}/> }
  };

  return (
    <ToastContext.Provider value={{ addToast }}>
      {children}
      <ToastContainer>
        {toasts.map(t => {
          const style = styles[t.type] || styles.success;
          return (
            <ToastItem key={t.id} $color={style.color} $isClosing={t.isClosing}>
              <div style={{color: style.color}}>{style.icon}</div>
              <Message>{t.message}</Message>
              <CloseBtn onClick={() => removeToast(t.id)}><X size={16}/></CloseBtn>
            </ToastItem>
          )
        })}
      </ToastContainer>
    </ToastContext.Provider>
  );
}