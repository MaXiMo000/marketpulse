import '@fontsource/ibm-plex-sans/400.css'
import '@fontsource/ibm-plex-sans/500.css'
import '@fontsource/ibm-plex-sans/600.css'
import '@fontsource/orbitron/700.css'
import '@fontsource/orbitron/900.css'
import '@fontsource/rajdhani/600.css'
import '@fontsource/rajdhani/700.css'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'
import { AuthError } from './lib/auth'
import './index.css'

// An auth failure is not transient: retrying would only feed the server's lockout counter.
const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: (count, error) => !(error instanceof AuthError) && count < 2 } },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)
