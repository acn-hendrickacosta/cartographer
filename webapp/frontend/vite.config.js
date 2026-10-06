import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Output is served by FastAPI: index.html at any non-API path (the SPA
// catch-all in ../backend/app/main.py), JS/CSS under /assets (see that same
// file's StaticFiles mount). `base` must match so built asset URLs resolve.
export default defineConfig({
  plugins: [react()],
  // Vite's default build.assetsDir ("assets") already nests built JS/CSS/font
  // files one level under outDir -- base must stay "/" so the built
  // references are "/assets/<file>", matching the backend's StaticFiles
  // mount at /assets -> dist/assets (not "/assets/assets/<file>").
  base: '/',
  build: {
    outDir: '../backend/app/static/dist',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      // During `npm run dev`, forward API calls to the real backend (run
      // separately: cd ../backend && uvicorn app.main:app --reload) so the
      // same session cookie / auth flow works without a production build.
      '/api': 'http://127.0.0.1:8000',
      '/login': 'http://127.0.0.1:8000',
      '/auth': 'http://127.0.0.1:8000',
      '/logout': 'http://127.0.0.1:8000',
    },
  },
});
