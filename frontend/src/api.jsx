import axios from 'axios';

// 백엔드 주소 설정
const api = axios.create({
  // ✅ [수정] 포트 8010 -> 8005 (백엔드 포트)
  baseURL: 'http://localhost:8005/api',
  headers: {
    'Content-Type': 'application/json',
  },
});

// 데이터베이스/파이프라인 서버 (port 8020)
export const pipelineApi = axios.create({
  baseURL: 'http://localhost:8020/api',
  headers: {
    'Content-Type': 'application/json',
  },
});

export default api;