/// <reference types="vitest/config" />
import { execSync } from 'node:child_process';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import type { Plugin } from 'vite';

function resolveAppVersion(): string {
  const explicitVersion = process.env.VITE_APP_VERSION?.trim();
  if (explicitVersion) return explicitVersion;

  try {
    return execSync('git rev-parse --short HEAD', { encoding: 'utf8' }).trim();
  } catch {
    return 'dev';
  }
}

function versionManifestPlugin(version: string): Plugin {
  const source = `${JSON.stringify({ version }, null, 2)}\n`;

  return {
    name: 'version-manifest',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const pathname = req.url?.split('?')[0];
        if (pathname !== '/version.json') {
          next();
          return;
        }

        res.statusCode = 200;
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(source);
      });
    },
    generateBundle() {
      this.emitFile({
        type: 'asset',
        fileName: 'version.json',
        source,
      });
    },
  };
}

const appVersion = resolveAppVersion();

export default defineConfig({
  plugins: [react(), versionManifestPlugin(appVersion)],
  define: {
    __APP_VERSION__: JSON.stringify(appVersion),
  },
  server: {
    port: 5174,
    host: '0.0.0.0',
    strictPort: true,
    cors: true,
    hmr: {
      clientPort: parseInt(process.env.PORT || '8008'),
    },
  },
  cacheDir: '/tmp/.vite-cache',
  test: {
    environment: 'jsdom',
    include: ['tests/**/*.{test,spec}.{ts,tsx}'],
  },
});
