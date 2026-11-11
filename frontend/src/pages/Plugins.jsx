import React, { useEffect, useState } from 'react'
import { api, fmtDate } from '../api.js'

export default function PluginsPage({ teamId }) {
  const [list, setList] = useState([])
  const [form, setForm] = useState({ name: '', url: '', slot: 'result', author_team: '', description: '', onlyThis: false })
  const [err, setErr] = useState('')
  const load = () => api.plugins().then(setList).catch(e => setErr(e.message))
  useEffect(() => { load() }, [])

  const add = async e => {
    e.preventDefault()
    setErr('')
    try {
      const { onlyThis, ...body } = form
      await api.addPlugin({ ...body, team_id: onlyThis ? teamId : null })
      setForm({ ...form, name: '', url: '', description: '' })
      load()
    } catch (e) { setErr(e.message) }
  }
  const up = (k, v) => setForm({ ...form, [k]: v })

  return (
    <div className="stack">
      <h1>Plugins</h1>
      <p className="lead">
        Other teams extend VibeCheck with plugins. A plugin is a small web service: when a check finishes (or the style page opens),
        we send it the data and it answers with a panel that appears inside our pages.
        Full API: <a href="/docs" target="_blank" rel="noreferrer">interactive docs</a> · <a href="/openapi.json" target="_blank" rel="noreferrer">OpenAPI 3 spec</a> · <a href="/plugins/panel-example" target="_blank" rel="noreferrer">panel example</a>.
      </p>
      {err && <p className="alert error" role="alert">{err}</p>}

      <section className="card" aria-labelledby="inst-h">
        <h2 id="inst-h">Installed</h2>
        {!list.length ? <p className="muted">No plugins yet.</p> : (
          <table>
            <thead><tr><th scope="col">Name</th><th scope="col">Shows on</th><th scope="col">URL</th><th scope="col">Scope</th><th scope="col">On</th><th scope="col"><span className="sr-only">Remove</span></th></tr></thead>
            <tbody>
              {list.map(p => (
                <tr key={p.id}>
                  <td><strong>{p.name}</strong>{p.author_team && <div className="small muted">by {p.author_team}</div>}{p.description && <div className="small muted">{p.description}</div>}</td>
                  <td>{p.slot === 'result' ? 'Result page' : 'Team style'}</td>
                  <td className="small" style={{ wordBreak: 'break-all' }}>{p.url}</td>
                  <td className="small">{p.team_id ? `team ${p.team_id} only` : 'all teams'}<div className="muted">{fmtDate(p.created_at)}</div></td>
                  <td><input type="checkbox" aria-label={`Enable ${p.name}`} checked={p.enabled} style={{ width: 'auto' }}
                    onChange={async e => { await api.patchPlugin(p.id, { enabled: e.target.checked }); load() }} /></td>
                  <td><button className="link" onClick={async () => { await api.deletePlugin(p.id); load() }}>Remove</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <form className="card" onSubmit={add} aria-labelledby="add-h">
        <h2 id="add-h">Add a plugin</h2>
        <div className="grid cols-2">
          <div className="field"><label htmlFor="pn">Name</label><input id="pn" required value={form.name} onChange={e => up('name', e.target.value)} placeholder="Contrast checker" /></div>
          <div className="field"><label htmlFor="pu">Webhook URL</label><input id="pu" required type="url" value={form.url} onChange={e => up('url', e.target.value)} placeholder="http://localhost:8100/hook" /></div>
          <div className="field"><label htmlFor="ps">Shows on</label>
            <select id="ps" value={form.slot} onChange={e => up('slot', e.target.value)}><option value="result">Result page (after each check)</option><option value="profile">Team style page</option></select></div>
          <div className="field"><label htmlFor="pa">Built by (team)</label><input id="pa" value={form.author_team} onChange={e => up('author_team', e.target.value)} /></div>
        </div>
        <div className="field"><label htmlFor="pd">Description</label><input id="pd" value={form.description} onChange={e => up('description', e.target.value)} /></div>
        <div className="field row"><input id="po" type="checkbox" style={{ width: 'auto' }} checked={form.onlyThis} onChange={e => up('onlyThis', e.target.checked)} /><label htmlFor="po" style={{ margin: 0 }}>Only for the selected team</label></div>
        <button className="primary" type="submit">Add plugin</button>
      </form>
    </div>
  )
}
