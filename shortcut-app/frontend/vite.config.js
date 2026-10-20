import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
        configure(proxy) {
          proxy.on('proxyReq', (proxyReq, req, res) => {
            // 브라우저가 EventSource를 닫아도 GET 요청은 이미 끝난 상태라 프록시가 상류 연결을 남겨 두므로 직접 끊는다.
            res.on('close', () => {
              if (!res.writableEnded) proxyReq.destroy()
            })
          })
        }
      }
    }
  }
})
