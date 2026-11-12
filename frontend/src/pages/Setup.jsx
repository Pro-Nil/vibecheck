import React, { useEffect, useRef, useState } from 'react'
import { ChevronRight, Download, RefreshCw, Upload } from 'lucide-react'
import { api, fmtDate, go } from '../api.js'
import { Progress } from '../components/Charts.jsx'
import { Mark, Notice, PinnedPost } from '../components/ui.jsx'

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
    <form onSubmit={submit} aria-labelledby="new-team-h">
      <h2 id="new-team-h">Add a design team</h2>
      <p className="sub">VibeCheck learns this team's style from its own posts.</p>
      <div className="body">
        <div className="field"><label htmlFor="tn">Team name</label><input id="tn" required value={name} onChange={e => setName(e.target.value)} placeholder="Techkriti Design" /></div>
        <div className="fields">
          <div className="field"><label htmlFor="th">Team Instagram page <span className="hint">(optional, without @)</span></label>
            <input id="th" value={handle} onChange={e => setHandle(e.target.value)} placeholder="techkriti.iitk" /></div>
          <div className="field"><label htmlFor="to">Other pages, “not our vibe” <span className="hint">(optional)</span></label>
            <input id="to" value={others} onChange={e => setOthers(e.target.value)} placeholder="antaragni.iitk moodi.iitb" /></div>
        </div>
        {err && <div className="field"><Notice kind="error">{err}</Notice></div>}
        <div className="field"><button className="primary" type="submit">Create team</button></div>
      </div>
    </form>
  )
}

const STATUS = { done: ['ok', 'finished'], error: ['bad', 'failed'], running: ['info', 'running'], queued: ['info', 'queued'] }
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
  if (!jobs.length) return <p className="sub">No imports or training runs yet.</p>
  return (
    <ul className="reasons" aria-live="polite">
      {jobs.map(j => {
        const [k, l] = STATUS[j.status] || ['info', j.status]
        return (
          <li key={j.id}>
            <Mark kind={k} label={l} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <strong>{j.kind} <span className="num">#{j.id}</span></strong>
                <span className="small muted">{l} · {fmtDate(j.created_at)}</span>
              </div>
              {(j.status === 'running' || j.status === 'queued') && <div style={{ margin: '8px 0' }}><Progress value={j.progress} label={`Job ${j.id} progress`} /></div>}
              <p className="small muted" style={{ marginTop: 4 }}>{j.message}</p>
            </div>
          </li>
        )
      })}
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
    setMsg(`Uploaded ${r.added} images as “${label}”. Features and retraining are running.`)
    setFiles([])
    setBump(b => b + 1)
  })
  const retrain = () => act(async () => { await api.retrain(teamId); setBump(b => b + 1); setMsg('Retraining started.') })

  if (firstRun || !team) {
    return (
      <div>
        <div className="page-head"><div className="titles">
          <h1>Welcome to <em>VibeCheck</em></h1>
          <p className="lead">Add your design team, then import its posts (from Instagram or by uploading images) so the app can learn its style.</p>
        </div></div>
        <section className="paper" style={{ maxWidth: 760 }}>
          <NewTeamForm onCreated={async t => { await reloadTeams(); setTeamId(t.id); go('setup') }} />
        </section>
      </div>
    )
  }
  const c = info?.counts || {}
  return (
    <div>
      <div className="page-head">
        <div className="titles">
          <h1>Team setup: <em>{team.name}</em></h1>
          <p className="lead">The team's own posts teach the model what “our vibe” looks like; other pages' posts and real rejected drafts teach it what doesn't fit.</p>
        </div>
        <div className="actions"><button onClick={retrain}><RefreshCw className="i" aria-hidden="true" />Retrain now</button></div>
      </div>
      {msg && <div style={{ marginBottom: 16 }}><Notice kind="ok">{msg}</Notice></div>}
      {err && <div style={{ marginBottom: 16 }}><Notice kind="error">{err}</Notice></div>}

      <section className="board" aria-labelledby="have-h">
        <p className="board-label" id="have-h">What the model learns from</p>
        <div className="counts">
          <div><b>{c.team || 0}</b><span>team posts</span></div>
          <div><b>{c.other || 0}</b><span>other pages' posts</span></div>
          <div><b>{c.rejected || 0}</b><span>rejected drafts</span></div>
          <div><b>{c.augmented || 0}</b><span>near-misses (made automatically)</span></div>
        </div>
        {preview.length > 0 && (
          <div className="posts" style={{ marginTop: 26, gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))' }}>
            {preview.slice(0, 8).map((p, i) => <PinnedPost key={p.id} post={p} i={i} />)}
          </div>
        )}
      </section>

      <div className="grid cols-2 section-gap">
        <section className="paper" aria-labelledby="ig-h">
          <h2 id="ig-h">Import from Instagram</h2>
          <p className="sub">Downloads public posts with Instaloader, about 7 a minute so Instagram doesn't block it. If it does, upload images instead.</p>
          <div className="body">
            <div className="fields">
              <div className="field"><label htmlFor="h2">Team page</label><input id="h2" value={handle} onChange={e => setHandle(e.target.value)} placeholder="techkriti.iitk" /></div>
              <div className="field"><label htmlFor="o2">Other pages</label><input id="o2" value={others} onChange={e => setOthers(e.target.value)} placeholder="antaragni.iitk moodi.iitb" /></div>
              <div className="field"><label htmlFor="mp">Team posts to fetch</label><input id="mp" type="number" min="10" max="5000" value={maxPosts} onChange={e => setMaxPosts(e.target.value)} /></div>
              <div className="field"><label htmlFor="mo">Posts per other page</label><input id="mo" type="number" min="0" max="5000" value={maxOther} onChange={e => setMaxOther(e.target.value)} /></div>
            </div>
            <div className="field"><label htmlFor="since">Only posts since <span className="hint">(older posts show an old style)</span></label><input id="since" type="date" value={since} onChange={e => setSince(e.target.value)} /></div>
            <div className="field"><button className="primary" onClick={saveAndFetch} disabled={!handle && !others}><Download className="i" aria-hidden="true" />Save and import</button></div>
          </div>
        </section>

        <section className="paper" aria-labelledby="up-h">
          <h2 id="up-h">Upload images</h2>
          <p className="sub">Select many files at once, and say what they are first.</p>
          <div className="body">
            <div className="field">
              <label htmlFor="lab">These images are</label>
              <select id="lab" value={label} onChange={e => setLabel(e.target.value)}>
                <option value="team">Our team's posts (approved)</option>
                <option value="other">Other pages' posts (not our vibe)</option>
                <option value="accepted">Designs the seniors accepted</option>
                <option value="rejected">Rejected drafts</option>
              </select>
            </div>
            {(label === 'accepted' || label === 'rejected') && (
              <div className="field">
                <label htmlFor="proj">Project <span className="hint">(the brief they were for)</span></label>
                <input id="proj" value={project} onChange={e => setProject(e.target.value)} placeholder="finlit-talk" />
                <p className="hint" style={{ marginTop: 6 }}>Accepted and rejected versions of the same brief teach the approval model which version wins.</p>
              </div>
            )}
            <div className="field">
              <label htmlFor="files">Images</label>
              <input id="files" type="file" accept="image/*" multiple onChange={e => setFiles([...e.target.files])} />
              <p className="hint num" style={{ marginTop: 6 }}>{files.length ? `${files.length} selected` : 'JPG, PNG or WebP'}</p>
            </div>
            <div className="field"><button className="primary" onClick={upload} disabled={!files.length}><Upload className="i" aria-hidden="true" />Upload and retrain</button></div>
          </div>
        </section>
      </div>

      <section className="paper section-gap" aria-labelledby="jobs-h">
        <h2 id="jobs-h">Imports and training</h2>
        <Jobs teamId={teamId} bump={bump} onDone={() => { load(); reloadTeams() }} />
      </section>

      <details className="paper section-gap">
        <summary><ChevronRight className="i" aria-hidden="true" />Add another team</summary>
        <div style={{ marginTop: 16 }}><NewTeamForm onCreated={async t => { await reloadTeams(); setTeamId(t.id) }} /></div>
      </details>
    </div>
  )
}
