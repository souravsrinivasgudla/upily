import { Component } from 'react'
import { Button, Kicker } from './ui'

/** Stops one broken component from blanking the whole paper. */
export default class ErrorBoundary extends Component {
  state = { error: null }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    console.error('UI error:', error, info.componentStack)
  }

  componentDidUpdate(prev) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null })
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div role="alert" className="border-4 border-ink p-8 text-center">
        <Kicker accent className="block mb-3">Stop the presses</Kicker>
        <h2 className="font-serif text-3xl font-black">This page failed to print.</h2>
        <p className="mt-3 font-body text-neutral-600">Something went wrong while showing this section.</p>
        <Button className="mt-6" onClick={() => this.setState({ error: null })}>Try again</Button>
      </div>
    )
  }
}
