import React from 'react'
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { C, LEVEL, pct } from '../api.js'

/** Semi-circle gauge with the score and verdict written in words. */
export function Gauge({ score, level, label }) {
  const r = 80, cx = 100, cy = 96
  const a = Math.PI * (1 - score / 100)
  const x = cx + r * Math.cos(a), y = cy - r * Math.sin(a)
  const col = LEVEL[level]?.color || C.grey
  return (
    <svg viewBox="0 0 200 116" width="220" role="img" aria-label={`Vibe match ${Math.round(score)} out of 100: ${label}`}>
      <path d={`M${cx - r} ${cy} A${r} ${r} 0 0 1 ${cx + r} ${cy}`} fill="none" stroke="var(--surface-2)" strokeWidth="16" strokeLinecap="round" />
      <path d={`M${cx - r} ${cy} A${r} ${r} 0 0 1 ${x} ${y}`} fill="none" stroke={col} strokeWidth="16" strokeLinecap="round" />
      <text x={cx} y={cy - 14} textAnchor="middle" fontSize="38" fontWeight="800" fill="var(--text)">{Math.round(score)}</text>
      <text x={cx} y={cy + 12} textAnchor="middle" fontSize="11" fill="var(--text-2)">out of 100</text>
    </svg>
  )
}

/** One row per style feature: the team's usual range as a band, the plan as a dot. */
export function FeatureStrips({ reasons }) {
  const rows = reasons.filter(r => r.usual_low !== undefined)
  const W = 520, rowH = 34, left = 170, right = 20, w = W - left - right
  const X = v => left + v * w
  return (
    <svg viewBox={`0 0 ${W} ${rows.length * rowH + 30}`} width="100%" role="img"
      aria-label="Your plan compared with this team's usual range for each style feature">
      {[0, 0.25, 0.5, 0.75, 1].map(t => (
        <g key={t}>
          <line x1={X(t)} x2={X(t)} y1={4} y2={rows.length * rowH + 4} stroke="var(--border)" />
          <text x={X(t)} y={rows.length * rowH + 22} textAnchor="middle" fontSize="11" fill="var(--text-2)">{t * 100}</text>
        </g>
      ))}
      {rows.map((r, i) => {
        const y = i * rowH + rowH / 2 + 4
        return (
          <g key={r.feature}>
            <title>{r.text}</title>
            <text x={left - 10} y={y + 4} textAnchor="end" fontSize="12.5" fill="var(--text)">{r.label}</text>
            <rect x={X(r.usual_low)} y={y - 7} width={Math.max(2, X(r.usual_high) - X(r.usual_low))} height="14" rx="7" fill={C.team} fillOpacity="0.22" stroke={C.team} />
            <line x1={X(r.usual_mid)} x2={X(r.usual_mid)} y1={y - 7} y2={y + 7} stroke={C.team} strokeWidth="2" />
            {r.ok
              ? <circle cx={X(r.plan)} cy={y} r="7" fill={C.plan} stroke="var(--surface)" strokeWidth="2" />
              : <g transform={`translate(${X(r.plan)} ${y})`}><rect x="-7" y="-7" width="14" height="14" transform="rotate(45)" fill={C.reject} stroke="var(--surface)" strokeWidth="2" /></g>}
          </g>
        )
      })}
    </svg>
  )
}

export function Swatches({ colors, label }) {
  if (!colors?.length) return <p className="muted small">No colours.</p>
  return (
    <div>
      <div className="swatches" role="img" aria-label={`${label}: ${colors.map(c => `${c.hex} ${pct(c.share)}%`).join(', ')}`}>
        {colors.map(c => <div key={c.hex} style={{ background: c.hex, flex: c.share }} title={`${c.hex} · ${pct(c.share)}%`} />)}
      </div>
      <div className="swatch-labels" aria-hidden="true">{colors.map(c => <span key={c.hex}>{c.hex} {pct(c.share)}%</span>)}</div>
    </div>
  )
}

/** Draws a plugin's Panel JSON with our own components. */
export function PluginPanel({ p }) {
  if (!p.ok) return (
    <div className="card">
      <h3>{p.plugin}</h3>
      <p className="muted small">Plugin did not answer: {p.error}</p>
    </div>
  )
  const panel = p.panel
  return (
    <section className="card" aria-label={`Plugin: ${panel.title}`}>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h3>{panel.title}</h3>
        <span className="muted small">plugin{p.author_team ? ` by ${p.author_team}` : ''}</span>
      </div>
      {panel.summary && <p className="muted small">{panel.summary}</p>}
      {panel.metrics && (
        <div className="tiles" style={{ marginBottom: 12 }}>
          {panel.metrics.map(m => <div className="tile" key={m.label}><div className="v">{m.value}{m.unit || ''}</div><div className="l">{m.label}</div></div>)}
        </div>
      )}
      {panel.items && (
        <ul className="reasons">
          {panel.items.map((it, i) => (
            <li key={i}>
              {it.ok === true && <span className="mark ok" aria-label="good">✓</span>}
              {it.ok === false && <span className="mark bad" aria-label="problem">✗</span>}
              <span>{it.text}</span>
            </li>
          ))}
        </ul>
      )}
      {panel.chart && (
        <figure style={{ margin: '12px 0 0' }}>
          {panel.chart.title && <figcaption className="small muted">{panel.chart.title}</figcaption>}
          <ResponsiveContainer width="100%" height={200}>
            {panel.chart.type === 'line' ? (
              <LineChart data={panel.chart.points}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="label" fontSize={12} /><YAxis fontSize={12} label={{ value: panel.chart.y_label || '', angle: -90, position: 'insideLeft', fontSize: 12 }} />
                <Tooltip /><Line dataKey="value" stroke={C.team} strokeWidth={2} />
              </LineChart>
            ) : (
              <BarChart data={panel.chart.points}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="label" fontSize={12} /><YAxis fontSize={12} label={{ value: panel.chart.y_label || '', angle: -90, position: 'insideLeft', fontSize: 12 }} />
                <Tooltip /><Bar dataKey="value" fill={C.team} radius={[4, 4, 0, 0]}>{panel.chart.points.map((_, i) => <Cell key={i} />)}</Bar>
              </BarChart>
            )}
          </ResponsiveContainer>
        </figure>
      )}
    </section>
  )
}

export function Progress({ value, label }) {
  return (
    <div>
      <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(value * 100)} aria-label={label}>
        <div style={{ width: `${Math.round(value * 100)}%` }} />
      </div>
    </div>
  )
}
