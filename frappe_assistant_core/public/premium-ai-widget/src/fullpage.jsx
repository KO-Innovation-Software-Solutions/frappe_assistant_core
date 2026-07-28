import React from 'react'
import ReactDOM from 'react-dom/client'
import AikoFullPage from './components/AikoFullPage'
import ErrorBoundary from './components/ErrorBoundary'
import cssText from './index.css?inline'

window.AikoChatPage = {
  init(hostContainer) {
    if (typeof frappe === 'undefined') {
      console.warn('[AIKO Fullpage] frappe not available')
      return
    }

    hostContainer.style.width = '100%'
    hostContainer.style.height = '100vh'
    hostContainer.style.overflow = 'hidden'

    const shadow = hostContainer.attachShadow({ mode: 'open' })

    const style = document.createElement('style')
    style.textContent = cssText
    shadow.appendChild(style)

    const appRoot = document.createElement('div')
    appRoot.id = 'premium-ai-widget-root'
    appRoot.style.width = '100%'
    appRoot.style.height = '100%'
    shadow.appendChild(appRoot)

    try {
      ReactDOM.createRoot(appRoot).render(
        <React.StrictMode>
          <ErrorBoundary>
            <AikoFullPage />
          </ErrorBoundary>
        </React.StrictMode>
      )
    } catch (err) {
      console.error('[AIKO Fullpage] Failed to render:', err)
    }
  }
}
