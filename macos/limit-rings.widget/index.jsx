// Limit Rings for Übersicht: the usage limits of Claude Code and Codex on the macOS desktop.
// The cards are built by card.mjs from the collector's output; this file only draws them.

import { view, settingsFrom } from "./lib/card.mjs"
import { makeTranslator } from "./lib/i18n.mjs"
import catalog from "./lib/de.json"
import settings from "./settings.json"

// ---- Settings: edit settings.json next to this file (kept when the installer updates the widget) ---------
const SETTINGS = settingsFrom(settings)
// providers: cards to show; login: live limits via login (without it only status line / session logs);
// remaining: show what is left instead of what is used; thresholds: warning and critical in percent used;
// top/left: position on the desktop in pixels
// ---------------------------------------------------------------------------------------------------------

const keys = list => list.filter(k => /^[a-z]+$/.test(k)).join(",")
const env =
  `LIMIT_RINGS_NOTIFY=0 LIMIT_RINGS_PROVIDERS=${keys(SETTINGS.providers)} LIMIT_RINGS_LOGIN=${keys(SETTINGS.login)} ` +
  `LIMIT_RINGS_THRESHOLDS=${SETTINGS.thresholds.map(n => Math.round(n)).join(",")}`
// A folder under another name (e.g. "limit-rings.widget 2") gets an envelope the card can explain, not sh's exit 127.
export const command =
  `if [ -f limit-rings.widget/run.sh ]; then ${env} sh limit-rings.widget/run.sh; ` +
  `else echo '{"envelope":1,"error":"widget-folder"}'; fi; echo "@exit=$?"`
export const refreshFrequency = 60000

const tr = makeTranslator(typeof navigator !== "undefined" ? navigator.language : "en-US", catalog)

export const initialState = { view: null }
export const updateState = (event, previous) => {
  const text = event.output || ""
  const m = text.match(/@exit=(\d+)\s*$/)
  const output = { exitCode: m ? Number(m[1]) : 1, stdout: m ? text.slice(0, m.index) : text }
  return { view: view(output, previous.view, Date.now(), SETTINGS, tr) }
}

export const className = `
  top: ${SETTINGS.top}px; left: ${SETTINGS.left}px;
  font: 12px -apple-system, BlinkMacSystemFont, sans-serif;
  --fg: #1d1d1f; --muted: #6e6e73; --track: rgba(0,0,0,.12); --card: rgba(255,255,255,.72);
  --normal: #0a84ff; --normal: AccentColor; --warning: #f5a623; --critical: #e5484d;
  @media (prefers-color-scheme: dark) {
    --fg: #f5f5f7; --muted: #a1a1a6; --track: rgba(255,255,255,.16); --card: rgba(30,30,32,.72);
  }
  color: var(--fg);
  .cards { display: flex; gap: 12px; align-items: flex-start; }
  .card { background: var(--card); backdrop-filter: blur(20px); border-radius: 12px; padding: 12px 14px; width: 260px; }
  .head { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
  .name { font-weight: 600; font-size: 14px; } .plan { color: var(--muted); margin-left: auto; }
  .row { margin: 6px 0; } .row .top { display: flex; justify-content: space-between; }
  .bar { position: relative; height: 6px; border-radius: 3px; background: var(--track); margin-top: 3px; }
  .bar .fill { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 3px; }
  .bar .mark { position: absolute; top: -2px; bottom: -2px; width: 2px; background: var(--fg); opacity: .5; }
  .muted { color: var(--muted); } .note, .hint, .status { color: var(--muted); font-size: 11px; margin-top: 4px; }
  .stale { opacity: .5; }
  .chart { display: flex; align-items: flex-end; gap: 1px; height: 28px; margin-top: 8px; }
  .chart div { flex: 1; background: var(--normal); opacity: .6; border-radius: 1px 1px 0 0; min-height: 1px; }
`

const tone = sev => `var(--${sev || "normal"})`

const Arc = ({ r, ring, width }) => {
  const c = 2 * Math.PI * r
  const pct = Math.max(0, Math.min(100, ring.percent))
  return (
    <g>
      <circle r={r} fill="none" stroke="var(--track)" strokeWidth={width} />
      <circle r={r} fill="none" stroke={tone(ring.severity)} strokeWidth={width} strokeLinecap="round"
              strokeDasharray={`${(pct / 100) * c} ${c}`} transform="rotate(-90)" />
      {ring.share !== null && (
        <line x1="0" y1={-r - width / 2 - 1} x2="0" y2={-r + width / 2 + 1} stroke="var(--fg)" strokeWidth="1.5"
              opacity=".6" transform={`rotate(${ring.share * 360})`} />
      )}
    </g>
  )
}

const Rings = ({ rings }) => (
  <svg width="40" height="40" viewBox="-20 -20 40 40">
    {rings.outer && <Arc r={16} ring={rings.outer} width={4} />}
    {rings.inner && <Arc r={9} ring={rings.inner} width={4} />}
  </svg>
)

const Row = ({ row }) => (
  <div className="row">
    <div className="top"><span>{row.label}</span><span>{row.percentText}<span className="muted">{row.countdown ? ` · ${row.countdown}` : ""}</span></span></div>
    <div className="bar">
      <div className="fill" style={{ width: `${Math.max(0, Math.min(100, row.percent))}%`, background: tone(row.severity) }} />
      {row.share !== null && <div className="mark" style={{ left: `${row.share * 100}%` }} />}
    </div>
    {row.note && <div className="note">{row.note}</div>}
  </div>
)

const Card = ({ card }) => (
  <div className={`card${card.stale ? " stale" : ""}`}>
    <div className="head"><Rings rings={card.rings} /><span className="name">{card.name}</span><span className="plan">{card.plan}</span></div>
    {card.rows.map(row => <Row key={row.label} row={row} />)}
    {card.hint && <div className="hint">{card.hint}</div>}
    {card.errors && <div className="hint">{card.errors}</div>}
    <div className="muted">{card.tokens.map(t => `${t.label} ${t.value}`).join(" · ")}</div>
    {card.series.length > 0 && (
      <div className="chart">{card.series.map(s => <div key={s.date} title={s.tip} style={{ height: `${s.height * 100}%` }} />)}</div>
    )}
    {card.footer && <div className="note">{card.footer}</div>}
  </div>
)

export const render = ({ view: v }) => {
  if (!v) return <div />
  return (
    <div>
      <div className="cards">{v.cards.map(card => <Card key={card.key} card={card} />)}</div>
      {v.status && <div className="status">{v.status}</div>}
    </div>
  )
}
