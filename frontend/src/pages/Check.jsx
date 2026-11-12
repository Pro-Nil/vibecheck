import React, { useEffect, useMemo, useRef, useState } from 'react'
import { ImagePlus, LoaderCircle, Pin, Stamp, X } from 'lucide-react'
import { api, go } from '../api.js'
import { Swatches } from '../components/Charts.jsx'
import { Notice, PinnedPost } from '../components/ui.jsx'

const DRAFT_KEY = 'vibe.draft'
function loadDraft() { try { return JSON.parse(sessionStorage.getItem(DRAFT_KEY)) || {} } catch { return {} } }

const TEXT = {
  plan: {
    title: 'Check my idea', max: 5, imgH: 'Inspiration images', imgHint: '(1–5)',
    imgSub: 'Screenshots, pins, other posters, or a rough sketch of your layout.',
    drop: 'Add inspiration images: click or drop files here', button: 'Check the vibe',
  },
  final: {
    title: 'Check my finished design', max: 1, imgH: 'Your finished design', imgHint: '(1 image, as you would post it)',
    imgSub: 'Export at full size. We check it against the team\'s style and run finish checks: legibility, text, resolution and shape.',
    drop: 'Add your finished design: click or drop a file here', button: 'Check my design',
  },
}

export default function CheckPage({ team, teamId, mode = 'plan', planId = null }) {
  const t = TEXT[mode]
  const [files, setFiles] = useState([])
  const [desc, setDesc] = useState(() => loadDraft().description || '')
  const [user, setUser] = useState(() => loadDraft().user || '')
  const [project, setProject] = useState(() => loadDraft().project || '')
  const [plans, setPlans] = useState([])
  const [plan, setPlan] = useState(planId || '')
  const [over, setOver] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const input = useRef()
  const [ref, setRef] = useState({ posts: [], palette: [] })

  useEffect(() => {
    if (!teamId || (team && !team.trained)) return
    let alive = true
    api.posts(teamId, 'team', 4).then(p => alive && setRef(r => ({ ...r, posts: p.items || [] }))).catch(() => {})
    api.profile(teamId).then(p => alive && setRef(r => ({ ...r, palette: (p.signature_palette || []).slice(0, 6) }))).catch(() => {})
    return () => { alive = false }
  }, [teamId, team?.trained])
  useEffect(() => { setFiles([]); setErr(''); setPlan(planId || '') }, [mode, planId])
  useEffect(() => {
    if (mode !== 'final' || !teamId) return
    api.checks(teamId).then(cs => setPlans(cs.filter(c => (c.kind || 'plan') === 'plan'))).catch(() => {})
  }, [mode, teamId])
  useEffect(() => { try { sessionStorage.setItem(DRAFT_KEY, JSON.stringify({ description: desc, user, project })) } catch {} }, [desc, user, project])
  const urls = useMemo(() => files.map(f => URL.createObjectURL(f)), [files])
  useEffect(() => () => urls.forEach(u => URL.revokeObjectURL(u)), [urls])

  const add = list => {
    const imgs = [...list].filter(f => f.type.startsWith('image/'))
    setFiles(prev => (t.max === 1 ? imgs.slice(0, 1) : [...prev, ...imgs].slice(0, t.max)))
  }
  const submit = async e => {
    e.preventDefault()
    setErr('')
    if (mode === 'final' && files.length !== 1) { setErr('Add your finished design (one image).'); return }
    if (mode === 'plan' && !files.length && !desc.trim()) { setErr('Add at least one inspiration image or describe your idea.'); return }
    setBusy(true)
    try {
      const r = await api.check(teamId, files, mode === 'plan' ? desc : '', user,
        { kind: mode, planCheckId: mode === 'final' && plan ? Number(plan) : null, project })
      go(`result/${r.id}`)
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  if (team && !team.trained) {
    return (
      <div>
        <div className="page-head"><div className="titles"><h1>{t.title}</h1></div></div>
        <Notice>{team.name} has no trained model yet. <a href="#/setup">Import the team's posts first.</a></Notice>
      </div>
    )
  }
  const pick = () => input.current.click()
  return (
    <form onSubmit={submit} noValidate>
      <div className="page-head">
        <div className="titles">
          <h1>{t.title.split(' ').slice(0, -1).join(' ')} <em>{t.title.split(' ').pop()}</em></h1>
          {mode === 'plan'
            ? <p className="lead">Before you design, pin what you plan to make. You get a score for <strong>{team?.name}</strong>, the reasons in words, and the team's closest past posts. Finished already? <a href="#/final">Check your design instead.</a></p>
            : <p className="lead">Done designing? Pin the final poster to check it against <strong>{team?.name}</strong>'s style and get a finish checklist before the seniors see it.</p>}
        </div>
      </div>

      <div className="check-layout">
      <div>
      <section aria-labelledby="inspo-h">
        <div className="row" style={{ justifyContent: 'space-between', marginBottom: 12 }}>
          <h2 id="inspo-h">{t.imgH} <span className="hint num">{files.length}/{t.max}</span></h2>
        </div>
        <div className={`board dropboard${over ? ' over' : ''}`}
          onDragOver={e => { e.preventDefault(); setOver(true) }} onDragLeave={() => setOver(false)}
          onDrop={e => { e.preventDefault(); setOver(false); add(e.dataTransfer.files) }}>
          {files.length === 0 ? (
            <button type="button" className="hint-big" onClick={pick} style={{ width: '100%', background: 'transparent', font: 'inherit' }} aria-label={t.drop}>
              <Pin aria-hidden="true" />
              <strong>{t.max === 1 ? 'Pin your design here' : 'Pin your inspiration here'}</strong>
              <span>{t.imgSub}</span>
              <span className="steps" aria-hidden="true">
                <span><b>1</b>Drop {t.max === 1 ? 'the image' : `up to ${t.max} images`} or click</span>
                <span><b>2</b>{mode === 'plan' ? 'Describe the plan' : 'Link your plan (optional)'}</span>
                <span><b>3</b>Get the verdict</span>
              </span>
            </button>
          ) : (
            <div className="pins">
              {files.map((f, i) => (
                <figure className="pinned" key={i} style={{ '--tilt': ['-1.4deg', '1.1deg', '-0.6deg', '1.5deg', '-1deg'][i % 5], '--pin-c': 'var(--pin)', margin: 0 }}>
                  <img src={urls[i]} alt={`${mode === 'final' ? 'Your design' : `Inspiration ${i + 1}`}: ${f.name}`} />
                  <button type="button" className="unpin" onClick={() => setFiles(files.filter((_, j) => j !== i))} aria-label={`Remove ${f.name}`}><X className="i" aria-hidden="true" /></button>
                </figure>
              ))}
              {files.length < t.max && (
                <button type="button" className="add-tile" onClick={pick} style={{ background: 'transparent', font: 'inherit', color: 'var(--on-felt-2)' }}>
                  <ImagePlus className="i" aria-hidden="true" />{t.max === 1 ? 'Replace' : 'Add another'}
                </button>
              )}
            </div>
          )}
        </div>
        <input ref={input} type="file" accept="image/*" multiple={t.max > 1} hidden onChange={e => { add(e.target.files); e.target.value = '' }} />
      </section>

      <section className="paper section-gap" aria-labelledby="desc-h">
        <h2 id="desc-h">{mode === 'plan' ? 'Describe your plan' : 'About this design'}</h2>
        <div className="body">
          {mode === 'plan' && (
            <div className="field">
              <label htmlFor="desc">Description <span className="hint">(colours, layout, fonts, photo or illustration)</span></label>
              <textarea id="desc" value={desc} onChange={e => setDesc(e.target.value)}
                placeholder="dark background, neon green code text, big bold title, robot illustration" />
            </div>
          )}
          {mode === 'final' && (
            <div className="field" style={{ maxWidth: 520 }}>
              <label htmlFor="plan">Compare with my plan <span className="hint">(optional)</span></label>
              <select id="plan" value={plan} onChange={e => setPlan(e.target.value)}>
                <option value="">No plan check</option>
                {plans.map(c => <option key={c.id} value={c.id}>#{c.id} · {Math.round(c.score)} · {(c.description || 'images only').slice(0, 50)}</option>)}
              </select>
            </div>
          )}
          <div className="fields">
            <div className="field">
              <label htmlFor="proj">Project <span className="hint">(optional)</span></label>
              <input id="proj" value={project} onChange={e => setProject(e.target.value)} placeholder="finlit-talk" />
            </div>
            <div className="field">
              <label htmlFor="who">Your name <span className="hint">(optional)</span></label>
              <input id="who" value={user} onChange={e => setUser(e.target.value)} />
            </div>
          </div>
          <p className="hint" style={{ marginTop: 10 }}>Use the same project name for every version of one brief: when the seniors decide, the model learns which version won.</p>
        </div>
      </section>

      {err && <div className="section-gap"><Notice kind="error">{err}</Notice></div>}
      <div className="submit-bar">
        <button className="primary big" type="submit" disabled={busy}>{busy ? <LoaderCircle className="i spin" aria-hidden="true" /> : <Stamp className="i" aria-hidden="true" />}{busy ? 'Checking…' : t.button}</button>
        {busy
          ? <span className="muted small" role="status">{mode === 'final' ? 'Reading your design and its text (up to ~10 seconds)…' : 'Reading your images (a few seconds)…'}</span>
          : <span className="muted small">{mode === 'final' ? 'Takes about ten seconds.' : 'Takes a few seconds.'}</span>}
      </div>
      </div>

      <aside className="ref-rail paper" aria-labelledby="ref-h">
        <h2 id="ref-h" style={{ fontSize: '1.3rem' }}>{team?.name?.replace(/\s*\(synthetic\)$/, '')} at a glance</h2>
        <p className="sub">What “on-brand” means here: the latest posts and the signature palette.</p>
        {ref.palette.length > 0 && <Swatches colors={ref.palette} label="Team signature palette" />}
        {ref.posts.length > 0 && (
          <div className="posts">
            {ref.posts.map((p, i) => <PinnedPost key={p.id} post={p} i={i} />)}
          </div>
        )}
        <p className="sub" style={{ marginTop: 18 }}><a href="#/profile">See the full team style</a></p>
      </aside>
      </div>
    </form>
  )
}
