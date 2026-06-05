import React, { createContext, useState, useContext, useEffect, useCallback } from 'react';
import api from '../api';
import { useAuth } from './AuthContext';

const ChatContext = createContext();

export const ChatProvider = ({ children }) => {
  const { user } = useAuth();

  const [conversations, setConversations] = useState([]);
  const [activeConvs, setActiveConvs] = useState(new Map());

  const loadConversations = useCallback(async () => {
    try {
      const res = await api.get('/conversations');
      setConversations(res.data || []);
      return res.data || [];
    } catch (e) {
      console.error('대화 목록 로드 실패:', e);
      return [];
    }
  }, []);

  useEffect(() => {
    if (user) loadConversations();
  }, [user, loadConversations]);

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

  const deleteConversation = useCallback(async (convId) => {
    try {
      await api.delete(`/conversations/${convId}`);
      setConversations(prev => prev.filter(c => c.id !== convId));
      setActiveConvs(prev => {
        const next = new Map(prev);
        next.delete(convId);
        return next;
      });
    } catch (e) {
      console.error('대화 삭제 실패:', e);
    }
  }, []);

  const setPendingConv = useCallback((convId, messages, isLoading = true) => {
    setActiveConvs(prev => new Map(prev).set(convId, { messages, isLoading }));
  }, []);

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
  if (!context) throw new Error('useChat must be used within a ChatProvider');
  return context;
};
