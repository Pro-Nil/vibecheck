import React, { useEffect, useState } from 'react'
import { ClipboardList } from 'lucide-react'
import { api, fmtDate } from '../api.js'
import { Empty, Loading, Notice, Stamp, VerdictChip } from '../components/ui.jsx'

const OUT = { approved: 'Approved', rejected: 'Rejected', posted: 'Posted' }

export default function HistoryPage({ teamId, team }) {
  const [rows, setRows] = useState(null)
  const [err, setErr] = useState('')
  const load = () => api.checks(teamId).then(setRows).catch(e => setErr(e.message))
  useEffect(() => { if (teamId) load() }, [teamId])

  const set = async (id, result) => {
    try { await api.outcome(id, result); load() } catch (e) { setErr(e.message) }
  }
  const decided = rows ? rows.filter(r => r.outcome).length : 0
  return (
    <div>
      <div className="page-head">
        <div className="titles">
          <h1>History</h1>
          <p className="lead">Every check for {team?.name}. Record what the seniors decided: those decisions are how the approval model learns. Nothing is deleted; decided work keeps its stamp.</p>
        </div>
      </div>
      {rows?.length > 0 && (
        <div className="summary-row" aria-label="Summary">
          <div><b>{rows.length}</b><span>checks</span></div>
          <div><b>{rows.filter(r => r.verdict_level === 'approve').length}</b><span>scored on-brand</span></div>
          <div><b>{decided}</b><span>decided by seniors</span></div>
          <div><b>{rows.filter(r => r.outcome === 'approved' || r.outcome === 'posted').length}</b><span>approved or posted</span></div>
        </div>
      )}
      {err && <Notice kind="error">{err}</Notice>}
      {!rows && !err && <Loading />}
      {rows && !rows.length && (
        <section className="paper">
          <Empty icon={ClipboardList} title="No checks yet">
            <p>Pin an idea or a finished design to get the first verdict. <a href="#/check">Check an idea</a> or <a href="#/final">check a design</a>.</p>
          </Empty>
        </section>
      )}
      {rows?.length > 0 && (
        <section className="paper table-wrap" style={{ padding: '6px 18px' }}>
          <table>
            <caption className="sr-only">Past checks</caption>
            <thead><tr><th scope="col">Work</th><th scope="col">What</th><th scope="col">Score</th><th scope="col">Verdict</th><th scope="col">Seniors decided</th><th scope="col">Date</th></tr></thead>
            <tbody>
              {rows.map(c => (
                <tr key={c.id}>
                  <td>
                    <a href={`#/result/${c.id}`} aria-label={`Open check ${c.id}`} className="thumbs-mini" style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                      {c.inspo_urls.slice(0, 3).map(u => <img key={u} src={u} alt="" />)}
                      {!c.inspo_urls.length && <span className="num">#{c.id}</span>}
                    </a>
                  </td>
                  <td style={{ maxWidth: 340 }}>
                    <div className="kind">{(c.kind || 'plan') === 'final' ? 'Design' : 'Idea'} #{c.id}{c.project ? ` · ${c.project}` : ''}</div>
                    <a href={`#/result/${c.id}`}>{c.description ? c.description.slice(0, 90) : (c.kind === 'final' ? 'Finished design' : 'Images only')}</a>
                    {c.user && <div className="small muted">by {c.user}</div>}
                  </td>
                  <td className="score"><b>{Math.round(c.score)}</b></td>
                  <td><VerdictChip level={c.verdict_level}>{c.verdict}</VerdictChip></td>
                  <td>
                    <div className="row" style={{ gap: 12 }}>
                      <label className="sr-only" htmlFor={`o${c.id}`}>Seniors' decision on check {c.id}</label>
                      <select id={`o${c.id}`} value={c.outcome || ''} onChange={e => e.target.value && set(c.id, e.target.value)}>
                        <option value="">Not yet</option><option value="approved">Approved</option><option value="rejected">Rejected</option><option value="posted">Posted</option>
                      </select>
                      {c.outcome && <Stamp small text={OUT[c.outcome]} />}
                    </div>
                  </td>
                  <td className="small muted num" style={{ whiteSpace: 'nowrap' }}>{fmtDate(c.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  )
}
