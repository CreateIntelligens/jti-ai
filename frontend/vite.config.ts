import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    host: '0.0.0.0',
    strictPort: true,
    cors: true, // 啟用 CORS
    hmr: {
      clientPort: 8913, // HMR 透過 nginx port
    },
    proxy: {
      '/api': {
        target: 'http://localhost:5000',
        changeOrigin: true,
      },
    },
  },
  cacheDir: '/tmp/.vite-cache',
});
