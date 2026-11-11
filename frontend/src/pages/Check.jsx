import React, { useEffect, useMemo, useRef, useState } from 'react'
import { api, go } from '../api.js'

const DRAFT_KEY = 'vibe.draft'
function loadDraft() { try { return JSON.parse(sessionStorage.getItem(DRAFT_KEY)) || {} } catch { return {} } }

export default function CheckPage({ team, teamId }) {
  const [files, setFiles] = useState([])
  const [desc, setDesc] = useState(() => loadDraft().description || '')
  const [user, setUser] = useState(() => loadDraft().user || '')
  const [over, setOver] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const input = useRef()

  useEffect(() => { try { sessionStorage.setItem(DRAFT_KEY, JSON.stringify({ description: desc, user })) } catch {} }, [desc, user])
  const urls = useMemo(() => files.map(f => URL.createObjectURL(f)), [files])
  useEffect(() => () => urls.forEach(u => URL.revokeObjectURL(u)), [urls])

  const add = list => {
    const imgs = [...list].filter(f => f.type.startsWith('image/'))
    setFiles(prev => [...prev, ...imgs].slice(0, 5))
  }
  const submit = async e => {
    e.preventDefault()
    setErr('')
    if (!files.length && !desc.trim()) { setErr('Add at least one inspiration image or describe your idea.'); return }
    setBusy(true)
    try {
      const r = await api.check(teamId, files, desc, user)
      go(`result/${r.id}`)
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  if (team && !team.trained) {
    return (
      <div className="stack">
        <h1>Check my idea</h1>
        <p className="alert">{team.name} has no trained model yet. <a href="#/setup">Import the team's posts first.</a></p>
      </div>
    )
  }
  return (
    <form className="stack" onSubmit={submit}>
      <h1>Check my idea</h1>
      <p className="lead">Before you design, show what you plan to make. You'll get a vibe-match score for <strong>{team?.name}</strong>, the reasons, and the team's closest past posts.</p>

      <section className="card" aria-labelledby="inspo-h">
        <h2 id="inspo-h">Inspiration images <span className="hint">(1–5)</span></h2>
        <p className="sub">Screenshots, pins, other posters, or a rough sketch of your layout.</p>
        <div className={`drop${over ? ' over' : ''}`} role="button" tabIndex={0}
          onClick={() => input.current.click()}
          onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.current.click() } }}
          onDragOver={e => { e.preventDefault(); setOver(true) }} onDragLeave={() => setOver(false)}
          onDrop={e => { e.preventDefault(); setOver(false); add(e.dataTransfer.files) }}
          aria-label="Add inspiration images: click or drop files here">
          <strong>Drop images here</strong> or click to choose · {files.length}/5
        </div>
        <input ref={input} type="file" accept="image/*" multiple hidden onChange={e => { add(e.target.files); e.target.value = '' }} />
        {files.length > 0 && (
          <div className="thumbs" style={{ marginTop: 12 }}>
            {files.map((f, i) => (
              <div className="thumb" key={i}>
                <img src={urls[i]} alt={`Inspiration ${i + 1}: ${f.name}`} />
                <button type="button" onClick={() => setFiles(files.filter((_, j) => j !== i))} aria-label={`Remove ${f.name}`}>✕</button>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="card" aria-labelledby="desc-h">
        <h2 id="desc-h">Describe your plan</h2>
        <div className="field">
          <label htmlFor="desc" className="sr-only">Description</label>
          <textarea id="desc" value={desc} onChange={e => setDesc(e.target.value)}
            placeholder="dark background, neon green code text, big bold title, robot illustration" />
          <span className="hint">Colours, layout, fonts, photo or illustration — whatever you have in mind.</span>
        </div>
        <div className="field" style={{ maxWidth: 320 }}>
          <label htmlFor="who">Your name <span className="hint">(optional)</span></label>
          <input id="who" value={user} onChange={e => setUser(e.target.value)} />
        </div>
      </section>

      {err && <p className="alert error" role="alert">{err}</p>}
      <div className="row">
        <button className="primary" type="submit" disabled={busy}>{busy ? 'Checking…' : 'Check the vibe'}</button>
        {busy && <span className="muted small" role="status">Reading your images (a few seconds)…</span>}
      </div>
    </form>
  )
}
