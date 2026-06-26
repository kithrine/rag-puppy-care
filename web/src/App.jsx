import { useState, useRef, useEffect } from 'react'
import ChatBox from './components/ChatBox.jsx'
import Message from './components/Message.jsx'

// A few starter questions for the empty state. They double as one-tap prompts.
const EXAMPLES = [
  'How often should I feed my puppy?',
  'When does my puppy need vaccinations?',
  'Is chocolate dangerous for dogs?',
  'How do I crate train at night?',
]

export default function App() {
  // The whole conversation lives here. Each item is one of:
  //   { role: 'user', text }
  //   { role: 'assistant', answer, refused, sources }   (from /api/ask)
  //   { role: 'assistant', error: true, text }          (network/server failure)
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const endRef = useRef(null)

  // Keep the newest message (and the thinking indicator) in view.
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  async function ask(question) {
    const q = question.trim()
    if (!q || loading) return

    setMessages((prev) => [...prev, { role: 'user', text: q }])
    setLoading(true)
    try {
      // Same relative URL in dev and prod: Vite proxies /api to FastAPI in dev,
      // and FastAPI serves both in prod.
      const res = await fetch('/api/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setMessages((prev) => [...prev, { role: 'assistant', ...data }])
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          error: true,
          text: "I couldn't reach the server. Make sure the API is running on port 8000.",
        },
      ])
    } finally {
      setLoading(false)
    }
  }

  const empty = messages.length === 0

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-3xl flex-col px-4 sm:px-6">
      {/* ---- Header ---- */}
      <header className="animate-rise pt-10 pb-6 text-center sm:pt-14">
        <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-line bg-card/70 px-4 py-1.5 text-xs font-semibold uppercase tracking-[0.18em] text-muted">
          <span aria-hidden="true">🐾</span> Grounded in trusted puppy docs
        </div>
        <h1 className="font-display text-5xl font-semibold leading-none tracking-tight text-ink sm:text-6xl">
          Puppy Care
        </h1>
        <p className="mx-auto mt-3 max-w-md text-[15px] leading-relaxed text-muted">
          Ask anything about raising your puppy. Answers come only from the
          handbook — with the exact sources shown.
        </p>
      </header>

      {/* ---- Conversation ---- */}
      <main className="scroll-soft flex-1 overflow-y-auto pb-4">
        {empty ? (
          <EmptyState onPick={ask} />
        ) : (
          <div className="flex flex-col gap-5 py-2">
            {messages.map((m, i) => (
              <Message key={i} message={m} />
            ))}
            {loading && <ThinkingIndicator />}
            <div ref={endRef} />
          </div>
        )}
      </main>

      {/* ---- Composer ---- */}
      <div className="sticky bottom-0 -mx-4 bg-gradient-to-t from-paper via-paper to-transparent px-4 pb-5 pt-2 sm:-mx-6 sm:px-6">
        <ChatBox onSend={ask} loading={loading} />
        <p className="mt-2 text-center text-xs text-muted/80">
          Puppy Care can only answer from its documents — always confirm health
          decisions with your vet.
        </p>
      </div>
    </div>
  )
}

function EmptyState({ onPick }) {
  return (
    <div className="animate-rise flex flex-col items-center py-6 text-center">
      <div className="mb-5 grid h-16 w-16 place-items-center rounded-2xl border border-line bg-card text-3xl shadow-sm">
        🐶
      </div>
      <h2 className="font-display text-2xl font-medium text-ink">
        What can I help you with?
      </h2>
      <p className="mt-1.5 mb-6 max-w-sm text-sm text-muted">
        Try one of these, or ask your own question below.
      </p>
      <div className="grid w-full gap-2.5 sm:grid-cols-2">
        {EXAMPLES.map((ex) => (
          <button
            key={ex}
            onClick={() => onPick(ex)}
            className="group rounded-xl border border-line bg-card px-4 py-3 text-left text-[15px] text-ink shadow-sm transition hover:-translate-y-0.5 hover:border-honey/50 hover:shadow-md"
          >
            <span className="mr-2 text-honey transition group-hover:translate-x-0.5">
              ❯
            </span>
            {ex}
          </button>
        ))}
      </div>
    </div>
  )
}

function ThinkingIndicator() {
  return (
    <div className="flex items-center gap-3">
      <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-honey-soft text-base">
        🐾
      </div>
      <div className="flex items-center gap-1.5 rounded-2xl rounded-tl-sm border border-line bg-card px-4 py-3 shadow-sm">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="inline-block h-2 w-2 rounded-full bg-honey"
            style={{ animation: 'blink 1.4s infinite both', animationDelay: `${i * 0.18}s` }}
          />
        ))}
      </div>
    </div>
  )
}
