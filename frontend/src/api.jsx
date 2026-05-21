import axios from 'axios';

// 인증 전용 클라이언트 (port 8005, /auth/* — /api prefix 없음)
export const authApi = axios.create({
  baseURL: import.meta.env.VITE_AUTH_API_URL ?? 'http://localhost:8005',
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
});

// CRM Agent 서버 (port 8005) - /api/*
const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? 'http://localhost:8005/api',
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
});

// Token refresh queue — 동시 401 요청 시 refresh 한 번만 호출
let isRefreshing = false;
let refreshSubscribers = [];

function onRefreshed(error) {
  refreshSubscribers.forEach(cb => cb(error));
  refreshSubscribers = [];
}

// 401 응답 시 refresh 시도, 실패 시만 /login 리다이렉트
api.interceptors.response.use(
  res => res,
  async err => {
    const { config: originalRequest, response } = err;

    if (response?.status !== 401 || originalRequest._retry) {
      return Promise.reject(err);
    }

    originalRequest._retry = true;

    if (isRefreshing) {
      return new Promise((resolve, reject) => {
        refreshSubscribers.push(error => {
          if (error) reject(error);
          else resolve(api(originalRequest));
        });
      });
    }

    isRefreshing = true;

    try {
      await authApi.post('/auth/refresh');
      onRefreshed(null);
      return api(originalRequest);
    } catch (refreshErr) {
      onRefreshed(refreshErr);
      window.location.href = '/login';
      return Promise.reject(refreshErr);
    } finally {
      isRefreshing = false;
    }
  }
);

// DB/Pipeline 서버 (port 8020) - /api/personas/*, /api/generated-messages/*
export const dbApi = axios.create({
  baseURL: import.meta.env.VITE_DB_API_URL ?? 'http://localhost:8020/api',
  headers: { 'Content-Type': 'application/json' },
});

export const pipelineApi = dbApi;

export default api;
