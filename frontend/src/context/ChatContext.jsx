import React, { createContext, useState, useContext, useEffect, useCallback } from 'react';
import { dbApi } from '../api';

const ChatContext = createContext();

const USER_ID = 'son';

export const ChatProvider = ({ children }) => {
  // 대화 목록 (사이드바용)
  const [conversations, setConversations] = useState([]);

  // In-flight API 상태: Map<convId, { messages: [], isLoading: bool }>
  // 컴포넌트 언마운트/리마운트에 무관하게 상태 보존 (ChatGPT/Claude 방식)
  const [activeConvs, setActiveConvs] = useState(new Map());

  // 대화 목록 로드
  const loadConversations = useCallback(async () => {
    try {
      const res = await dbApi.get(`/conversations?user_id=${USER_ID}`);
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
      await dbApi.put(`/conversations/${convId}/messages`, {
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
      await dbApi.delete(`/conversations/${convId}`);
      setConversations(prev => prev.filter(c => c.id !== convId));
      // in-flight 상태도 정리
      setActiveConvs(prev => {
        const next = new Map(prev);
        next.delete(convId);
        return next;
      });
    } catch (e) {
      console.error('대화 삭제 실패:', e);
    }
  }, []);

  // API 시작 또는 진행 중 상태 등록/업데이트
  const setPendingConv = useCallback((convId, messages, isLoading = true) => {
    setActiveConvs(prev => new Map(prev).set(convId, { messages, isLoading }));
  }, []);

  // API 완료 후 정리 (컴포넌트가 final state를 반영한 뒤 호출)
  const clearPendingConv = useCallback((convId) => {
    setActiveConvs(prev => {
      const next = new Map(prev);
      next.delete(convId);
      return next;
    });
  }, []);

  return (
    <ChatContext.Provider value={{
      conversations,
      loadConversations,
      saveMessages,
      deleteConversation,
      activeConvs,
      setPendingConv,
      clearPendingConv,
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
