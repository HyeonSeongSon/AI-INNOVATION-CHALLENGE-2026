import React, { createContext, useState, useContext, useEffect } from 'react';

// Context 생성
const ChatContext = createContext();

// Provider 컴포넌트
export const ChatProvider = ({ children }) => {
  // 1. 초기 상태를 로컬 스토리지에서 불러옴
  const [messages, setMessages] = useState(() => {
    try {
      const savedMessages = localStorage.getItem('chat_history');
      return savedMessages ? JSON.parse(savedMessages) : [];
    } catch (e) {
      console.error("Failed to load chat history", e);
      return [];
    }
  });

  // 2. 메시지가 변경될 때마다 로컬 스토리지에 저장
  useEffect(() => {
    try {
      localStorage.setItem('chat_history', JSON.stringify(messages));
    } catch (e) {
      console.error("Failed to save chat history", e);
    }
  }, [messages]);

  // 메시지 추가 함수
  const addMessage = (message) => {
    setMessages((prev) => [...prev, message]);
  };

  // 대화 초기화 함수
  const clearChat = () => {
    setMessages([]);
    localStorage.removeItem('chat_history');
  };

  return (
    <ChatContext.Provider value={{ messages, setMessages, addMessage, clearChat }}>
      {children}
    </ChatContext.Provider>
  );
};

// Custom Hook (컴포넌트에서 쉽게 쓰기 위함)
export const useChat = () => {
  const context = useContext(ChatContext);
  if (!context) {
    throw new Error('useChat must be used within a ChatProvider');
  }
  return context;
};