import { useState, useRef, useEffect } from 'react'
import { Bot, User, SendHorizontal, Loader2 } from 'lucide-react'
import { sendChat } from '../api'

function Bubble({ msg }) {
  const isUser = msg.role === 'user'
  return (
    <div className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      <div className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0
        ${isUser ? 'bg-brand-600' : 'bg-gray-700'}`}>
        {isUser
          ? <User className="w-3.5 h-3.5 text-white" />
          : <Bot  className="w-3.5 h-3.5 text-gray-300" />}
      </div>

      <div className={`max-w-[80%] rounded-xl px-4 py-3 text-sm leading-relaxed
        ${isUser
          ? 'bg-brand-600 text-white rounded-tr-none'
          : 'bg-gray-800 text-gray-200 rounded-tl-none'}`}>
        <p className="whitespace-pre-wrap">{msg.content}</p>

        {msg.related?.length > 0 && (
          <div className="mt-3 pt-2 border-t border-gray-700 space-y-1">
            <p className="text-xs text-gray-400 font-medium">Related articles:</p>
            {msg.related.map(r => (
              <a
                key={r.id}
                href={`/article/${r.id}`}
                className="block text-xs text-brand-400 hover:text-brand-300 truncate"
              >
                → {r.title}
              </a>
            ))}
          </div>
        )}

        {msg.sources && (
          <p className="mt-2 text-xs text-gray-500 italic">
            Sources: {msg.sources}
          </p>
        )}
      </div>
    </div>
  )
}

const WELCOME = (articleId) => articleId
  ? '💡 Ask me anything about this article — I can explain context, implications, and background.'
  : "🧠 Ask me anything about recent news or current events. I'll search my knowledge base and the web if needed."

export default function ChatPanel({ articleId = null, articleData = null }) {
  const [messages, setMessages] = useState([
    { role: 'assistant', content: WELCOME(articleId) },
  ])
  const [input,   setInput]   = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const send = async () => {
    const q = input.trim()
    if (!q || loading) return

    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: q }])
    setLoading(true)

    try {
      const data = await sendChat(q, articleId, articleData)
      setMessages(prev => [...prev, {
        role:    'assistant',
        content: data.answer || 'No answer returned.',
        related: data.related_articles || [],
        sources: data.sources_used,
      }])
    } catch {
      setMessages(prev => [...prev, {
        role:    'assistant',
        content: '⚠️ Could not reach the backend. Make sure the server is running.',
      }])
    } finally {
      setLoading(false)
    }
  }

  const onKey = e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }

  return (
    <div className="flex flex-col bg-gray-950" style={{ height: 520 }}>
      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((m, i) => <Bubble key={i} msg={m} />)}

        {loading && (
          <div className="flex gap-3">
            <div className="w-7 h-7 rounded-full bg-gray-700 flex items-center justify-center">
              <Bot className="w-3.5 h-3.5 text-gray-300" />
            </div>
            <div className="bg-gray-800 rounded-xl rounded-tl-none px-4 py-3 flex items-center gap-2">
              <Loader2 className="w-4 h-4 animate-spin text-brand-400" />
              <span className="text-xs text-gray-400">Thinking…</span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div className="border-t border-gray-800 p-3 flex gap-2">
        <textarea
          rows={1}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={onKey}
          placeholder="Ask a question…"
          className="flex-1 resize-none bg-gray-800 text-white placeholder-gray-500 text-sm
                     rounded-lg px-4 py-2.5 outline-none focus:ring-1 focus:ring-brand-500"
        />
        <button
          onClick={send}
          disabled={!input.trim() || loading}
          className="bg-brand-600 hover:bg-brand-700 disabled:opacity-40 text-white
                     rounded-lg px-4 py-2.5 transition-colors shrink-0"
        >
          <SendHorizontal className="w-4 h-4" />
        </button>
      </div>
    </div>
  )
}
