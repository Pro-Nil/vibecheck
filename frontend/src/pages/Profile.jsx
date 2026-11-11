import React, { useEffect, useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer,
  Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from 'recharts'
import { api, C, fmtDate, pct } from '../api.js'
import { PluginPanel, Swatches } from '../components/Charts.jsx'

const GROUPS = [
  { key: 'other', name: "Other pages' posts", color: C.other, shape: 'triangle' },
  { key: 'team', name: "This team's posts", color: C.team, shape: 'circle' },
  { key: 'rejected', name: 'Rejected drafts', color: C.rejected, shape: 'cross' },
]
const TREND_KEYS = [
  ['brightness', 'Brightness', C.other, '0'],
  ['saturation', 'Saturation', C.team, '6 3'],
  ['text_amount', 'Amount of text', C.rejected, '2 2'],
  ['busyness', 'Busyness', C.plan, '0'],
]

function MapTip({ active, payload }) {
  const [post, setPost] = useState(null)
  const id = active && payload?.[0]?.payload?.post_id
  useEffect(() => { setPost(null); if (id) api.post(id).then(setPost).catch(() => {}) }, [id])
  if (!active || !id) return null
  return (
    <div className="card" style={{ padding: 8, width: 160 }}>
      {post ? <><img src={post.image_url} alt="" style={{ width: '100%', borderRadius: 6 }} />
        <div className="small">{post.source_page} · {fmtDate(post.posted_at)}</div></> : <span className="small">Loading…</span>}
    </div>
  )
}

export default function ProfilePage({ teamId, team }) {
  const [p, setP] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => { setP(null); setErr(''); if (teamId) api.profile(teamId).then(setP).catch(e => setErr(e.message)) }, [teamId])
  const groups = useMemo(() => p ? GROUPS.map(g => ({ ...g, data: p.map.filter(d => d.label === g.key) })) : [], [p])

  if (err) return <p className="alert" role="alert">{err} <a href="#/setup">Go to team setup.</a></p>
  if (!p) return <p className="muted" role="status">Loading the team's style…</p>
  const m = p.metrics
  const ranges = Object.entries(p.ranges).map(([k, r]) => ({ key: k, ...r }))
  return (
    <div className="stack">
      <h1>{team?.name}: learned style</h1>
      <p className="lead">What the model has learned from {m.n_team} team posts{p.date_range ? ` (${fmtDate(p.date_range[0])} – ${fmtDate(p.date_range[1])})` : ''}, compared against {m.n_other} posts from other pages.</p>

      <section className="card" aria-labelledby="health-h">
        <h2 id="health-h">Model health</h2>
        <p className="sub">Tested on 20% of posts the model never saw. Model v{p.model_version}, trained {fmtDate(p.trained_at)}.</p>
        <div className="tiles">
          <div className="tile"><div className="v">{m.auc ?? '—'}</div><div className="l">AUC: telling our posts from others (1.0 = perfect, 0.5 = guessing)</div></div>
          <div className="tile"><div className="v">{m.accuracy != null ? `${pct(m.accuracy)}%` : '—'}</div><div className="l">correct at the "likely approved" line</div></div>
          <div className="tile"><div className="v">{m.team_posts_passing != null ? `${pct(m.team_posts_passing)}%` : '—'}</div><div className="l">of unseen team posts score "likely approved"</div></div>
          <div className="tile"><div className="v">{m.real_rejects ? `${m.real_rejects.below_approve} / ${m.real_rejects.n}` : '—'}</div><div className="l">real rejected drafts caught</div></div>
          <div className="tile"><div className="v">{m.auc_vs_near_misses ?? '—'}</div><div className="l">AUC against near-misses (harder)</div></div>
          {m.weights && <div className="tile"><div className="v">{pct(m.weights.classifier)} / {pct(m.weights.similarity)}</div><div className="l">score mix: classifier / similarity, set by how well each did on unseen posts</div></div>}
          <div className="tile"><div className="v">{m.engagement ?`${m.engagement.mae} vs ${m.engagement.baseline_mae}` : '—'}</div><div className="l">engagement error vs. always-"usual" baseline (lower is better)</div></div>
        </div>
      </section>

      <div className="grid cols-2">
        <section className="card" aria-labelledby="map-h">
          <h2 id="map-h">Style map</h2>
          <p className="sub">Every post as a point; similar-looking posts sit close together. Hover a point to see the post.</p>
          <div className="legend" aria-hidden="true">
            <span><svg width="12" height="12"><circle cx="6" cy="6" r="5" fill={C.team} /></svg>This team</span>
            <span><svg width="12" height="12"><path d="M6 1L11 11H1Z" fill={C.other} /></svg>Other pages</span>
            <span><svg width="12" height="12"><path d="M2 2L10 10M10 2L2 10" stroke={C.rejected} strokeWidth="3" /></svg>Rejected drafts</span>
          </div>
          <div role="img" aria-label={`Scatter map of ${p.map.length} posts. This team's posts form their own cluster apart from other pages.`}>
            <ResponsiveContainer width="100%" height={340}>
              <ScatterChart margin={{ top: 10, right: 10, bottom: 10, left: -20 }}>
                <XAxis type="number" dataKey="x" hide domain={['dataMin - 0.5', 'dataMax + 0.5']} />
                <YAxis type="number" dataKey="y" hide domain={['dataMin - 0.5', 'dataMax + 0.5']} />
                <ZAxis range={[28, 28]} />
                <Tooltip content={<MapTip />} cursor={false} />
                {groups.map(g => <Scatter key={g.key} name={g.name} data={g.data} fill={g.color} shape={g.shape} fillOpacity={g.key === 'other' ? 0.55 : 0.9} isAnimationActive={false} />)}
              </ScatterChart>
            </ResponsiveContainer>
          </div>
        </section>

        <section className="card stack" aria-labelledby="sig-h">
          <div>
            <h2 id="sig-h">Signature palette</h2>
            <p className="sub">The colours this team uses most, by area.</p>
            <Swatches colors={p.signature_palette} label="Signature palette" />
          </div>
          <div>
            <h2>Typical style</h2>
            <p className="sub">Middle 80% of team posts (bar) and the median (line). Grey tick = other pages' median.</p>
            <svg viewBox={`0 0 520 ${ranges.length * 30 + 26}`} width="100%" role="img" aria-label="Team's usual range for each style feature compared with other pages">
              {ranges.map((r, i) => {
                const y = i * 30 + 16, X = v => 170 + v * 330
                return (
                  <g key={r.key}>
                    <text x="160" y={y + 4} textAnchor="end" fontSize="12.5" fill="var(--text)">{r.label}</text>
                    <line x1={X(0)} x2={X(1)} y1={y} y2={y} stroke="var(--border)" />
                    <rect x={X(r.p10)} y={y - 7} width={Math.max(2, X(r.p90) - X(r.p10))} height="14" rx="7" fill={C.team} fillOpacity=".22" stroke={C.team} />
                    <line x1={X(r.p50)} x2={X(r.p50)} y1={y - 8} y2={y + 8} stroke={C.team} strokeWidth="2.5" />
                    {r.other_p50 != null && <line x1={X(r.other_p50)} x2={X(r.other_p50)} y1={y - 10} y2={y + 10} stroke="var(--text-2)" strokeWidth="1.5" strokeDasharray="2 2" />}
                  </g>
                )
              })}
              {[0, 0.5, 1].map(t => <text key={t} x={170 + t * 330} y={ranges.length * 30 + 20} textAnchor="middle" fontSize="11" fill="var(--text-2)">{t * 100}</text>)}
            </svg>
          </div>
        </section>
      </div>

      <div className="grid cols-2">
        {p.trend.length > 1 && (
          <section className="card" aria-labelledby="trend-h">
            <h2 id="trend-h">Style over time</h2>
            <p className="sub">Monthly median of team posts (0–1). Lines differ by dash as well as colour.</p>
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={p.trend} margin={{ left: -16, right: 8 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="month" fontSize={11} minTickGap={24} />
                <YAxis domain={[0, 1]} fontSize={11} />
                <Tooltip formatter={v => Number(v).toFixed(2)} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                {TREND_KEYS.map(([k, name, col, dash]) => <Line key={k} dataKey={k} name={name} stroke={col} strokeDasharray={dash} strokeWidth={2} dot={false} />)}
              </LineChart>
            </ResponsiveContainer>
          </section>
        )}
        {p.what_works && (
          <section className="card" aria-labelledby="works-h">
            <h2 id="works-h">What goes with more likes</h2>
            <p className="sub">Correlation of each feature with likes (vs the page's usual likes that month). Right = more likes.</p>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={p.what_works} layout="vertical" margin={{ left: 40, right: 16 }}>
                <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                <XAxis type="number" domain={[-0.6, 0.6]} fontSize={11} />
                <YAxis type="category" dataKey="label" width={130} fontSize={11} />
                <ReferenceLine x={0} stroke="var(--text-2)" />
                <Tooltip formatter={v => Number(v).toFixed(2)} />
                <Bar dataKey="correlation" name="correlation">
                  {p.what_works.map(w => <Cell key={w.feature} fill={w.correlation >= 0 ? C.team : C.other} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </section>
        )}
      </div>

      {p.plugins?.length > 0 && (
        <section className="stack" aria-labelledby="pp-h">
          <h2 id="pp-h">From plugins</h2>
          <div className="grid cols-2">{p.plugins.map(x => <PluginPanel key={x.plugin_id} p={x} />)}</div>
        </section>
      )}
    </div>
  )
}
