import SourceCard from './SourceCard.jsx'

// Renders one conversation turn. Three shapes:
//   user        -> a honey bubble on the right
//   error       -> a clay-tinted notice (couldn't reach the server)
//   refused     -> a distinct "not in the handbook" card, no sources
//   answered    -> the grounded answer + its SourceCards
export default function Message({ message }) {
  if (message.role === 'user') {
    return (
      <div className="animate-rise flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-tr-sm bg-honey-soft px-4 py-2.5 text-[15px] leading-relaxed text-ink shadow-sm">
          {message.text}
        </div>
      </div>
    )
  }

  return (
    <div className="animate-rise flex gap-3">
      <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-honey-soft text-base shadow-sm">
        🐾
      </div>

      <div className="min-w-0 flex-1">
        {message.error ? (
          <div className="rounded-2xl rounded-tl-sm border border-clay/30 bg-clay/5 px-4 py-3 text-[15px] leading-relaxed text-clay">
            {message.text}
          </div>
        ) : message.refused ? (
          <div className="rounded-2xl rounded-tl-sm border border-dashed border-line bg-card/60 px-4 py-3 shadow-sm">
            <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted">
              Not in the handbook
            </p>
            <p className="text-[15px] leading-relaxed text-ink/80">{message.answer}</p>
          </div>
        ) : (
          <>
            <div className="whitespace-pre-wrap rounded-2xl rounded-tl-sm border border-line bg-card px-4 py-3 text-[15px] leading-relaxed text-ink shadow-sm">
              {message.answer}
            </div>

            {message.sources?.length > 0 && (
              <div className="mt-3">
                <p className="mb-2 px-1 text-xs font-semibold uppercase tracking-[0.16em] text-muted">
                  Sources
                </p>
                <div className="grid gap-2.5 sm:grid-cols-2">
                  {message.sources.map((s, i) => (
                    <SourceCard key={i} source={s} />
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
