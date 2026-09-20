import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests', fullyParallel: false, expect: { timeout: 15000 },
  use: { baseURL: 'http://127.0.0.1:5174', headless: true, screenshot: 'only-on-failure' },
  webServer: [
    { env: { PYTHONPATH: '../backend' }, command: process.platform === 'win32' ? '..\\.venv\\Scripts\\python.exe -m uvicorn browser_app:app --app-dir ../backend/tests --host 127.0.0.1 --port 8010' : '../.venv/bin/python -m uvicorn browser_app:app --app-dir ../backend/tests --host 127.0.0.1 --port 8010',
      url: 'http://127.0.0.1:8010/health', reuseExistingServer: false, timeout: 30000 },
    { env: { VITE_API_TARGET: 'http://127.0.0.1:8010' }, command: 'npm run dev -- --port 5174 --strictPort', url: 'http://127.0.0.1:5174', reuseExistingServer: false, timeout: 30000 },
  ],
});
