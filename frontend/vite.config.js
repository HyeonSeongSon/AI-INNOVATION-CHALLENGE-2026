import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8005',
        changeOrigin: true,
        secure: false,
        configure: (proxy) => {
          proxy.on('proxyReq', (proxyReq, req) => {
            // SSE 엔드포인트: 압축 비활성화 → 청크 즉시 전달
            if (req.url?.includes('/stream')) {
              proxyReq.setHeader('Accept-Encoding', 'identity');
            }
          });
        },
      },
    },
  },
})
