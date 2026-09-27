import ChatPanel from '../components/ChatPanel'
import { Kicker } from '../components/ui'

const SUGGESTIONS = [
  'What are the biggest stories today?',
  'Explain the latest in AI regulation',
  'What is moving the markets?',
]

export default function ChatPage() {
  return (
    <div className="grid grid-cols-1 gap-8 lg:grid-cols-12">
      <header className="lg:col-span-4 lg:border-r lg:border-ink lg:pr-8">
        <Kicker accent className="block mb-3">Letters to the editor</Kicker>
        <h1 className="font-serif text-5xl font-black leading-[0.9] tracking-tighter sm:text-6xl">
          Ask the Editor
        </h1>
        <p className="drop-cap mt-6 font-body leading-relaxed text-neutral-700 text-justify hyphens-auto">
          Put your question to the Upily desk. Answers draw on the stories we have filed in the
          past two days, with a web search when our own coverage runs thin. Follow-up questions
          keep the thread of the conversation.
        </p>
        <p className="mt-4 font-mono text-[11px] uppercase tracking-widest text-neutral-500">
          Answers are AI-generated. Check important facts with the original reporting.
        </p>
      </header>

      <section aria-label="Conversation with the Upily desk" className="lg:col-span-8">
        <ChatPanel suggestions={SUGGESTIONS} />
      </section>
    </div>
  )
}
