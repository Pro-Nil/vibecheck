// Thin wrapper over the VibeCheck REST API (same origin; Vite proxies in dev).
async function req(method, path, body, isForm = false) {
  const opts = { method, headers: {} }
  if (body !== undefined) {
    if (isForm) opts.body = body
    else { opts.body = JSON.stringify(body); opts.headers['Content-Type'] = 'application/json' }
  }
  const r = await fetch(path, opts)
  if (r.status === 204) return null
  const text = await r.text()
  let data
  try { data = text ? JSON.parse(text) : null } catch { data = text }
  if (!r.ok) {
    const msg = data && data.detail ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)) : `HTTP ${r.status}`
    throw new Error(msg)
  }
  return data
}

export const api = {
  teams: () => req('GET', '/teams'),
  team: id => req('GET', `/teams/${id}`),
  createTeam: body => req('POST', '/teams', body),
  patchTeam: (id, body) => req('PATCH', `/teams/${id}`, body),
  startImport: (id, body) => req('POST', `/teams/${id}/import`, body),
  uploadMany: (id, files, label, project = '') => {
    const f = new FormData()
    files.forEach(x => f.append('files', x))
    f.append('label', label)
    f.append('project', project)
    f.append('train', 'true')
    return req('POST', `/teams/${id}/import/upload`, f, true)
  },
  job: id => req('GET', `/jobs/${id}`),
  jobs: id => req('GET', `/teams/${id}/jobs?limit=5`),
  retrain: id => req('POST', `/teams/${id}/retrain`),
  model: id => req('GET', `/teams/${id}/model`),
  profile: id => req('GET', `/teams/${id}/style-profile`),
  posts: (id, label, limit = 24) => req('GET', `/teams/${id}/posts?label=${label}&limit=${limit}`),
  post: id => req('GET', `/posts/${id}`),
  check: (id, files, description, user, { kind = 'plan', planCheckId = null, project = '' } = {}) => {
    const f = new FormData()
    files.forEach(x => f.append('images', x))
    f.append('description', description)
    f.append('user', user || '')
    f.append('kind', kind)
    f.append('project', project || '')
    if (planCheckId) f.append('plan_check_id', String(planCheckId))
    return req('POST', `/teams/${id}/checks`, f, true)
  },
  getCheck: id => req('GET', `/checks/${id}`),
  checks: id => req('GET', `/teams/${id}/checks`),
  outcome: (checkId, result, file) => {
    const f = new FormData()
    f.append('result', result)
    if (file) f.append('final_image', file)
    return req('POST', `/checks/${checkId}/outcome`, f, true)
  },
  plugins: teamId => req('GET', `/plugins${teamId ? `?team_id=${teamId}` : ''}`),
  addPlugin: body => req('POST', '/plugins', body),
  patchPlugin: (id, body) => req('PATCH', `/plugins/${id}`, body),
  deletePlugin: id => req('DELETE', `/plugins/${id}`),
}

// Okabe–Ito colour-blind-safe palette. Meaning is never carried by colour alone.
// Verdict colours (approve/borderline/reject) are reserved for verdicts and check states.
export const C = {
  team: '#0072B2', other: '#CC79A7', rejected: '#D55E00', plan: '#009E73', ink2: '#7b8a83',
  approve: '#009E73', borderline: '#E69F00', reject: '#D55E00', grey: '#8a8f98', stamp: '#5B3E96',
}
export const go = path => { window.location.hash = '#/' + path }
export const pct = v => Math.round(v * 100)
export const fmtShort = s => (s ? new Date(s).toLocaleDateString(undefined, { day: 'numeric', month: 'short' }) : '—')
export const fmtDate = s => (s ? new Date(s).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : '—')
