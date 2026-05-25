import axios from 'axios';

// 인증 전용 클라이언트 (port 8005, /auth/* — /api prefix 없음)
export const authApi = axios.create({
  baseURL: import.meta.env.VITE_AUTH_API_URL ?? 'http://localhost:8005',
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
});

// authApi 401 인터셉터: access token 만료 시 refresh 후 재시도
// /auth/refresh, /auth/login은 skip — 무한루프 및 로그인 실패 오진단 방지
authApi.interceptors.response.use(
  res => res,
  async err => {
    const { config: originalRequest, response } = err;

    const url = originalRequest?.url ?? '';
    const isAuthMutation =
      url.includes('/auth/refresh') || url.includes('/auth/login');

    if (response?.status !== 401 || originalRequest._retry || isAuthMutation) {
      return Promise.reject(err);
    }

    originalRequest._retry = true;

    if (isRefreshing) {
      return new Promise((resolve, reject) => {
        refreshSubscribers.push(error => {
          if (error) reject(error);
          else resolve(authApi(originalRequest));
        });
      });
    }

    isRefreshing = true;

    try {
      await authApi.post('/auth/refresh', null, { timeout: 10_000 });
      onRefreshed(null);
      return authApi(originalRequest);
    } catch (refreshErr) {
      onRefreshed(refreshErr);
      return Promise.reject(refreshErr);
    } finally {
      isRefreshing = false;
    }
  }
);

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
      await authApi.post('/auth/refresh', null, { timeout: 10_000 });
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

// CRM 서비스 클라이언트 (port 8006) — LangGraph 에이전트 + Pipeline SSE
export const crmApi = axios.create({
  baseURL: `${import.meta.env.VITE_CRM_API_URL ?? 'http://localhost:8006'}/api`,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
});

crmApi.interceptors.response.use(
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
          else resolve(crmApi(originalRequest));
        });
      });
    }

    isRefreshing = true;

    try {
      await authApi.post('/auth/refresh', null, { timeout: 10_000 });
      onRefreshed(null);
      return crmApi(originalRequest);
    } catch (refreshErr) {
      onRefreshed(refreshErr);
      window.location.href = '/login';
      return Promise.reject(refreshErr);
    } finally {
      isRefreshing = false;
    }
  }
);

// pipelineApi — backend:8005 BFF 프록시를 통해 DB 데이터에 접근 (인증 포함)
export const pipelineApi = api;

export default api;
