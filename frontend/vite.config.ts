import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // the 3D scene (three.js) is a deliberately lazy chunk, loaded only when the skyline renders
  build: { chunkSizeWarningLimit: 1000 },
})
