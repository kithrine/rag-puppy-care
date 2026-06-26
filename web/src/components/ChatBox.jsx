import { useState } from 'react'

// The composer: a single-line input + Send button. Enter sends; Send is disabled
// while a request is in flight or the field is blank.
export default function ChatBox({ onSend, loading }) {
  const [value, setValue] = useState('')
  const canSend = value.trim().length > 0 && !loading

  function submit(e) {
    e.preventDefault()
    if (!canSend) return
    onSend(value)
    setValue('')
  }

  return (
    <form
      onSubmit={submit}
      className="flex items-center gap-2 rounded-2xl border border-line bg-card p-2 shadow-md focus-within:border-honey/60 focus-within:shadow-lg"
    >
      <label htmlFor="q" className="sr-only">
        Ask a question about puppy care
      </label>
      <input
        id="q"
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        disabled={loading}
        autoComplete="off"
        placeholder={loading ? 'Fetching from the handbook…' : 'Ask about feeding, vaccines, training…'}
        className="min-w-0 flex-1 bg-transparent px-3 py-2 text-[15px] text-ink placeholder:text-muted/70 focus:outline-none disabled:opacity-60"
      />
      <button
        type="submit"
        disabled={!canSend}
        aria-label="Send question"
        className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-honey text-card transition hover:bg-clay disabled:cursor-not-allowed disabled:bg-line disabled:text-muted"
      >
        {/* paper-plane arrow */}
        <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M22 2 11 13" />
          <path d="M22 2 15 22l-4-9-9-4 20-7Z" />
        </svg>
      </button>
    </form>
  )
}
