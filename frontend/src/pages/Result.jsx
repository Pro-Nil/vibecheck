import React, { useEffect, useState } from 'react'
import { ArrowRight, Calendar, Check, CircleHelp, FolderOpen, Minus, RotateCcw, Sparkles, TrendingDown, TrendingUp, User } from 'lucide-react'
import { api, fmtDate, pct } from '../api.js'
import { FeatureStrips, PluginPanel, StripLegend, Swatches } from '../components/Charts.jsx'
import { Loading, Mark, Notice, PinnedPost, Stamp, VerdictChip } from '../components/ui.jsx'

const ENG_ICON = { 'Above usual': TrendingUp, Usual: Minus, 'Below usual': TrendingDown }
const OUTCOMES = [['approved', 'Approved'], ['rejected', 'Rejected'], ['posted', 'Posted']]
const STAMP_DATE = s => (s ? new Date(s).toLocaleDateString(undefined, { day: 'numeric', month: 'short' }).toUpperCase() : '')

/** The verdict lines drawn as zones on a 0–100 rule, with the score as a marker. */
function ScoreScale({ score, borderline, approve }) {
  const W = 330, X = v => 6 + (v / 100) * (W - 12), y = 30
  const zones = [[0, borderline, 'Off-brand', 0.07], [borderline, approve, 'Borderline', 0.14], [approve, 100, 'On-brand', 0.26]]
  return (
    <div className="scale">
      <svg viewBox={`0 0 ${W} 62`} role="img" aria-label={`Score ${Math.round(score)} on a scale where ${Math.round(borderline)} starts borderline and ${Math.round(approve)} starts on-brand`}>
        {zones.map(([a, b, l, o]) => (
          <g key={l}>
            <rect x={X(a) + 1} y={y - 7} width={Math.max(0, X(b) - X(a) - 2)} height="14" rx="3" fill={`rgba(255,255,255,${o})`} />
            {X(b) - X(a) > 96 && <text className="zone-l" x={(X(a) + X(b)) / 2} y={y + 26} textAnchor="middle">{l}</text>}
          </g>
        ))}
        {[borderline, approve].map(t => <text key={t} className="tick" x={X(t)} y={y - 13} textAnchor="middle">{Math.round(t)}</text>)}
        <g transform={`translate(${X(Math.max(0, Math.min(100, score)))} ${y})`}>
          <line y1="-12" y2="12" stroke="#fff" strokeWidth="3" strokeLinecap="round" />
          <circle r="5" fill="#fff" />
        </g>
      </svg>
      <p className="scale-cap">Off-brand below {Math.round(borderline)} · Borderline {Math.round(borderline)}–{Math.round(approve) - 1} · On-brand {Math.round(approve)}+</p>
    </div>
  )
}

function Parts({ c }) {
  const k = c.components
  const items = [
    k.looks_like !== undefined && ['Look', k.looks_like, 'overall look vs the team'],
    k.colour_match !== undefined && ['Colours', k.colour_match, 'vs similar-topic posts'],
    k.style_match !== undefined && ['Style', k.style_match, 'vs similar-topic posts'],
    k.classifier !== undefined && ['Team vs others', k.classifier, 'looks like the team, not other pages'],
    k.text !== undefined && ['Description', k.text, 'description fit'],
    k.approval !== undefined && ['Approval', k.approval, `learned from the seniors' decisions (weight ${pct(c.weights.approval)}%)`],
  ].filter(Boolean)
  return (
    <div className="parts" aria-label="Parts of the score">
      {items.map(([l, v, t]) => (
        <div key={l} title={t}><b className="num">{pct(v)}%</b><span>{l}</span><i style={{ '--v': `${pct(v)}%` }} aria-hidden="true" /></div>
      ))}
    </div>
  )
}

function FinishCard({ finish }) {
  const todo = finish.checks.filter(c => c.severity !== 'ok')
  const ok = finish.checks.filter(c => c.severity === 'ok')
  return (
    <section className={`paper fix${todo.length ? '' : ' clear'}`} aria-labelledby="fin-h">
      <h2 id="fin-h">Finish checklist</h2>
      <p className="sub">{finish.must_fix ? `${finish.must_fix} to fix before posting` : 'Ready to post'}{finish.warnings ? `, ${finish.warnings} worth a look` : ''}.
        Calibrated on this team's own posts; about readiness, not taste, so it does not change the score.</p>
      {todo.length > 0 && (
        <ul className="fix-list">
          {todo.map(c => <li key={c.feature} className={c.severity === 'warn' ? 'warn' : ''}><Mark kind={c.severity === 'fail' ? 'bad' : 'warn'} label={c.severity === 'fail' ? 'must fix' : 'worth a look'} /><span><strong>{c.label}.</strong> {c.text}</span></li>)}
        </ul>
      )}
      {ok.length > 0 && (
        <div className="passed" aria-label="Checks passed">
          {ok.map(c => <span key={c.feature} title={c.text}><Check aria-hidden="true" />{c.label}</span>)}
        </div>
      )}
    </section>
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
  const many = !final && c.inspo_urls.length > 1
  const summary = c.vs_new_posts != null
    ? <>Fits better than <strong>{pct(c.vs_new_posts)}%</strong> of the posts the team published next, posts the model had not seen.</>
    : c.components.on_brand !== undefined ? <>More on-brand than <strong>{pct(c.components.on_brand)}%</strong> of the team's own posts.</> : null

  return (
    <div>
      <div className="page-head">
        <div className="titles">
          <h1>{final ? 'Design check' : 'Idea check'} <span className="num">#{c.id}</span></h1>
          <div className="meta-chips">
            {c.project && <span><FolderOpen aria-hidden="true" />{c.project}</span>}
            {c.user && <span><User aria-hidden="true" />{c.user}</span>}
            <span><Calendar aria-hidden="true" />{fmtDate(c.created_at)}</span>
            <span>Model v{c.model_version}</span>
          </div>
        </div>
        <div className="actions">
          <a className="btn" href={final ? '#/final' : '#/check'}><RotateCcw className="i" aria-hidden="true" />{final ? 'Check another version' : 'Edit and re-check'}</a>
          {!final && <a className="btn primary" href={`#/final/${c.id}`}>Check my finished design<ArrowRight className="i" aria-hidden="true" /></a>}
        </div>
      </div>

      <section className="board" aria-labelledby="verdict-h">
        <div className="result-board">
          <div className={`mine${many ? ' many' : ''}`}>
            {c.inspo_urls.length > 0 ? c.inspo_urls.slice(0, 5).map((u, i) => (
              <figure className={`pinned${c.per_image && many ? ' has-plate' : ''}`} key={u} style={{ '--tilt': i === 0 ? '-1.6deg' : i % 2 ? '1.4deg' : '-0.8deg', '--pin-c': i === 0 ? 'var(--pin)' : undefined, margin: 0 }}>
                <img src={u} alt={final ? 'Your finished design' : `Your inspiration image ${i + 1}`} style={final ? { aspectRatio: 'auto' } : undefined} />
                {c.per_image && many && <div className="nameplate"><span>Image {i + 1}</span><strong className="num">{Math.round(c.per_image[i])}</strong></div>}
                {i === 0 && <Stamp text={stampText} sub={`VibeCheck · ${STAMP_DATE(c.created_at)}`} press />}
              </figure>
            )) : (
              <div className="pinned" style={{ '--tilt': '-1.2deg', '--pin-c': 'var(--pin)' }}>
                <p style={{ color: '#14171a', padding: '28px 14px', minHeight: 200 }}>“{c.description}”</p>
                <Stamp text={stampText} sub={`VibeCheck · ${STAMP_DATE(c.created_at)}`} press />
              </div>
            )}
          </div>

          <div className="readout">
            <div className="lede">
            <div className="score-n" aria-label={`Score ${Math.round(c.score)} out of 100`}>{Math.round(c.score)}<span>/ 100</span></div>
            <div className="verdict-line">
              <h2 id="verdict-h">{c.verdict}</h2>
              <VerdictChip level={c.verdict_level}>{c.verdict_level === 'approve' ? 'fits the team' : c.verdict_level === 'borderline' ? 'close' : 'does not fit yet'}</VerdictChip>
            </div>
            {summary && <p className="summary">{summary}</p>}
            {c.confidence && c.confidence.level !== 'high' && (
              <span className="conf" title={c.confidence.notes.join('. ')}><CircleHelp aria-hidden="true" />{c.confidence.level[0].toUpperCase() + c.confidence.level.slice(1)} confidence: {c.confidence.notes[0]}</span>
            )}
            </div>
            <div className="detail">
            <ScoreScale score={c.score} borderline={c.thresholds.borderline} approve={c.thresholds.approve} />
            <Parts c={c} />
            {(c.engagement || c.appeal) && (
              <div className="extras">
                {c.engagement && <span><Eng aria-hidden="true" />{c.engagement.band} likes expected ({c.engagement.predicted_vs_usual}× usual)</span>}
                {c.appeal && <span title="LAION aesthetic score: general visual appeal. It predicts likes a little but is not this team's taste, so it does not change the verdict."><Sparkles aria-hidden="true" />General appeal above {pct(c.appeal.percentile)}% of team posts</span>}
              </div>
            )}
            </div>
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

      <div className="grid cols-2 section-gap">
        <section className={`paper fix${problems.length ? '' : ' clear'}`} aria-labelledby="why-h">
          <h2 id="why-h">{problems.length ? `What to change (${problems.length})` : 'Nothing to change'}</h2>
          <p className="sub">{problems.length ? "Measured against this team's own posts." : 'Everything we measure fits this team.'}</p>
          {problems.length > 0 && (
            <ul className="fix-list">
              {problems.map(r => <li key={r.feature}><Mark kind="bad" /><span>{r.text}</span></li>)}
            </ul>
          )}
        </section>
        {c.finish ? <FinishCard finish={c.finish} /> : (
          c.plan_style && (
            <section className="paper" aria-labelledby="strip-h">
              <h2 id="strip-h">Against the team's usual range</h2>
              <StripLegend />
              <div className="body"><FeatureStrips reasons={c.reasons} /></div>
            </section>
          )
        )}
      </div>

      {fits.length > 0 && (
        <section className="paper section-gap" aria-labelledby="fits-h">
          <h2 id="fits-h">What already fits ({fits.length})</h2>
          <ul className="fits">
            {fits.map(r => <li key={r.feature}><Mark kind="ok" /><span>{r.text}</span></li>)}
          </ul>
        </section>
      )}

      <div className="grid cols-2 section-gap">
        {c.finish && c.plan_style && (
          <section className="paper" aria-labelledby="strip-h">
            <h2 id="strip-h">Against the team's usual range</h2>
            <StripLegend />
            <div className="body"><FeatureStrips reasons={c.reasons} /></div>
          </section>
        )}
        <section className="paper" aria-labelledby="pal-h">
          <h2 id="pal-h">Colours</h2>
          <div className="palettes">
            {c.plan_palette?.length > 0 && <div><span className="label">{final ? 'Your design' : 'Your inspiration'}</span><Swatches colors={c.plan_palette} label="Your main colours" /></div>}
            <div><span className="label">The team's signature palette</span><Swatches colors={c.signature_palette} label="Team signature palette" /></div>
          </div>
        </section>
        {pvf && (
          <section className="paper" aria-labelledby="pvf-h">
            <h2 id="pvf-h">Plan vs final</h2>
            <p className="sub">Compared with <a href={`#/result/${pvf.plan_check_id}`}>plan check #{pvf.plan_check_id}</a>.</p>
            <div className="ledger">
              <div><b className="num">{Math.round(pvf.plan_score)} → {Math.round(c.score)}</b><span>on-brand score, plan to final</span></div>
              <div><b className="num">{pct(pvf.similarity)}%</b><span>look-alike with the plan's inspiration. {pvf.similarity >= 0.8 ? 'You built what you planned.' : pvf.similarity >= 0.6 ? 'Same direction, changed along the way.' : 'Quite different from the plan.'}</span></div>
            </div>
            <p className="sub" style={{ marginTop: 14 }}>{c.score >= pvf.plan_score - 5 ? "The final kept (or improved on) the plan's fit with the team." : "The final drifted from what made the plan fit; compare the reasons with the plan's."}</p>
          </section>
        )}
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
