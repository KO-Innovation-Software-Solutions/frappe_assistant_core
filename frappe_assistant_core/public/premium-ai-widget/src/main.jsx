import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import ErrorBoundary from './components/ErrorBoundary'
import cssText from './index.css?inline'

function mountWidget() {
  const host = document.createElement('div')
  host.id = 'premium-ai-widget-host'
  host.style.position = 'fixed'
  host.style.top = '0'
  host.style.left = '0'
  host.style.width = '0'
  host.style.height = '0'
  host.style.zIndex = '2147483647'
  document.body.appendChild(host)

  const shadow = host.attachShadow({ mode: 'open' })

  const style = document.createElement('style')
  style.textContent = cssText
  shadow.appendChild(style)

  const appRoot = document.createElement('div')
  appRoot.id = 'premium-ai-widget-root'
  shadow.appendChild(appRoot)

  try {
    ReactDOM.createRoot(appRoot).render(
      <React.StrictMode>
        <ErrorBoundary>
          <App />
        </ErrorBoundary>
      </React.StrictMode>
    )
  } catch (err) {
    console.error('[AI Widget] Failed to render root:', err)
  }
}

function init() {
  if (typeof frappe === 'undefined') return
  if (frappe.session.user === 'Guest') return
  if (window.location.pathname.includes('/aiko_chat')) return

  setTimeout(mountWidget, 50)
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init)
} else {
  init()
}