import React, { useEffect, useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, ReferenceArea, ReferenceLine, ResponsiveContainer,
  Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from 'recharts'
import { api, C, fmtDate, fmtShort, pct } from '../api.js'
import { PluginPanel, Swatches } from '../components/Charts.jsx'
import { Loading, Notice } from '../components/ui.jsx'

const ON_BOARD = { team: '#ffffff', other: '#E7A6CB', rejected: '#FFB27A' }
// drawn in this order: team posts last, on top, since they are what the map is about
const GROUPS = [
  { key: 'other', name: "Other pages' posts", shape: 'triangle' },
  { key: 'rejected', name: 'Rejected drafts', shape: 'cross' },
  { key: 'team', name: "This team's posts", shape: 'circle' },
]
const TREND_KEYS = [
  ['brightness', 'Brightness', '#E69F00', '0'],
  ['saturation', 'Saturation', C.team, '6 3'],
  ['text_amount', 'Amount of text', C.rejected, '2 2'],
  ['busyness', 'Busyness', C.plan, '0'],
]
const short = fmtShort

// low and high ends of each style feature, in words (0 = left/bottom, 1 = right/top)
const ENDS = {
  brightness: ['darker', 'brighter'], saturation: ['muted', 'saturated'], warmth: ['cooler', 'warmer'],
  text_amount: ['little text', 'text-heavy'], busyness: ['plain', 'busy'], whitespace: ['filled', 'empty space'],
  contrast: ['flat', 'high contrast'], illustration: ['photographic', 'illustrated'],
}
const median = a => { const s = [...a].sort((x, y) => x - y); return s.length ? s[Math.floor(s.length / 2)] : 0.5 }
const iqr = a => { const s = [...a].sort((x, y) => x - y); return s.length > 3 ? s[Math.floor(s.length * 0.75)] - s[Math.floor(s.length * 0.25)] : 0.2 }

/** How far apart the team's posts and the comparison posts are on one feature, in spread units. */
function separation(points, k) {
  const t = points.filter(d => d.label === 'team').map(d => d[k])
  let o = points.filter(d => d.label === 'other').map(d => d[k])
  if (o.length < 5) o = points.filter(d => d.label === 'rejected').map(d => d[k])
  if (t.length < 3 || o.length < 3) return 0
  return Math.abs(median(t) - median(o)) / Math.max(0.03, (iqr(t) + iqr(o)) / 2)
}

/** Every post plotted on two named style features; the team's usual zone drawn as a box. */
function StyleScatter({ points, ranges }) {
  const keys = Object.keys(ranges).filter(k => ENDS[k] && points.some(d => d[k] != null))
  const ranked = useMemo(() => [...keys].sort((a, b) => separation(points, b) - separation(points, a)), [points])
  const [xk, setX] = useState(null)
  const [yk, setY] = useState(null)
  const X = xk || ranked[0], Y = yk || (ranked[1] === X ? ranked[0] : ranked[1])
  const groups = useMemo(() => {
    const ls = points.filter(d => d.label === 'team' && d.likes != null).map(d => d.likes)
    const lo = Math.min(...ls), hi = Math.max(...ls)
    const size = d => (d.likes == null || !ls.length || hi === lo ? 0.35 : (d.likes - lo) / (hi - lo))
    return GROUPS.map(g => ({ ...g, data: points.filter(d => d.label === g.key).map(d => ({ ...d, x: d[X], y: d[Y], size: g.key === 'team' ? size(d) : 0.3 })) }))
  }, [points, X, Y])
  if (!X || !Y || !points.length) return <p className="muted">Not enough posts to plot yet.</p>

  const team = points.filter(d => d.label === 'team'), other = points.filter(d => d.label === 'other')
  const word = (k, a, b) => (Math.abs(a - b) < 0.04 ? null : ENDS[k][a > b ? 1 : 0])
  const tx = median(team.map(d => d[X])), ty = median(team.map(d => d[Y]))
  const diffs = other.length >= 5 ? [word(X, tx, median(other.map(d => d[X]))), word(Y, ty, median(other.map(d => d[Y])))].filter(Boolean) : []
  const rx = ranges[X], ry = ranges[Y]
  // zoom each axis to where the posts actually are (with a margin), so a narrow range does not squash them
  const dom = k => {
    const v = points.map(d => d[k]).filter(x => x != null)
    const lo = Math.min(...v), hi = Math.max(...v), pad = Math.max(0.02, (hi - lo) * 0.08)
    return [Math.max(0, +(lo - pad).toFixed(3)), Math.min(1, +(hi + pad).toFixed(3))]
  }
  const dx = dom(X), dy = dom(Y)
  const select = (id, v, set, not) => (
    <select id={id} value={v} onChange={e => set(e.target.value)}>
      {keys.filter(k => k !== not).map(k => <option key={k} value={k}>{ranges[k].label}</option>)}
    </select>
  )
  return (
    <div>
      <h2 id="map-h" style={{ color: '#fff' }}>Where the team's posts sit</h2>
      <p className="muted" style={{ marginTop: 6 }}>
        Every post plotted by two measured style features. The box is the team's usual zone (middle 80% of its posts).
        {diffs.length > 0 && <> Compared with other pages, this team's posts are <strong style={{ color: '#fff' }}>{diffs.join(' and ')}</strong>.</>}
      </p>
      <div className="axis-pick">
        <label htmlFor="ax-x">Across</label>{select('ax-x', X, setX, Y)}
        <label htmlFor="ax-y">Up</label>{select('ax-y', Y, setY, X)}
      </div>
      <div className="legend" aria-hidden="true">
        <span><svg width="14" height="14"><circle cx="7" cy="7" r="6" fill={ON_BOARD.team} /></svg>This team (bigger = more likes)</span>
        <span><svg width="14" height="14"><path d="M7 1.5L12.5 12H1.5Z" fill={ON_BOARD.other} /></svg>Other pages</span>
        <span><svg width="14" height="14"><path d="M2.5 2.5L11.5 11.5M11.5 2.5L2.5 11.5" stroke={ON_BOARD.rejected} strokeWidth="3" /></svg>Rejected drafts</span>
      </div>
      <div role="img" aria-label={`Scatter of ${points.length} posts by ${ranges[X].label} and ${ranges[Y].label}.${diffs.length ? ` This team's posts are ${diffs.join(' and ')} than other pages.` : ''}`} style={{ marginTop: 8 }}>
        <ResponsiveContainer width="100%" height={400}>
          <ScatterChart margin={{ top: 8, right: 16, bottom: 30, left: 8 }}>
            <CartesianGrid stroke="rgba(255,255,255,.08)" />
            <XAxis type="number" dataKey="x" domain={dx} ticks={dx} tickFormatter={v => (v === dx[0] ? `← ${ENDS[X][0]}` : `${ENDS[X][1]} →`)}
              tick={{ fill: '#a1a1aa', fontSize: 12 }} stroke="rgba(255,255,255,.25)"
              label={{ value: ranges[X].label, position: 'insideBottom', offset: -18, fill: '#fff', fontSize: 13, fontWeight: 700 }} />
            <YAxis type="number" dataKey="y" domain={dy} ticks={dy} tickFormatter={v => (v === dy[0] ? ENDS[Y][0] : ENDS[Y][1])}
              tick={{ fill: '#a1a1aa', fontSize: 12 }} stroke="rgba(255,255,255,.25)" width={86}
              label={{ value: ranges[Y].label, angle: -90, position: 'insideLeft', offset: 10, fill: '#fff', fontSize: 13, fontWeight: 700 }} />
            <ZAxis type="number" dataKey="size" domain={[0, 1]} range={[22, 190]} />
            <ReferenceArea x1={Math.max(dx[0], rx.p10)} x2={Math.min(dx[1], rx.p90)} y1={Math.max(dy[0], ry.p10)} y2={Math.min(dy[1], ry.p90)} ifOverflow="hidden" fill="#fff" fillOpacity={0.07} stroke="#fff" strokeOpacity={0.55} strokeDasharray="5 4"
              label={{ value: "team's usual zone", position: 'insideTopLeft', fill: '#fff', fontSize: 11 }} />
            <Tooltip content={<MapTip />} cursor={false} />
            {groups.map(g => <Scatter key={g.key} name={g.name} data={g.data} fill={ON_BOARD[g.key]} shape={g.shape}
              fillOpacity={g.key === 'team' ? 0.85 : 0.7} stroke={g.key === 'team' ? '#111113' : 'none'} strokeWidth={1} isAnimationActive={false} />)}
          </ScatterChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

function MapTip({ active, payload }) {
  const [post, setPost] = useState(null)
  const id = active && payload?.[0]?.payload?.post_id
  useEffect(() => { setPost(null); if (id) api.post(id).then(setPost).catch(() => {}) }, [id])
  if (!active || !id) return null
  return (
    <div className="map-tip">
      {post ? <>
        <img src={post.image_url} alt="" />
        <div className="nameplate"><strong>{short(post.posted_at)}</strong><span className="num">{post.likes != null ? `${post.likes} likes` : post.source_page}</span></div>
      </> : <span className="small">Loading…</span>}
    </div>
  )
}

export default function ProfilePage({ teamId, team }) {
  const [p, setP] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => { setP(null); setErr(''); if (teamId) api.profile(teamId).then(setP).catch(e => setErr(e.message)) }, [teamId])

  if (err) return <Notice kind="error">{err} <a href="#/setup">Go to team setup.</a></Notice>
  if (!p) return <Loading>Loading the team's style…</Loading>
  const m = p.metrics
  const ap = m.approval
  const ranges = Object.entries(p.ranges).map(([k, r]) => ({ key: k, ...r }))
  return (
    <div>
      <div className="page-head">
        <div className="titles">
          <h1>{team?.name}: <em>learned style</em></h1>
          <p className="lead">What the model learned from {m.n_team} team posts{p.date_range ? ` (${fmtDate(p.date_range[0])} to ${fmtDate(p.date_range[1])})` : ''}, compared with {m.n_other} posts from other pages. Model v{p.model_version}, trained {fmtDate(p.trained_at)}.</p>
        </div>
      </div>

      <section className="board" aria-labelledby="map-h">
        <div className="split" style={{ gridTemplateColumns: 'minmax(0, 1.5fr) minmax(0, 1fr)', alignItems: 'start' }}>
          <StyleScatter points={p.points || []} ranges={p.ranges} />
          <div>
            <h2 style={{ color: '#fff' }}>Signature palette</h2>
            <p className="muted" style={{ marginTop: 6, marginBottom: 14 }}>The colours this team uses most, by area.</p>
            <Swatches colors={p.signature_palette} label="Signature palette" />
            <div className="counts" style={{ marginTop: 28 }}>
              <div><b>{m.n_team}</b><span>team posts</span></div>
              <div><b>{m.n_other}</b><span>other pages' posts</span></div>
              {ap && <div><b>{ap.n_accepted + ap.n_rejected}</b><span>decided designs</span></div>}
            </div>
          </div>
        </div>
      </section>

      <section className="paper section-gap" aria-labelledby="health-h">
        <h2 id="health-h">How well the model knows this team</h2>
        <p className="sub">The on-brand score compares a design with this team's own posts: 30 means "more on-brand than 30% of them". Every number below comes from posts or decisions the model had not seen.</p>
        <div className="ledger">
          {ap && (
            <div>
              <b className={ap.on ? 'on' : 'off'}>{ap.on ? `On · AUC ${ap.auc}` : 'Off'}</b>
              <span>
                Approval model, learned from designs the seniors decided ({ap.n_accepted} accepted, {ap.n_rejected} rejected, {ap.n_projects} projects).{' '}
                {ap.on
                  ? `Tested leaving out one project at a time; it makes up ${pct(ap.weight)}% of each final-design score.`
                  : `Needs ${[ap.needs.accepted && `${ap.needs.accepted} more accepted`, ap.needs.rejected && `${ap.needs.rejected} more rejected`, ap.needs.projects && `${ap.needs.projects} more project${ap.needs.projects > 1 ? 's' : ''}`].filter(Boolean).join(', ') || 'to beat the plain on-brand score'}. Mark outcomes in History or upload decided designs in Team setup.`}
              </span>
            </div>
          )}
          {m.calibration?.n > 0 && (
            <div><b className="num">{pct(m.calibration.new_posts_off_brand)}% / {pct(m.calibration.new_posts_on_brand)}%</b>
              <span>of {m.calibration.n} newer team posts scored Off-brand / On-brand when the model only knew older posts ({m.calibration.method}). The verdict lines are set from these.</span></div>
          )}
          {m.auc != null && <div><b className="num">{m.auc}</b><span>AUC on unseen posts, this team vs other pages (1.0 perfect, 0.5 guessing)</span></div>}
          {m.accuracy != null && <div><b className="num">{pct(m.accuracy)}%</b><span>correct at the on-brand line on unseen posts</span></div>}
          <div><b className="num">{m.real_rejects ? `${m.real_rejects.below_approve} / ${m.real_rejects.n}` : '–'}</b><span>rejected drafts below the on-brand line{m.real_rejects ? ` (${m.real_rejects.below_borderline} below borderline)` : ''}. A check, not proof: accepted one-off posters can score low too.</span></div>
          {ap?.n_pairs > 0 && <div><b className="num">{pct(ap.on_brand_pairs_right)}%</b><span>of {ap.n_pairs} accepted-vs-rejected pairs from the same project where the on-brand score ranked the accepted one higher (50% = guessing)</span></div>}
          {m.near_misses_below_approve != null && <div><b className="num">{pct(m.near_misses_below_approve)}%</b><span>of automatically broken copies score below the on-brand line</span></div>}
          {m.weights && m.weights.classifier > 0 && <div><b className="num">{pct(m.weights.classifier)} / {pct(m.weights.on_brand)}</b><span>score mix: classifier / on-brand, set by how each did on unseen posts</span></div>}
          <div><b className="num">{m.engagement ? `${m.engagement.mae} vs ${m.engagement.baseline_mae}` : '–'}</b><span>likes error vs always guessing "usual" (lower is better){m.engagement?.model ? `; model: ${m.engagement.model}` : ''}</span></div>
        </div>
      </section>

      <div className="grid cols-2 section-gap">
        <section className="paper" aria-labelledby="typ-h">
          <h2 id="typ-h">Typical style</h2>
          <p className="sub">Middle 80% of team posts (band) and the median (line). Dashed tick: other pages' median.</p>
          <svg className="body" viewBox={`0 0 520 ${ranges.length * 32 + 26}`} width="100%" role="img" aria-label="Team's usual range for each style feature compared with other pages">
            {ranges.map((r, i) => {
              const y = i * 32 + 16, X = v => 170 + v * 330
              return (
                <g key={r.key}>
                  <text x="158" y={y + 4} textAnchor="end" fontSize="13" fill="var(--ink)">{r.label}</text>
                  <line x1={X(0)} x2={X(1)} y1={y} y2={y} stroke="var(--rule)" />
                  <rect x={X(r.p10)} y={y - 8} width={Math.max(2, X(r.p90) - X(r.p10))} height="16" rx="8" fill={C.team} fillOpacity=".18" stroke={C.team} strokeOpacity=".7" />
                  <line x1={X(r.p50)} x2={X(r.p50)} y1={y - 9} y2={y + 9} stroke={C.team} strokeWidth="2.5" />
                  {r.other_p50 != null && <line x1={X(r.other_p50)} x2={X(r.other_p50)} y1={y - 11} y2={y + 11} stroke="var(--ink-2)" strokeWidth="1.5" strokeDasharray="2 2" />}
                </g>
              )
            })}
            {[0, 0.5, 1].map(t => <text key={t} x={170 + t * 330} y={ranges.length * 32 + 20} textAnchor="middle" fontSize="11" fill="var(--ink-2)">{t * 100}</text>)}
          </svg>
        </section>
        {p.trend.length > 1 && (
          <section className="paper" aria-labelledby="trend-h">
            <h2 id="trend-h">Style over time</h2>
            <p className="sub">Monthly median of team posts (0 to 1). Lines differ by dash as well as colour.</p>
            <div className="body">
              <ResponsiveContainer width="100%" height={270}>
                <LineChart data={p.trend} margin={{ left: -16, right: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="month" fontSize={11} minTickGap={24} />
                  <YAxis domain={[0, 1]} fontSize={11} />
                  <Tooltip formatter={v => Number(v).toFixed(2)} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  {TREND_KEYS.map(([k, name, col, dash]) => <Line key={k} dataKey={k} name={name} stroke={col} strokeDasharray={dash} strokeWidth={2.2} dot={false} />)}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </section>
        )}
      </div>

      {p.what_works && (
        <section className="paper section-gap" aria-labelledby="works-h">
          <h2 id="works-h">What goes with more likes</h2>
          <p className="sub">Correlation of each feature with likes, relative to the page's usual likes that month. Right of the line means more likes.</p>
          <div className="body">
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={p.what_works} layout="vertical" margin={{ left: 40, right: 16 }}>
                <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                <XAxis type="number" domain={[-0.6, 0.6]} fontSize={11} />
                <YAxis type="category" dataKey="label" width={140} fontSize={12} />
                <ReferenceLine x={0} stroke="var(--ink-2)" />
                <Tooltip formatter={v => Number(v).toFixed(2)} />
                <Bar dataKey="correlation" name="correlation" radius={[0, 4, 4, 0]}>
                  {p.what_works.map(w => <Cell key={w.feature} fill={w.correlation >= 0 ? C.team : C.other} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>
      )}

      {p.plugins?.length > 0 && (
        <section className="section-gap" aria-labelledby="pp-h">
          <h2 id="pp-h" style={{ marginBottom: 14 }}>From plugins</h2>
          <div className="grid cols-2">{p.plugins.map(x => <PluginPanel key={x.plugin_id} p={x} />)}</div>
        </section>
      )}
    </div>
  )
}
