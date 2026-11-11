import React, { useEffect, useState } from 'react'
import { api, fmtDate, LEVEL, pct } from '../api.js'
import { FeatureStrips, Gauge, PluginPanel, Swatches } from '../components/Charts.jsx'

const ENG_ICON = { 'Above usual': '▲', Usual: '●', 'Below usual': '▼' }

export default function ResultPage({ checkId }) {
  const [c, setC] = useState(null)
  const [err, setErr] = useState('')
  const [saving, setSaving] = useState(false)
  useEffect(() => { setC(null); api.getCheck(checkId).then(setC).catch(e => setErr(e.message)) }, [checkId])

  const mark = async result => {
    setSaving(true)
    try { setC({ ...(await api.outcome(checkId, result)), plugins: c.plugins }) } catch (e) { setErr(e.message) } finally { setSaving(false) }
  }

  if (err) return <p className="alert error" role="alert">{err}</p>
  if (!c) return <p className="muted" role="status">Loading result…</p>
  const lv = LEVEL[c.verdict_level]
  const problems = c.reasons.filter(r => !r.ok)
  const fits = c.reasons.filter(r => r.ok)

  return (
    <div className="stack">
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h1>Vibe check #{c.id}</h1>
        <a className="btn" href="#/check">Edit and re-check</a>
      </div>

      <section className="card verdict" aria-labelledby="verdict-h">
        <Gauge score={c.score} level={c.verdict_level} label={c.verdict} />
        <div className="verdict-text" style={{ flex: 1, minWidth: 240 }}>
          <h2 id="verdict-h" className="sr-only">Verdict</h2>
          <div className="big" style={{ color: lv.color }}><span aria-hidden="true">{lv.icon} </span>{c.verdict}</div>
          <p className="muted">
            Score {Math.round(c.score)} / 100. This team's line: {Math.round(c.thresholds.approve)}+ likely approved,
            {' '}{Math.round(c.thresholds.borderline)}–{Math.round(c.thresholds.approve) - 1} borderline.
          </p>
          <p className="small muted">
            {c.components.image_score !== undefined && <>Looks like the team: {Math.round(c.components.classifier * 100)}% · closer to the team than {pct(c.components.similarity)}% of other pages' posts</>}
            {c.components.text !== undefined && <> · description fit {pct(c.components.text)}%</>}
          </p>
          {c.engagement && (
            <p><span className="pill" style={{ color: 'var(--text-2)' }}><span aria-hidden="true">{ENG_ICON[c.engagement.band]}</span> {c.engagement.band} engagement</span>
              <span className="small muted"> · predicted {c.engagement.predicted_vs_usual}× this page's usual likes</span></p>
          )}
          <div className="row small" style={{ marginTop: 8 }}>
            <span className="muted">What did the seniors decide?</span>
            {['approved', 'rejected', 'posted'].map(r => (
              <button key={r} type="button" disabled={saving} aria-pressed={c.outcome === r} onClick={() => mark(r)}
                style={c.outcome === r ? { borderColor: 'var(--accent)', borderWidth: 2 } : undefined}>{r}</button>
            ))}
          </div>
        </div>
        {c.inspo_urls.length > 0 && (
          <div className="thumbs" style={{ width: 260 }} aria-label="Your inspiration images">
            {c.inspo_urls.map((u, i) => (
              <div className="thumb" key={u}><img src={u} alt={`Your inspiration image ${i + 1}`} />
                {c.per_image && <span className="tag">{Math.round(c.per_image[i])}</span>}</div>
            ))}
          </div>
        )}
      </section>

      <div className="grid cols-2">
        <section className="card" aria-labelledby="why-h">
          <h2 id="why-h">Why</h2>
          <p className="sub">{problems.length ? `${problems.length} thing${problems.length > 1 ? 's' : ''} off, ${fits.length} that fit.` : 'Everything we measure fits this team.'}</p>
          <ul className="reasons">
            {c.reasons.map(r => (
              <li key={r.feature}>
                <span className={`mark ${r.ok ? 'ok' : 'bad'}`} aria-label={r.ok ? 'fits' : 'off'}>{r.ok ? '✓' : '✗'}</span>
                <span>{r.text}</span>
              </li>
            ))}
          </ul>
        </section>

        <div className="stack">
          {c.plan_style && (
            <section className="card" aria-labelledby="strip-h">
              <h2 id="strip-h">Your plan vs the team's usual range</h2>
              <div className="legend" aria-hidden="true">
                <span><svg width="26" height="12"><rect x="1" y="1" width="24" height="10" rx="5" fill="#0072B2" fillOpacity=".22" stroke="#0072B2" /></svg>team's usual range (middle 80%)</span>
                <span><svg width="12" height="12"><circle cx="6" cy="6" r="5" fill="#009E73" /></svg>yours, fits</span>
                <span><svg width="12" height="12"><rect x="2" y="2" width="8" height="8" transform="rotate(45 6 6)" fill="#D55E00" /></svg>yours, off</span>
              </div>
              <FeatureStrips reasons={c.reasons} />
            </section>
          )}
          <section className="card" aria-labelledby="pal-h">
            <h2 id="pal-h">Colours</h2>
            {c.plan_palette?.length > 0 && <><h3 className="small muted">Your inspiration</h3><Swatches colors={c.plan_palette} label="Your inspiration's main colours" /></>}
            <h3 className="small muted" style={{ marginTop: 12 }}>This team's signature palette</h3>
            <Swatches colors={c.signature_palette} label="Team signature palette" />
          </section>
        </div>
      </div>

      <section className="card" aria-labelledby="near-h">
        <h2 id="near-h">Closest past posts from the team</h2>
        <p className="sub">What "on-brand" looks like near your idea.</p>
        <div className="posts">
          {c.nearest.map(p => (
            <figure className="post" key={p.id} style={{ margin: 0 }}>
              <img src={p.image_url} alt={p.caption ? `Past post: ${p.caption.slice(0, 120)}` : 'Past team post'} loading="lazy" />
              <figcaption className="meta"><strong>{pct(p.similarity)}% similar</strong><br />{fmtDate(p.posted_at)}{p.likes != null ? ` · ${p.likes} likes` : ''}</figcaption>
            </figure>
          ))}
        </div>
      </section>

      {c.plugins?.length > 0 && (
        <section aria-labelledby="plug-h" className="stack">
          <h2 id="plug-h">From plugins</h2>
          <div className="grid cols-2">{c.plugins.map(p => <PluginPanel key={p.plugin_id} p={p} />)}</div>
        </section>
      )}
      {c.description && <p className="small muted">Your description: “{c.description}” · model v{c.model_version} · {fmtDate(c.created_at)}</p>}
    </div>
  )
}
