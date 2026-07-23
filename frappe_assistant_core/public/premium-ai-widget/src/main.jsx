import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import ErrorBoundary from './components/ErrorBoundary'
import './index.css'

function init() {
  if (typeof frappe === 'undefined') {
    console.warn('[AI Widget] frappe not available — skipping render')
    return
  }
  if (frappe.session.user === 'Guest') {
    console.warn('[AI Widget] user is Guest — skipping render')
    return
  }

  // ── Protect Frappe's jQuery from being overwritten by our bundle ──
  const savedJQuery = window.jQuery
  const savedDollar = window.$

  const container = document.createElement('div')
  container.id = 'premium-ai-widget-root'
  document.body.appendChild(container)

  try {
    ReactDOM.createRoot(container).render(
      <React.StrictMode>
        <ErrorBoundary>
          <App />
        </ErrorBoundary>
      </React.StrictMode>
    )
  } catch (err) {
    console.error('[AI Widget] Failed to render root:', err)
  }

  // ── Restore Frappe's jQuery right after, in case anything clobbered it ──
  window.jQuery = savedJQuery
  window.$ = savedDollar
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init)
} else {
  init()
}