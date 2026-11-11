import React, { useEffect, useState } from 'react'
import { api, fmtDate, LEVEL, pct } from '../api.js'
import { FeatureStrips, Gauge, PluginPanel, Swatches } from '../components/Charts.jsx'

const ENG_ICON = { 'Above usual': '▲', Usual: '●', 'Below usual': '▼' }
const SEV = { fail: ['✗', 'bad', 'must fix'], warn: ['!', 'warn', 'worth a look'], ok: ['✓', 'ok', 'fine'] }

function FinishCard({ finish }) {
  return (
    <section className="card" aria-labelledby="fin-h">
      <h2 id="fin-h">Finish checklist</h2>
      <p className="sub">{finish.must_fix ? `${finish.must_fix} to fix before posting, ` : 'Nothing that must be fixed, '}
        {finish.warnings} worth a look. Each check is calibrated on this team's own posts, so it does not flag what the team normally does.
        These are about readiness, not taste: they do not change the score.</p>
      <ul className="reasons">
        {finish.checks.map(c => (
          <li key={c.feature}>
            <span className={`mark ${SEV[c.severity][1]}`} aria-label={SEV[c.severity][2]}>{SEV[c.severity][0]}</span>
            <span><strong>{c.label}.</strong> {c.text}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}

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
  const final = c.kind === 'final'
  const pvf = c.plan_vs_final

  return (
    <div className="stack">
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h1>{final ? 'Design check' : 'Vibe check'} #{c.id}</h1>
        <div className="row">
          {!final && <a className="btn" href={`#/final/${c.id}`}>Check my finished design</a>}
          <a className="btn" href={final ? '#/final' : '#/check'}>{final ? 'Check another version' : 'Edit and re-check'}</a>
        </div>
      </div>

      <section className="card verdict" aria-labelledby="verdict-h">
        <Gauge score={c.score} level={c.verdict_level} label={c.verdict} />
        <div className="verdict-text" style={{ flex: 1, minWidth: 240 }}>
          <h2 id="verdict-h" className="sr-only">Verdict</h2>
          <div className="big" style={{ color: lv.color }}><span aria-hidden="true">{lv.icon} </span>{c.verdict}</div>
          <p className="muted">
            Score {Math.round(c.score)} / 100 ({Math.round(c.thresholds.approve)}+ on-brand, {Math.round(c.thresholds.borderline)}–{Math.round(c.thresholds.approve) - 1} borderline).
            {c.components.on_brand !== undefined && c.components.classifier === undefined &&
              <> Your {final ? 'design is' : 'images alone are'} more on-brand than {Math.round(c.components.on_brand * 100)}% of this team's own posts.</>}
            {c.vs_new_posts != null && <> It fits better than <strong>{pct(c.vs_new_posts)}%</strong> of the posts this team actually published next (tested on posts the model had not seen).</>}
          </p>
          <p className="small muted">
            {c.components.looks_like !== undefined && <>Overall look {pct(c.components.looks_like)} · colours vs similar-topic posts {pct(c.components.colour_match)}{c.components.style_match !== undefined && <> · style vs similar-topic posts {pct(c.components.style_match)}</>}</>}
            {c.components.classifier !== undefined && <> · looks like the team vs other pages {pct(c.components.classifier)}%</>}
            {c.components.text !== undefined && <> · description fit {pct(c.components.text)}%</>}
            {c.components.approval !== undefined && <> · learned approval {pct(c.components.approval)}% (weight {pct(c.weights.approval)}%)</>}
          </p>
          {c.confidence && c.confidence.level !== 'high' && (
            <p className="small" style={{ color: 'var(--text-2)' }}>
              <strong>Confidence: {c.confidence.level}.</strong> {c.confidence.notes.map(n => n[0].toUpperCase() + n.slice(1)).join('. ')}.
            </p>
          )}
          <div className="row">
            {c.engagement && (
              <span><span className="pill" style={{ color: 'var(--text-2)' }}><span aria-hidden="true">{ENG_ICON[c.engagement.band]}</span> {c.engagement.band} engagement</span>
                <span className="small muted"> · predicted {c.engagement.predicted_vs_usual}× this page's usual likes</span></span>
            )}
            {c.appeal && (
              <span className="small muted" title="LAION aesthetic score: general visual appeal as rated by many people. It predicts likes a little but is not this team's taste, so it does not change the verdict.">
                Audience appeal: higher than {pct(c.appeal.percentile)}% of the team's posts (affects likes, not the verdict)
              </span>
            )}
          </div>
          <div className="row small" style={{ marginTop: 8 }}>
            <span className="muted">What did the seniors decide{final ? ' about this design' : ''}?</span>
            {['approved', 'rejected', 'posted'].map(r => (
              <button key={r} type="button" disabled={saving} aria-pressed={c.outcome === r} onClick={() => mark(r)}
                style={c.outcome === r ? { borderColor: 'var(--accent)', borderWidth: 2 } : undefined}>{r}</button>
            ))}
          </div>
          {final && <p className="small muted">Marking this design accepted or rejected teaches the approval model{c.project ? ` (project “${c.project}”)` : ''}.</p>}
          {c.finals?.length > 0 && (
            <p className="small">Finished designs from this plan: {c.finals.map((f, i) => (
              <span key={f.id}>{i ? ', ' : ''}<a href={`#/result/${f.id}`}>#{f.id}</a> ({Math.round(f.score)}, {f.verdict})</span>))}</p>
          )}
        </div>
        {c.inspo_urls.length > 0 && (
          <div className="thumbs" style={{ width: final ? 200 : 260 }} aria-label={final ? 'Your design' : 'Your inspiration images'}>
            {c.inspo_urls.map((u, i) => (
              <div className="thumb" key={u} style={final ? { width: 200, height: 'auto' } : undefined}><img src={u} alt={final ? 'Your finished design' : `Your inspiration image ${i + 1}`} style={final ? { height: 'auto' } : undefined} />
                {c.per_image && <span className="tag">{Math.round(c.per_image[i])}</span>}</div>
            ))}
          </div>
        )}
      </section>

      {(c.finish || pvf) && (
        <div className="grid cols-2">
          {c.finish && <FinishCard finish={c.finish} />}
          {pvf && (
            <section className="card" aria-labelledby="pvf-h">
              <h2 id="pvf-h">Plan vs final</h2>
              <p className="sub">How the finished design compares with <a href={`#/result/${pvf.plan_check_id}`}>plan check #{pvf.plan_check_id}</a>.</p>
              <div className="tiles">
                <div className="tile"><div className="v">{Math.round(pvf.plan_score)} → {Math.round(c.score)}</div><div className="l">on-brand score, plan → final</div></div>
                <div className="tile"><div className="v">{pct(pvf.similarity)}%</div><div className="l">look-alike with your plan's inspiration (CLIP). {pvf.similarity >= 0.8 ? 'You built what you planned.' : pvf.similarity >= 0.6 ? 'Same direction, changed along the way.' : 'Quite different from the plan.'}</div></div>
              </div>
              <p className="small muted">{c.score >= pvf.plan_score - 5 ? "The final kept (or improved on) the plan's fit with the team." : "The final drifted away from what made the plan fit; compare the reasons below with the plan's."}</p>
            </section>
          )}
        </div>
      )}

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
              <h2 id="strip-h">Your {final ? 'design' : 'plan'} vs the team's usual range</h2>
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
            {c.plan_palette?.length > 0 && <><h3 className="small muted">{final ? 'Your design' : 'Your inspiration'}</h3><Swatches colors={c.plan_palette} label="Your inspiration's main colours" /></>}
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
