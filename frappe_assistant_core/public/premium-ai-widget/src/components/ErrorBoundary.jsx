import { Component } from 'react'

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, info) {
    console.error('[AI Widget] Error boundary caught:', error, info)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="fixed bottom-6 right-6 z-50 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-700 shadow-lg dark:border-red-800 dark:bg-red-900/30 dark:text-red-300">
          <p className="font-semibold">Widget failed to load</p>
          <p className="mt-1 text-xs opacity-80">Check console for details.</p>
          <button
            onClick={() => { this.setState({ hasError: false, error: null }) }}
            className="mt-2 rounded-lg bg-red-600 px-3 py-1 text-xs font-medium text-white hover:bg-red-700"
          >
            Retry
          </button>
        </div>
      )
    }

    return this.props.children
  }
}
