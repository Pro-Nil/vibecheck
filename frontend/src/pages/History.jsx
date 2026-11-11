import React, { useEffect, useState } from 'react'
import { api, fmtDate, LEVEL } from '../api.js'

export default function HistoryPage({ teamId, team }) {
  const [rows, setRows] = useState(null)
  const [err, setErr] = useState('')
  const load = () => api.checks(teamId).then(setRows).catch(e => setErr(e.message))
  useEffect(() => { if (teamId) load() }, [teamId])

  const set = async (id, result) => {
    try { await api.outcome(id, result); load() } catch (e) { setErr(e.message) }
  }
  if (err) return <p className="alert error" role="alert">{err}</p>
  if (!rows) return <p className="muted" role="status">Loading…</p>
  return (
    <div className="stack">
      <h1>History</h1>
      <p className="lead">Every idea checked for {team?.name}. Mark what the seniors decided: those answers are how the model learns real approvals and rejections over time.</p>
      {!rows.length ? <p className="alert">No checks yet. <a href="#/check">Check your first idea.</a></p> : (
        <div className="card" style={{ overflowX: 'auto' }}>
          <table>
            <caption className="sr-only">Past vibe checks</caption>
            <thead><tr><th scope="col">Inspiration</th><th scope="col">Idea</th><th scope="col">Score</th><th scope="col">Verdict</th><th scope="col">Seniors decided</th><th scope="col">Date</th></tr></thead>
            <tbody>
              {rows.map(c => {
                const lv = LEVEL[c.verdict_level]
                return (
                  <tr key={c.id}>
                    <td>
                      <a href={`#/result/${c.id}`} aria-label={`Open check ${c.id}`} style={{ display: 'flex', gap: 4 }}>
                        {c.inspo_urls.slice(0, 3).map(u => <img key={u} src={u} alt="" width="40" height="50" style={{ objectFit: 'cover', borderRadius: 6 }} />)}
                        {!c.inspo_urls.length && <span>#{c.id}</span>}
                      </a>
                    </td>
                    <td style={{ maxWidth: 320 }}><a href={`#/result/${c.id}`}>{c.description ? c.description.slice(0, 90) : `Check #${c.id}`}</a>{c.user && <div className="small muted">by {c.user}</div>}</td>
                    <td><strong>{Math.round(c.score)}</strong></td>
                    <td><span className="pill" style={{ color: lv.color }}><span aria-hidden="true">{lv.icon}</span>{c.verdict}</span></td>
                    <td>
                      <label className="sr-only" htmlFor={`o${c.id}`}>Outcome of check {c.id}</label>
                      <select id={`o${c.id}`} className="inline" value={c.outcome || ''} onChange={e => e.target.value && set(c.id, e.target.value)}>
                        <option value="">not yet</option><option value="approved">approved</option><option value="rejected">rejected</option><option value="posted">posted</option>
                      </select>
                    </td>
                    <td className="small muted">{fmtDate(c.created_at)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
