// A retrieved chunk shown as a little reference "index card": a filename tab, a
// score meter, and the snippet. The API may include an optional `title`; fall
// back to the filename when it's absent.
export default function SourceCard({ source }) {
  const { source: filename, score, snippet, title } = source

  // TF-IDF cosine scores top out around ~0.5 in practice, so scale the meter
  // against 0.6 for a readable fill while still showing the exact value.
  const fill = Math.max(0.04, Math.min(1, score / 0.6))

  return (
    <div className="group rounded-xl border border-line bg-card p-3 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md">
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="truncate rounded-md bg-paper-deep px-2 py-0.5 font-mono text-xs font-medium text-ink/80">
          {title || filename}
        </span>
        <span className="shrink-0 font-mono text-xs tabular-nums text-muted">
          {score.toFixed(2)}
        </span>
      </div>

      {/* score meter */}
      <div className="mb-2 h-1.5 w-full overflow-hidden rounded-full bg-paper-deep">
        <div
          className="h-full rounded-full bg-honey transition-all"
          style={{ width: `${fill * 100}%` }}
        />
      </div>

      <p className="line-clamp-3 text-[13px] italic leading-relaxed text-muted">
        {snippet}
      </p>
    </div>
  )
}
