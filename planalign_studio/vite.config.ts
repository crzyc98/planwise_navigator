import { fileURLToPath, URL } from 'node:url';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig(({ mode }) => {
    const env = loadEnv(mode, '.', '');
    const bindHost = env.PLANALIGN_API_HOST || '127.0.0.1';
    const apiPort = env.PLANALIGN_API_PORT || '8000';
    const proxyHost = bindHost === '0.0.0.0'
      ? '127.0.0.1'
      : bindHost === '::' || bindHost === '[::]'
        ? '[::1]'
        : bindHost.startsWith('[') || !bindHost.includes(':')
          ? bindHost
          : `[${bindHost}]`;
    const allowedHosts = (env.PLANALIGN_STUDIO_ALLOWED_HOSTS || 'localhost,127.0.0.1,::1')
      .split(',')
      .map((host) => host.trim())
      .filter(Boolean);
    return {
      server: {
        port: 3000,
        host: bindHost,
        allowedHosts,
        proxy: {
          '/api': `http://${proxyHost}:${apiPort}`,
          '/ws': { target: `ws://${proxyHost}:${apiPort}`, ws: true },
        },
      },
      plugins: [tailwindcss(), react()],
      define: {
        'process.env.API_KEY': JSON.stringify(env.GEMINI_API_KEY),
        'process.env.GEMINI_API_KEY': JSON.stringify(env.GEMINI_API_KEY)
      },
      resolve: {
        alias: {
          '@': fileURLToPath(new URL('.', import.meta.url)),
        }
      }
    };
});
