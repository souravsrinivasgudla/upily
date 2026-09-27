import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { SendHorizontal } from 'lucide-react'
import { errorMessage, sendChat } from '../api'
import { useHealth } from '../useHealth'
import { Button, cn, Kicker, Notice } from './ui'

function Entry({ msg }) {
  const isReader = msg.role === 'user'
  return (
    <div className="grid grid-cols-[2.5rem_1fr] gap-3 border-b border-divider py-4 last:border-b-0">
      <span aria-hidden="true" className={cn('font-serif text-3xl font-black leading-none', msg.error && 'text-accent')}>
        {isReader ? 'Q.' : 'A.'}
      </span>
      <div>
        <Kicker className="block mb-1">{isReader ? 'The reader' : msg.error ? 'The press room' : 'The Upily desk'}</Kicker>
        <p className={cn(
          'whitespace-pre-wrap leading-relaxed',
          isReader ? 'font-serif text-lg font-semibold' : 'font-body text-[15px] text-neutral-700',
        )}>
          {msg.content}
        </p>

        {msg.related?.length > 0 && (
          <div className="mt-3 border-t border-ink pt-2">
            <Kicker className="block mb-1">Related coverage</Kicker>
            <ul className="space-y-1">
              {msg.related.map(r => (
                <li key={r.id}>
                  <Link to={`/article/${r.id}`} className="font-sans text-sm underline-offset-4 decoration-2 decoration-accent hover:underline">
                    → {r.title}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        )}

        {msg.sources?.length > 0 && (
          <Kicker className="mt-2 block">Sourced from: {msg.sources.join(', ')}</Kicker>
        )}
      </div>
    </div>
  )
}

const WELCOME = (articleId) => articleId
  ? 'Ask anything about this story — the context, the players, what happens next.'
  : 'Ask about the news. I check Upily’s recent coverage first, then search the web when needed.'

export default function ChatPanel({ articleId = null, suggestions = [] }) {
  const health = useHealth()
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const logRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    const el = logRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, loading])

  const disabled = health.loaded && !health.features.chat

  const send = async (text = input) => {
    const q = text.trim()
    if (!q || loading || disabled) return
    const history = messages.filter(m => !m.error).map(({ role, content }) => ({ role, content }))

    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: q }])
    setLoading(true)
    try {
      const data = await sendChat(q, { articleId, history })
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: data.answer,
        related: data.related_articles || [],
        sources: data.sources_used || [],
      }])
    } catch (err) {
      setMessages(prev => [...prev, { role: 'assistant', error: true, content: errorMessage(err, 'The desk could not answer that.') }])
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }

  const onKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }

  return (
    <div className="flex flex-col border border-ink bg-paper">
      <div ref={logRef} role="log" aria-live="polite" aria-label="Conversation"
           className="min-h-[280px] max-h-[60vh] overflow-y-auto px-4 sm:px-6">
        <div className="border-b border-divider py-4">
          <p className="font-body italic text-neutral-600">{WELCOME(articleId)}</p>
          {suggestions.length > 0 && messages.length === 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {suggestions.map(s => (
                <button key={s} type="button" onClick={() => send(s)} disabled={disabled}
                        className="min-h-[36px] border border-ink px-3 font-sans text-xs transition-colors duration-200 hover:bg-ink hover:text-paper disabled:opacity-40">
                  {s}
                </button>
              ))}
            </div>
          )}
        </div>

        {messages.map((m, i) => <Entry key={i} msg={m} />)}

        {loading && (
          <div className="grid grid-cols-[2.5rem_1fr] gap-3 py-4">
            <span aria-hidden="true" className="font-serif text-3xl font-black leading-none">A.</span>
            <Kicker className="animate-pulse">The desk is writing…</Kicker>
          </div>
        )}
      </div>

      {disabled && (
        <Notice tone="alert" className="m-4">The AI assistant is not configured on this server yet.</Notice>
      )}

      <form className="flex items-end gap-3 border-t border-ink p-4" onSubmit={(e) => { e.preventDefault(); send() }}>
        <label htmlFor={`chat-input-${articleId ?? 'desk'}`} className="sr-only">Your question</label>
        <textarea
          id={`chat-input-${articleId ?? 'desk'}`}
          ref={inputRef}
          rows={1}
          maxLength={1000}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={onKey}
          disabled={disabled}
          placeholder="Type your question…"
          className="min-h-[44px] flex-1 resize-none border-0 border-b-2 border-ink bg-transparent px-3 py-2.5 font-mono text-sm placeholder:text-neutral-500 focus-visible:bg-focus focus-visible:outline-none"
        />
        <Button type="submit" disabled={!input.trim() || loading || disabled} aria-label="Send question" className="px-4">
          <SendHorizontal className="h-4 w-4" strokeWidth={1.5} />
          <span className="hidden sm:inline">Ask</span>
        </Button>
      </form>
    </div>
  )
}
