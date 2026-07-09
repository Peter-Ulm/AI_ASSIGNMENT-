
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 3000,
    // Docker Desktop's bind mount doesn't reliably forward inotify events on
    // Windows/macOS hosts, so chokidar's default watcher misses file saves.
    // Polling trades a bit of CPU for actually picking up changes.
    watch: {
      usePolling: true,
      interval: 300
    }
  },
  optimizeDeps: {
    exclude: ['bootstrap-icons']
  },
  build: {
    outDir: 'dist',
    sourcemap: true
  }
})
