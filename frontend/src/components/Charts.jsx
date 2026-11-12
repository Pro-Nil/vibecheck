import React from 'react'
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { C, pct } from '../api.js'
import { Mark } from './ui.jsx'

/** One row per style feature: the team's usual range as a band, the design as a dot (circle fits, diamond off). */
export function FeatureStrips({ reasons }) {
  const rows = reasons.filter(r => r.usual_low !== undefined)
  const W = 540, rowH = 36, left = 168, right = 18, w = W - left - right
  const X = v => left + v * w
  return (
    <svg viewBox={`0 0 ${W} ${rows.length * rowH + 30}`} width="100%" role="img"
      aria-label="Your design compared with this team's usual range for each style feature">
      {[0, 0.25, 0.5, 0.75, 1].map(t => (
        <g key={t}>
          <line x1={X(t)} x2={X(t)} y1={4} y2={rows.length * rowH + 4} stroke="var(--rule)" />
          <text x={X(t)} y={rows.length * rowH + 22} textAnchor="middle" fontSize="11" fill="var(--ink-2)">{t * 100}</text>
        </g>
      ))}
      {rows.map((r, i) => {
        const y = i * rowH + rowH / 2 + 4
        return (
          <g key={r.feature}>
            <title>{r.text}</title>
            <text x={left - 12} y={y + 4} textAnchor="end" fontSize="13" fill="var(--ink)">{r.label}</text>
            <rect x={X(r.usual_low)} y={y - 8} width={Math.max(2, X(r.usual_high) - X(r.usual_low))} height="16" rx="8" fill={C.team} fillOpacity="0.18" stroke={C.team} strokeOpacity=".7" />
            <line x1={X(r.usual_mid)} x2={X(r.usual_mid)} y1={y - 8} y2={y + 8} stroke={C.team} strokeWidth="2" />
            {r.ok
              ? <circle cx={X(r.plan)} cy={y} r="7.5" fill={C.approve} stroke="var(--paper)" strokeWidth="2.5" />
              : <g transform={`translate(${X(r.plan)} ${y})`}><rect x="-7" y="-7" width="14" height="14" transform="rotate(45)" fill={C.reject} stroke="var(--paper)" strokeWidth="2.5" /></g>}
          </g>
        )
      })}
    </svg>
  )
}

export function StripLegend() {
  return (
    <div className="legend" aria-hidden="true">
      <span><svg width="26" height="12"><rect x="1" y="1" width="24" height="10" rx="5" fill={C.team} fillOpacity=".18" stroke={C.team} /></svg>team's usual range (middle 80%)</span>
      <span><svg width="12" height="12"><circle cx="6" cy="6" r="5" fill={C.approve} /></svg>yours, fits</span>
      <span><svg width="12" height="12"><rect x="2" y="2" width="8" height="8" transform="rotate(45 6 6)" fill={C.reject} /></svg>yours, off</span>
    </div>
  )
}

/** Palette as paint chips with hex and share. */
export function Swatches({ colors, label }) {
  if (!colors?.length) return <p className="muted small">No colours.</p>
  return (
    <ul className="chips" aria-label={label} style={{ listStyle: 'none', padding: 0, margin: 0 }}>
      {colors.map(c => (
        <li className="chip-card" key={c.hex}>
          <i style={{ background: c.hex }} />
          <code>{c.hex.toUpperCase()}</code>
          <span className="num">{pct(c.share)}% of area</span>
        </li>
      ))}
    </ul>
  )
}

/** Draws a plugin's Panel JSON with our own components. */
export function PluginPanel({ p }) {
  if (!p.ok) return (
    <section className="paper">
      <h3>{p.plugin}</h3>
      <p className="sub">This plugin did not answer: {p.error}</p>
    </section>
  )
  const panel = p.panel
  return (
    <section className="paper" aria-label={`Plugin: ${panel.title}`}>
      <header><h3>{panel.title}</h3><span className="kind">plugin{p.author_team ? ` · ${p.author_team}` : ''}</span></header>
      {panel.summary && <p className="sub">{panel.summary}</p>}
      {panel.metrics && (
        <div className="ledger">
          {panel.metrics.map(m => <div key={m.label}><b>{m.value}{m.unit || ''}</b><span>{m.label}</span></div>)}
        </div>
      )}
      {panel.items && (
        <ul className="reasons">
          {panel.items.map((it, i) => (
            <li key={i}>
              <Mark kind={it.ok === true ? 'ok' : it.ok === false ? 'bad' : 'info'} label={it.ok === true ? 'good' : it.ok === false ? 'problem' : 'note'} />
              <span>{it.text}</span>
            </li>
          ))}
        </ul>
      )}
      {panel.chart && (
        <figure style={{ margin: '16px 0 0' }}>
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
    <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(value * 100)} aria-label={label}>
      <div style={{ width: `${Math.round(value * 100)}%` }} />
    </div>
  )
}
