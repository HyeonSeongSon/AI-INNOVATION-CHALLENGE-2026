import axios from 'axios';

// CRM Agent 서버 (port 8005) - /api/marketing/*
const api = axios.create({
  baseURL: 'http://localhost:8005/api',
  headers: {
    'Content-Type': 'application/json',
  },
});

// DB/Pipeline 서버 (port 8020) - /api/personas/*, /api/pipeline/*, /api/conversations/*, /api/generated-messages
export const dbApi = axios.create({
  baseURL: 'http://localhost:8020/api',
  headers: {
    'Content-Type': 'application/json',
  },
});

export const pipelineApi = dbApi;

export default api;