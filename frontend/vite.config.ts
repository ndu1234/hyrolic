import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    port: 5173,
    proxy: {
      // Frontend talks to the FastAPI backend through Vite's dev proxy
      '/api': 'http://localhost:8080',
      '/ifc': 'http://localhost:8080',
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
});