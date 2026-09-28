import { defineConfig } from 'vite';

// Output is served by FastAPI: index.html at GET "/", everything else mounted
// under StaticFiles at "/static" (see cartographer/ui/server.py). `base` must
// match that mount point so built asset URLs resolve correctly.
export default defineConfig({
  base: '/static/',
  build: {
    outDir: '../src/cartographer/ui/static',
    emptyOutDir: true,
  },
});
