import React, { useEffect, useState } from 'react'
import { Blocks, ExternalLink, Plus, Trash2 } from 'lucide-react'
import { api, fmtDate } from '../api.js'
import { Empty, Notice } from '../components/ui.jsx'

export default function PluginsPage({ teamId }) {
  const [list, setList] = useState(null)
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
  const run = fn => async (...a) => { setErr(''); try { await fn(...a); load() } catch (e) { setErr(e.message) } }

  return (
    <div>
      <div className="page-head">
        <div className="titles">
          <h1>Plugins</h1>
          <p className="lead">Other teams extend VibeCheck with plugins. A plugin is a small web service: when a check finishes (or the Team style page opens) we send it the data, and the panel it answers with appears inside our pages.</p>
        </div>
        <div className="actions">
          <a className="btn" href="/docs" target="_blank" rel="noreferrer"><ExternalLink className="i" aria-hidden="true" />API docs</a>
          <a className="btn" href="/plugins/panel-example" target="_blank" rel="noreferrer">Panel example</a>
        </div>
      </div>
      {err && <div style={{ marginBottom: 16 }}><Notice kind="error">{err}</Notice></div>}

      <section className="paper" aria-labelledby="inst-h">
        <h2 id="inst-h">Installed</h2>
        {list && !list.length && <Empty icon={Blocks} title="No plugins yet"><p>Add one below with its webhook URL.</p></Empty>}
        {list?.length > 0 && (
          <div className="table-wrap body">
            <table>
              <thead><tr><th scope="col">Plugin</th><th scope="col">Shows on</th><th scope="col">Webhook</th><th scope="col">Scope</th><th scope="col">On</th><th scope="col"><span className="sr-only">Remove</span></th></tr></thead>
              <tbody>
                {list.map(p => (
                  <tr key={p.id}>
                    <td><strong>{p.name}</strong>{p.author_team && <div className="small muted">by {p.author_team}</div>}{p.description && <div className="small muted">{p.description}</div>}</td>
                    <td>{p.slot === 'result' ? 'Result page' : 'Team style'}</td>
                    <td className="small" style={{ wordBreak: 'break-all' }}><code>{p.url}</code></td>
                    <td className="small">{p.team_id ? `Team ${p.team_id} only` : 'All teams'}<div className="muted">{fmtDate(p.created_at)}</div></td>
                    <td><input type="checkbox" aria-label={`Enable ${p.name}`} checked={p.enabled} onChange={e => run(api.patchPlugin)(p.id, { enabled: e.target.checked })} /></td>
                    <td><button className="link" onClick={() => run(api.deletePlugin)(p.id)} aria-label={`Remove ${p.name}`}><Trash2 className="i" aria-hidden="true" />Remove</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <form className="paper section-gap" onSubmit={add} aria-labelledby="add-h">
        <h2 id="add-h">Add a plugin</h2>
        <div className="body">
          <div className="fields">
            <div className="field"><label htmlFor="pn">Name</label><input id="pn" required value={form.name} onChange={e => up('name', e.target.value)} placeholder="Contrast checker" /></div>
            <div className="field"><label htmlFor="pu">Webhook URL</label><input id="pu" required type="url" value={form.url} onChange={e => up('url', e.target.value)} placeholder="http://localhost:8100/hook" /></div>
            <div className="field"><label htmlFor="ps">Shows on</label>
              <select id="ps" value={form.slot} onChange={e => up('slot', e.target.value)}><option value="result">Result page (after each check)</option><option value="profile">Team style page</option></select></div>
            <div className="field"><label htmlFor="pa">Built by (team)</label><input id="pa" value={form.author_team} onChange={e => up('author_team', e.target.value)} /></div>
          </div>
          <div className="field"><label htmlFor="pd">Description</label><input id="pd" value={form.description} onChange={e => up('description', e.target.value)} /></div>
          <div className="check-row"><input id="po" type="checkbox" checked={form.onlyThis} onChange={e => up('onlyThis', e.target.checked)} /><label htmlFor="po">Only for the selected team</label></div>
          <div className="field"><button className="primary" type="submit"><Plus className="i" aria-hidden="true" />Add plugin</button></div>
        </div>
      </form>
    </div>
  )
}
