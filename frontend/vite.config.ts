import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv, type Plugin } from 'vite'

// Production builds get a Content-Security-Policy meta tag that only allows this app's own files
// and the configured API origin. (frame-ancestors cannot be set from a meta tag; set it on the host.)
function contentSecurityPolicy(apiUrl: string): Plugin {
  const policy = [
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self'",
    "style-src-attr 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self'",
    `connect-src 'self' ${new URL(apiUrl).origin}`,
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
  ].join('; ')
  return {
    name: 'content-security-policy',
    apply: 'build',
    transformIndexHtml: (html) =>
      html.replace('<head>', `<head>\n    <meta http-equiv="Content-Security-Policy" content="${policy}">`),
  }
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [react(), contentSecurityPolicy(env.VITE_API_URL || 'http://localhost:8000')],
    // the 3D scene (three.js) is a deliberately lazy chunk, loaded only when the skyline renders
    build: { chunkSizeWarningLimit: 1000 },
  }
})
