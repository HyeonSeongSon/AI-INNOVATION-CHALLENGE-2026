import React, { createContext, useState, useContext, useEffect, useCallback } from 'react';
import { dbApi as api } from '../api';

const ChatContext = createContext();

const USER_ID = 'son';

export const ChatProvider = ({ children }) => {
  // 대화 목록 (사이드바용)
  const [conversations, setConversations] = useState([]);

  // 대화 목록 로드
  const loadConversations = useCallback(async () => {
    try {
      const res = await api.get(`/conversations?user_id=${USER_ID}`);
      setConversations(res.data || []);
      return res.data || [];
    } catch (e) {
      console.error('대화 목록 로드 실패:', e);
      return [];
    }
  }, []);

  // 초기 대화 목록 로드
  useEffect(() => {
    loadConversations();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // DB에 메시지 + 제목 저장
  const saveMessages = useCallback(async (convId, msgs, title) => {
    if (!convId) return;
    try {
      await api.put(`/conversations/${convId}/messages`, {
        messages: msgs,
        title: title || undefined,
      });
      setConversations(prev =>
        prev.map(c => c.id === convId ? { ...c, title: title || c.title } : c)
      );
    } catch (e) {
      console.error('메시지 저장 실패:', e);
    }
  }, []);

  // 대화 삭제
  const deleteConversation = useCallback(async (convId) => {
    try {
      await api.delete(`/conversations/${convId}`);
      setConversations(prev => prev.filter(c => c.id !== convId));
    } catch (e) {
      console.error('대화 삭제 실패:', e);
    }
  }, []);

  return (
    <ChatContext.Provider value={{
      conversations,
      loadConversations,
      saveMessages,
      deleteConversation,
    }}>
      {children}
    </ChatContext.Provider>
  );
};

export const useChat = () => {
  const context = useContext(ChatContext);
  if (!context) {
    throw new Error('useChat must be used within a ChatProvider');
  }
  return context;
};
