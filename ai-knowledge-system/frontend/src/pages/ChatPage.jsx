import { MessageSquare } from 'lucide-react'
import ChatPanel from '../components/ChatPanel'

export default function ChatPage() {
  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        <MessageSquare className="w-6 h-6 text-brand-500" />
        <h1 className="text-2xl font-bold text-white">Ask AI</h1>
      </div>

      <p className="text-gray-400 text-sm mb-6">
        Chat with the AI about any news topic. It searches your stored articles first,
        then queries the web if needed.
      </p>

      <div className="rounded-xl border border-gray-800 overflow-hidden">
        <ChatPanel />
      </div>
    </div>
  )
}
