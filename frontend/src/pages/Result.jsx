import React, { useEffect, useState } from 'react'
import { ArrowRight, RotateCcw, TrendingDown, TrendingUp, Minus } from 'lucide-react'
import { api, fmtDate, pct } from '../api.js'
import { FeatureStrips, PluginPanel, StripLegend, Swatches } from '../components/Charts.jsx'
import { Loading, Mark, Notice, PinnedPost, Stamp, VerdictChip } from '../components/ui.jsx'

const ENG_ICON = { 'Above usual': TrendingUp, Usual: Minus, 'Below usual': TrendingDown }
const SEV = { fail: ['bad', 'must fix'], warn: ['warn', 'worth a look'], ok: ['ok', 'fine'] }
const OUTCOMES = [['approved', 'Approved'], ['rejected', 'Rejected'], ['posted', 'Posted']]
const STAMP_DATE = s => (s ? new Date(s).toLocaleDateString(undefined, { day: 'numeric', month: 'short' }).toUpperCase() : '')

function FinishCard({ finish }) {
  return (
    <section className="paper" aria-labelledby="fin-h">
      <h2 id="fin-h">Finish checklist</h2>
      <p className="sub">{finish.must_fix ? `${finish.must_fix} to fix before posting, ` : 'Nothing that must be fixed, '}
        {finish.warnings} worth a look. Checks are calibrated on this team's own posts and are about readiness, not taste:
        they do not change the score.</p>
      <ul className="reasons">
        {finish.checks.map(c => (
          <li key={c.feature}><Mark kind={SEV[c.severity][0]} label={SEV[c.severity][1]} /><span><strong>{c.label}.</strong> {c.text}</span></li>
        ))}
      </ul>
    </section>
  )
}

function Parts({ c, final }) {
  const k = c.components
  const items = [
    k.looks_like !== undefined && ['Look', pct(k.looks_like), 'overall look vs the team'],
    k.colour_match !== undefined && ['Colours', pct(k.colour_match), 'vs similar-topic posts'],
    k.style_match !== undefined && ['Style', pct(k.style_match), 'vs similar-topic posts'],
    k.classifier !== undefined && ['Team vs others', pct(k.classifier), 'looks like the team, not other pages'],
    k.text !== undefined && ['Description', pct(k.text), 'description fit'],
    k.approval !== undefined && ['Approval', pct(k.approval), `learned from decisions (weight ${pct(c.weights.approval)}%)`],
  ].filter(Boolean)
  return (
    <div className="parts" aria-label="Parts of the score">
      {items.map(([l, v, t]) => <div key={l} title={t}><b>{v}%</b><span>{l}</span></div>)}
    </div>
  )
}

export default function ResultPage({ checkId }) {
  const [c, setC] = useState(null)
  const [err, setErr] = useState('')
  const [saving, setSaving] = useState(false)
  useEffect(() => { setC(null); setErr(''); api.getCheck(checkId).then(setC).catch(e => setErr(e.message)) }, [checkId])

  const mark = async result => {
    setSaving(true)
    try { setC({ ...(await api.outcome(checkId, result)), plugins: c.plugins }) } catch (e) { setErr(e.message) } finally { setSaving(false) }
  }

  if (err) return <Notice kind="error">{err}</Notice>
  if (!c) return <Loading>Loading the result…</Loading>
  const final = c.kind === 'final'
  const pvf = c.plan_vs_final
  const problems = c.reasons.filter(r => !r.ok)
  const fits = c.reasons.filter(r => r.ok)
  const Eng = c.engagement ? ENG_ICON[c.engagement.band] : null
  const stampText = c.outcome ? OUTCOMES.find(o => o[0] === c.outcome)?.[1] : c.verdict

  return (
    <div>
      <div className="page-head">
        <div className="titles">
          <h1>{final ? 'Design check' : 'Idea check'} <span className="num">#{c.id}</span></h1>
          <p className="meta">
            {c.project ? <>Project “{c.project}” · </> : null}{c.user ? <>by {c.user} · </> : null}{fmtDate(c.created_at)} · model v{c.model_version}
          </p>
        </div>
        <div className="actions">
          <a className="btn" href={final ? '#/final' : '#/check'}><RotateCcw className="i" aria-hidden="true" />{final ? 'Check another version' : 'Edit and re-check'}</a>
          {!final && <a className="btn primary" href={`#/final/${c.id}`}>Check my finished design<ArrowRight className="i" aria-hidden="true" /></a>}
        </div>
      </div>

      <section className="board" aria-labelledby="verdict-h">
        <div className="result-board">
          <div className={`mine${!final && c.inspo_urls.length > 1 ? ' many' : ''}`}>
            {c.inspo_urls.length > 0 ? c.inspo_urls.slice(0, 5).map((u, i) => (
              <figure className={`pinned${c.per_image && c.inspo_urls.length > 1 ? ' has-plate' : ''}`} key={u} style={{ '--tilt': i === 0 ? '-1.6deg' : i % 2 ? '1.4deg' : '-0.8deg', '--pin-c': i === 0 ? 'var(--pin)' : undefined, margin: 0 }}>
                <img src={u} alt={final ? 'Your finished design' : `Your inspiration image ${i + 1}`} style={final ? { aspectRatio: 'auto' } : undefined} />
                {c.per_image && c.inspo_urls.length > 1 && <div className="nameplate"><span>image {i + 1}</span><strong className="num">{Math.round(c.per_image[i])}</strong></div>}
                {i === 0 && <Stamp text={stampText} sub={`VibeCheck · ${STAMP_DATE(c.created_at)}`} press />}
              </figure>
            )) : (
              <div className="pinned" style={{ '--tilt': '-1.2deg', '--pin-c': 'var(--pin)' }}>
                <p style={{ color: '#14171a', padding: '28px 14px', minHeight: 200 }}>“{c.description}”</p>
                <Stamp text={stampText} sub={`VibeCheck · ${STAMP_DATE(c.created_at)}`} press />
              </div>
            )}
          </div>

          <div>
            <div className="score-n" aria-label={`Score ${Math.round(c.score)} out of 100`}>{Math.round(c.score)}<span>/ 100</span></div>
            <div className="verdict-line">
              <h2 id="verdict-h">{c.verdict}</h2>
              <VerdictChip level={c.verdict_level}>{c.verdict_level === 'approve' ? 'fits the team' : c.verdict_level === 'borderline' ? 'close' : 'does not fit yet'}</VerdictChip>
            </div>
            <p className="score-note">
              {Math.round(c.thresholds.approve)}+ is on-brand, {Math.round(c.thresholds.borderline)}–{Math.round(c.thresholds.approve) - 1} borderline.
              {c.components.on_brand !== undefined && c.components.classifier === undefined &&
                <> {final ? 'This design is' : 'Your images are'} more on-brand than <strong>{pct(c.components.on_brand)}%</strong> of the team's own posts.</>}
              {c.vs_new_posts != null && <> It fits better than <strong>{pct(c.vs_new_posts)}%</strong> of the posts the team published next (posts the model had not seen).</>}
            </p>
            {c.confidence && c.confidence.level !== 'high' && (
              <p className="score-note"><strong>Confidence: {c.confidence.level}.</strong> {c.confidence.notes.map(n => n[0].toUpperCase() + n.slice(1)).join('. ')}.</p>
            )}
            <Parts c={c} final={final} />
            {(c.engagement || c.appeal) && (
              <p className="score-note small" style={{ display: 'flex', gap: '6px 16px', flexWrap: 'wrap', alignItems: 'center' }}>
                {c.engagement && <span style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}><Eng className="i" aria-hidden="true" />{c.engagement.band} likes expected ({c.engagement.predicted_vs_usual}× usual)</span>}
                {c.appeal && <span title="LAION aesthetic score: general visual appeal. It predicts likes a little but is not this team's taste, so it does not change the verdict.">General appeal above {pct(c.appeal.percentile)}% of team posts (not part of the verdict)</span>}
              </p>
            )}
          </div>

          <div className="near">
            <p className="board-label">Closest team posts</p>
            <div className="near-grid">
              {c.nearest.slice(0, 6).map((p, i) => <PinnedPost key={p.id} post={p} i={i} match={p.similarity} />)}
            </div>
          </div>
        </div>
      </section>

      <section className="paper decide" aria-labelledby="decide-h" style={{ marginTop: 18 }}>
        <div>
          <h2 id="decide-h">What did the seniors decide?</h2>
          <p className="sub">{final
            ? <>Marking this design approved or rejected teaches the approval model{c.project ? <> for project “{c.project}”</> : null}.</>
            : 'Recording the outcome lets the team see which ideas made it.'}</p>
          {c.finals?.length > 0 && (
            <p className="sub">Finished designs from this plan: {c.finals.map((f, i) => (
              <span key={f.id}>{i ? ', ' : ''}<a href={`#/result/${f.id}`}>#{f.id}</a> ({Math.round(f.score)}, {f.verdict})</span>))}</p>
          )}
        </div>
        <div className="seg" role="group" aria-label="Seniors' decision">
          {OUTCOMES.map(([r, l]) => (
            <button key={r} type="button" disabled={saving} aria-pressed={c.outcome === r} onClick={() => mark(r)}>{l}</button>
          ))}
        </div>
      </section>

      {(c.finish || pvf) && (
        <div className="grid cols-2 section-gap">
          {c.finish && <FinishCard finish={c.finish} />}
          {pvf && (
            <section className="paper" aria-labelledby="pvf-h">
              <h2 id="pvf-h">Plan vs final</h2>
              <p className="sub">Compared with <a href={`#/result/${pvf.plan_check_id}`}>plan check #{pvf.plan_check_id}</a>.</p>
              <div className="ledger">
                <div><b>{Math.round(pvf.plan_score)} → {Math.round(c.score)}</b><span>on-brand score, plan to final</span></div>
                <div><b>{pct(pvf.similarity)}%</b><span>look-alike with the plan's inspiration. {pvf.similarity >= 0.8 ? 'You built what you planned.' : pvf.similarity >= 0.6 ? 'Same direction, changed along the way.' : 'Quite different from the plan.'}</span></div>
              </div>
              <p className="sub" style={{ marginTop: 14 }}>{c.score >= pvf.plan_score - 5 ? "The final kept (or improved on) the plan's fit with the team." : "The final drifted from what made the plan fit; compare the reasons with the plan's."}</p>
            </section>
          )}
        </div>
      )}

      <div className="split section-gap">
        <section className="paper" aria-labelledby="why-h">
          <h2 id="why-h">Why</h2>
          <p className="sub">{problems.length ? `${problems.length} thing${problems.length > 1 ? 's' : ''} off, ${fits.length} that fit.` : 'Everything we measure fits this team.'}</p>
          <ul className="reasons">
            {[...problems, ...fits].map(r => (
              <li key={r.feature}><Mark kind={r.ok ? 'ok' : 'bad'} /><span>{r.text}</span></li>
            ))}
          </ul>
        </section>

        <div className="stack" style={{ marginTop: 0 }}>
          {c.plan_style && (
            <section className="paper" aria-labelledby="strip-h">
              <h2 id="strip-h">Against the team's usual range</h2>
              <StripLegend />
              <div className="body"><FeatureStrips reasons={c.reasons} /></div>
            </section>
          )}
          <section className="paper" aria-labelledby="pal-h">
            <h2 id="pal-h">Colours</h2>
            {c.plan_palette?.length > 0 && <><p className="sub">{final ? 'Your design' : 'Your inspiration'}</p><div className="body" style={{ marginTop: 8 }}><Swatches colors={c.plan_palette} label="Your main colours" /></div></>}
            <p className="sub" style={{ marginTop: 16 }}>The team's signature palette</p>
            <div className="body" style={{ marginTop: 8 }}><Swatches colors={c.signature_palette} label="Team signature palette" /></div>
          </section>
        </div>
      </div>

      {c.plugins?.length > 0 && (
        <section aria-labelledby="plug-h" className="section-gap">
          <h2 id="plug-h" style={{ marginBottom: 14 }}>From plugins</h2>
          <div className="grid cols-2">{c.plugins.map(p => <PluginPanel key={p.plugin_id} p={p} />)}</div>
        </section>
      )}
      {c.description && <p className="sub section-gap">Your description: “{c.description}”</p>}
    </div>
  )
}
