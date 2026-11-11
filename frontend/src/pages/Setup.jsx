import React, { useEffect, useRef, useState } from 'react'
import { api, fmtDate, go } from '../api.js'
import { Progress } from '../components/Charts.jsx'

function NewTeamForm({ onCreated }) {
  const [name, setName] = useState('')
  const [handle, setHandle] = useState('')
  const [others, setOthers] = useState('')
  const [err, setErr] = useState('')
  const submit = async e => {
    e.preventDefault()
    setErr('')
    try {
      const t = await api.createTeam({ name, instagram_handle: handle || null, other_pages: others.split(/[\s,]+/).filter(Boolean) })
      onCreated(t)
    } catch (e) { setErr(e.message) }
  }
  return (
    <form className="card" onSubmit={submit} aria-labelledby="new-team-h">
      <h2 id="new-team-h">Add a design team</h2>
      <p className="sub">The app learns this team's style from its posts.</p>
      <div className="field"><label htmlFor="tn">Team name</label><input id="tn" required value={name} onChange={e => setName(e.target.value)} placeholder="Techkriti Design" /></div>
      <div className="field">
        <label htmlFor="th">Team Instagram page <span className="hint">(optional, without @)</span></label>
        <input id="th" value={handle} onChange={e => setHandle(e.target.value)} placeholder="techkriti.iitk" />
      </div>
      <div className="field">
        <label htmlFor="to">Other pages, "not our vibe" <span className="hint">(optional, separated by spaces or commas)</span></label>
        <input id="to" value={others} onChange={e => setOthers(e.target.value)} placeholder="antaragni.iitk moodi.iitb" />
      </div>
      {err && <p className="alert error" role="alert">{err}</p>}
      <button className="primary" type="submit">Create team</button>
    </form>
  )
}

function Jobs({ teamId, bump, onDone }) {
  const [jobs, setJobs] = useState([])
  const timer = useRef()
  useEffect(() => {
    let alive = true
    const tick = async () => {
      const j = await api.jobs(teamId).catch(() => [])
      if (!alive) return
      setJobs(prev => {
        if (prev.some(p => p.status === 'running' || p.status === 'queued') && !j.some(x => x.status === 'running' || x.status === 'queued')) onDone?.()
        return j
      })
      const busy = j.some(x => x.status === 'running' || x.status === 'queued')
      timer.current = setTimeout(tick, busy ? 1500 : 8000)
    }
    tick()
    return () => { alive = false; clearTimeout(timer.current) }
  }, [teamId, bump])
  if (!jobs.length) return <p className="muted small">No imports yet.</p>
  return (
    <ul className="reasons" aria-live="polite">
      {jobs.map(j => (
        <li key={j.id} style={{ display: 'block' }}>
          <div className="row" style={{ justifyContent: 'space-between' }}>
            <strong>{j.kind} #{j.id}</strong>
            <span className="small muted">{j.status} · {fmtDate(j.created_at)}</span>
          </div>
          {(j.status === 'running' || j.status === 'queued') && <Progress value={j.progress} label={`Job ${j.id} progress`} />}
          <p className="small muted" style={{ marginTop: 4 }}>{j.message}</p>
        </li>
      ))}
    </ul>
  )
}

export default function SetupPage({ team, teamId, setTeamId, reloadTeams, firstRun }) {
  const [info, setInfo] = useState(null)
  const [handle, setHandle] = useState('')
  const [others, setOthers] = useState('')
  const [maxPosts, setMaxPosts] = useState(300)
  const [maxOther, setMaxOther] = useState(60)
  const [since, setSince] = useState(`${new Date().getFullYear()}-01-01`)
  const [label, setLabel] = useState('team')
  const [project, setProject] = useState('')
  const [files, setFiles] = useState([])
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const [bump, setBump] = useState(0)
  const [preview, setPreview] = useState([])

  const load = async () => {
    if (!teamId) return
    const t = await api.team(teamId).catch(() => null)
    setInfo(t)
    if (t) { setHandle(t.instagram_handle || ''); setOthers(t.other_pages.join(' ')) }
    const p = await api.posts(teamId, 'team', 12).catch(() => ({ items: [] }))
    setPreview(p.items)
  }
  useEffect(() => { load() }, [teamId])

  const act = async fn => { setErr(''); setMsg(''); try { await fn() } catch (e) { setErr(e.message) } }
  const saveAndFetch = () => act(async () => {
    await api.patchTeam(teamId, { instagram_handle: handle, other_pages: others.split(/[\s,]+/).filter(Boolean) })
    await api.startImport(teamId, { fetch_instagram: true, max_posts: Number(maxPosts), max_posts_other: Number(maxOther), since: since || null })
    setMsg('Import started. Downloading can take several minutes per page.')
    setBump(b => b + 1)
  })
  const upload = () => act(async () => {
    if (!files.length) throw new Error('Choose some images first.')
    const r = await api.uploadMany(teamId, files, label, project)
    setMsg(`Uploaded ${r.added} images as "${label}". Features and retraining are running.`)
    setFiles([])
    setBump(b => b + 1)
  })
  const retrain = () => act(async () => { await api.retrain(teamId); setBump(b => b + 1); setMsg('Retraining started.') })

  if (firstRun || !team) {
    return (
      <div className="stack">
        <h1>Welcome to VibeCheck</h1>
        <p className="lead">Add your design team first. Then import its posts (from Instagram or by uploading images) so the app can learn its style.</p>
        <NewTeamForm onCreated={async t => { await reloadTeams(); setTeamId(t.id); go('setup') }} />
      </div>
    )
  }
  const c = info?.counts || {}
  return (
    <div className="stack">
      <h1>Team setup: {team.name}</h1>
      <p className="lead">Feed the model. The team's own posts teach it what "our vibe" looks like; posts from other pages and a few real rejected drafts teach it what doesn't fit.</p>
      {msg && <p className="alert" role="status">{msg}</p>}
      {err && <p className="alert error" role="alert">{err}</p>}

      <div className="tiles" aria-label="What the model has learned from">
        <div className="tile"><div className="v">{c.team || 0}</div><div className="l">team posts</div></div>
        <div className="tile"><div className="v">{c.other || 0}</div><div className="l">other pages' posts</div></div>
        <div className="tile"><div className="v">{c.rejected || 0}</div><div className="l">real rejected drafts</div></div>
        <div className="tile"><div className="v">{c.augmented || 0}</div><div className="l">near-misses (auto-made)</div></div>
      </div>

      <div className="grid cols-2">
        <section className="card" aria-labelledby="ig-h">
          <h2 id="ig-h">1 · Import from Instagram</h2>
          <p className="sub">Downloads public posts with Instaloader. Instagram may block this; if it does, use the upload box instead.</p>
          <div className="field"><label htmlFor="h2">Team page</label><input id="h2" value={handle} onChange={e => setHandle(e.target.value)} placeholder="techkriti.iitk" /></div>
          <div className="field"><label htmlFor="o2">Other pages</label><input id="o2" value={others} onChange={e => setOthers(e.target.value)} placeholder="antaragni.iitk moodi.iitb" /></div>
          <div className="grid cols-2" style={{ gap: 12 }}>
            <div className="field"><label htmlFor="mp">Team posts to fetch</label><input id="mp" type="number" min="10" max="5000" value={maxPosts} onChange={e => setMaxPosts(e.target.value)} /></div>
            <div className="field"><label htmlFor="mo">Posts per other page</label><input id="mo" type="number" min="0" max="5000" value={maxOther} onChange={e => setMaxOther(e.target.value)} /></div>
          </div>
          <div className="field"><label htmlFor="since">Only posts since <span className="hint">(older posts show an old style)</span></label><input id="since" type="date" value={since} onChange={e => setSince(e.target.value)} /></div>
          <p className="hint">About 7 posts a minute: Instaloader goes slowly so Instagram doesn't block it.</p>
          <button className="primary" onClick={saveAndFetch} disabled={!handle && !others}>Save and import</button>
        </section>

        <section className="card" aria-labelledby="up-h">
          <h2 id="up-h">2 · Or upload images</h2>
          <p className="sub">Select many files at once. Choose what they are first.</p>
          <div className="field">
            <label htmlFor="lab">These images are…</label>
            <select id="lab" value={label} onChange={e => setLabel(e.target.value)}>
              <option value="team">Our team's posts (approved)</option>
              <option value="other">Other pages' posts (not our vibe)</option>
              <option value="accepted">Designs the seniors accepted</option>
              <option value="rejected">Rejected drafts</option>
            </select>
          </div>
          {(label === 'accepted' || label === 'rejected') && (
            <div className="field">
              <label htmlFor="proj">Project <span className="hint">(the brief they were for, e.g. finlit-talk)</span></label>
              <input id="proj" value={project} onChange={e => setProject(e.target.value)} placeholder="finlit-talk" />
              <span className="hint">Accepted and rejected versions of the same brief teach the approval model which version wins.</span>
            </div>
          )}
          <div className="field">
            <label htmlFor="files">Images</label>
            <input id="files" type="file" accept="image/*" multiple onChange={e => setFiles([...e.target.files])} />
            <span className="hint">{files.length ? `${files.length} selected` : 'JPG, PNG or WebP'}</span>
          </div>
          <div className="row">
            <button className="primary" onClick={upload} disabled={!files.length}>Upload and retrain</button>
            <button onClick={retrain}>Retrain now</button>
          </div>
        </section>
      </div>

      <section className="card" aria-labelledby="jobs-h">
        <h2 id="jobs-h">Progress</h2>
        <Jobs teamId={teamId} bump={bump} onDone={() => { load(); reloadTeams() }} />
      </section>

      {preview.length > 0 && (
        <section className="card" aria-labelledby="pv-h">
          <h2 id="pv-h">Latest team posts</h2>
          <div className="posts">
            {preview.map(p => (
              <figure className="post" key={p.id} style={{ margin: 0 }}>
                <img src={p.image_url} alt={p.caption ? `Team post: ${p.caption.slice(0, 120)}` : 'Team post'} loading="lazy" />
                <figcaption className="meta">{fmtDate(p.posted_at)}{p.likes != null ? ` · ${p.likes} likes` : ''}</figcaption>
              </figure>
            ))}
          </div>
        </section>
      )}

      <details className="card">
        <summary><strong>Add another team</strong></summary>
        <div style={{ marginTop: 12 }}><NewTeamForm onCreated={async t => { await reloadTeams(); setTeamId(t.id) }} /></div>
      </details>
    </div>
  )
}
