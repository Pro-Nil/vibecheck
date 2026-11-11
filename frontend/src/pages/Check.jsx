import React, { useEffect, useMemo, useRef, useState } from 'react'
import { api, go } from '../api.js'

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
      <div className="stack">
        <h1>{t.title}</h1>
        <p className="alert">{team.name} has no trained model yet. <a href="#/setup">Import the team's posts first.</a></p>
      </div>
    )
  }
  return (
    <form className="stack" onSubmit={submit}>
      <h1>{t.title}</h1>
      {mode === 'plan'
        ? <p className="lead">Before you design, show what you plan to make. You'll get a vibe-match score for <strong>{team?.name}</strong>, the reasons, and the team's closest past posts. Finished already? <a href="#/final">Check your design instead.</a></p>
        : <p className="lead">Done designing? Check the final poster against <strong>{team?.name}</strong>'s style and get a finish checklist before you send it to the seniors.</p>}

      <section className="card" aria-labelledby="inspo-h">
        <h2 id="inspo-h">{t.imgH} <span className="hint">{t.imgHint}</span></h2>
        <p className="sub">{t.imgSub}</p>
        <div className={`drop${over ? ' over' : ''}`} role="button" tabIndex={0}
          onClick={() => input.current.click()}
          onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.current.click() } }}
          onDragOver={e => { e.preventDefault(); setOver(true) }} onDragLeave={() => setOver(false)}
          onDrop={e => { e.preventDefault(); setOver(false); add(e.dataTransfer.files) }}
          aria-label={t.drop}>
          <strong>Drop {t.max === 1 ? 'your design' : 'images'} here</strong> or click to choose · {files.length}/{t.max}
        </div>
        <input ref={input} type="file" accept="image/*" multiple={t.max > 1} hidden onChange={e => { add(e.target.files); e.target.value = '' }} />
        {files.length > 0 && (
          <div className="thumbs" style={{ marginTop: 12 }}>
            {files.map((f, i) => (
              <div className="thumb" key={i}>
                <img src={urls[i]} alt={`${mode === 'final' ? 'Your design' : `Inspiration ${i + 1}`}: ${f.name}`} />
                <button type="button" onClick={() => setFiles(files.filter((_, j) => j !== i))} aria-label={`Remove ${f.name}`}>✕</button>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="card" aria-labelledby="desc-h">
        <h2 id="desc-h">{mode === 'plan' ? 'Describe your plan' : 'About this design'}</h2>
        {mode === 'plan' && (
          <div className="field">
            <label htmlFor="desc" className="sr-only">Description</label>
            <textarea id="desc" value={desc} onChange={e => setDesc(e.target.value)}
              placeholder="dark background, neon green code text, big bold title, robot illustration" />
            <span className="hint">Colours, layout, fonts, photo or illustration — whatever you have in mind.</span>
          </div>
        )}
        {mode === 'final' && (
          <div className="field" style={{ maxWidth: 480 }}>
            <label htmlFor="plan">Compare with my plan <span className="hint">(optional)</span></label>
            <select id="plan" value={plan} onChange={e => setPlan(e.target.value)}>
              <option value="">No plan check</option>
              {plans.map(c => <option key={c.id} value={c.id}>#{c.id} · {Math.round(c.score)} · {(c.description || 'images only').slice(0, 50)}</option>)}
            </select>
          </div>
        )}
        <div className="row">
          <div className="field" style={{ maxWidth: 260 }}>
            <label htmlFor="proj">Project <span className="hint">(optional)</span></label>
            <input id="proj" value={project} onChange={e => setProject(e.target.value)} placeholder="finlit-talk" />
          </div>
          <div className="field" style={{ maxWidth: 260 }}>
            <label htmlFor="who">Your name <span className="hint">(optional)</span></label>
            <input id="who" value={user} onChange={e => setUser(e.target.value)} />
          </div>
        </div>
        <span className="hint">Same project name for every version of one brief: when the seniors decide, the model learns which version won.</span>
      </section>

      {err && <p className="alert error" role="alert">{err}</p>}
      <div className="row">
        <button className="primary" type="submit" disabled={busy}>{busy ? 'Checking…' : t.button}</button>
        {busy && <span className="muted small" role="status">{mode === 'final' ? 'Reading your design and its text (up to ~10 seconds)…' : 'Reading your images (a few seconds)…'}</span>}
      </div>
    </form>
  )
}
