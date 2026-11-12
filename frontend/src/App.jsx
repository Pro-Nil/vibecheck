import React, { useCallback, useEffect, useState } from 'react'
import { api } from './api.js'
import SetupPage from './pages/Setup.jsx'
import CheckPage from './pages/Check.jsx'
import ResultPage from './pages/Result.jsx'
import HistoryPage from './pages/History.jsx'
import ProfilePage from './pages/Profile.jsx'
import PluginsPage from './pages/Plugins.jsx'
import { BrandMark } from './components/ui.jsx'
import { Blocks, History, Lightbulb, Moon, Palette, Settings2, Stamp, Sun } from 'lucide-react'

const NAV = [
  ['check', 'Check my idea', Lightbulb],
  ['final', 'Check my design', Stamp],
  ['history', 'History', History],
  ['profile', 'Team style', Palette],
  ['setup', 'Team setup', Settings2],
  ['plugins', 'Plugins', Blocks],
]

function useHashRoute() {
  const read = () => (window.location.hash.replace(/^#\/?/, '') || 'check').split('/')
  const [route, setRoute] = useState(read)
  useEffect(() => {
    const on = () => { setRoute(read()); window.scrollTo(0, 0) }
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return route
}

function store(key, val) { try { if (val === undefined) return localStorage.getItem(key); localStorage.setItem(key, val) } catch { return null } }

export default function App() {
  const route = useHashRoute()
  const [teams, setTeams] = useState([])
  const [teamId, setTeamId] = useState(() => Number(store('vibe.team')) || null)
  const [theme, setTheme] = useState(() => store('vibe.theme') || '')

  const reloadTeams = useCallback(async () => {
    const t = await api.teams().catch(() => [])
    setTeams(t)
    if (t.length && !t.some(x => x.id === teamId)) setTeamId(t[0].id)
    return t
  }, [teamId])
  useEffect(() => { reloadTeams() }, [])
  useEffect(() => { if (teamId) store('vibe.team', String(teamId)) }, [teamId])
  useEffect(() => {
    if (theme) document.documentElement.dataset.theme = theme
    else delete document.documentElement.dataset.theme
    store('vibe.theme', theme)
  }, [theme])

  const isDark = theme ? theme === 'dark' : window.matchMedia?.('(prefers-color-scheme: dark)').matches
  const team = teams.find(t => t.id === teamId) || null
  const [page, arg] = route
  const props = { team, teams, teamId, setTeamId, reloadTeams }

  let body
  if (!teams.length && page !== 'setup' && page !== 'plugins') body = <SetupPage {...props} firstRun />
  else if (page === 'setup') body = <SetupPage {...props} />
  else if (page === 'result') body = <ResultPage {...props} checkId={Number(arg)} />
  else if (page === 'history') body = <HistoryPage {...props} />
  else if (page === 'profile') body = <ProfilePage {...props} />
  else if (page === 'plugins') body = <PluginsPage {...props} />
  else body = <CheckPage {...props} mode={page === 'final' ? 'final' : 'plan'} planId={page === 'final' && arg ? Number(arg) : null} />

  return (
    <>
      <a className="skip" href="#main" onClick={e => { e.preventDefault(); document.getElementById('main')?.focus() }}>Skip to content</a>
      <header className="top">
        <div className="top-inner">
          <a className="brand" href="#/check" aria-label="VibeCheck home">
            <BrandMark />
            VIBECHECK
          </a>
          <nav className="tabs" aria-label="Main">
            {NAV.map(([k, label, I]) => (
              <a key={k} href={`#/${k}`} aria-current={page === k ? 'page' : undefined}><I aria-hidden="true" />{label}</a>
            ))}
          </nav>
          <div className="top-right">
            {teams.length > 0 && (
              <>
                <label htmlFor="team-pick" className="sr-only">Team</label>
                <select id="team-pick" className="inline" value={teamId || ''} onChange={e => setTeamId(Number(e.target.value))}>
                  {teams.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
              </>
            )}
            <button className="icon-btn" onClick={() => setTheme(isDark ? 'light' : 'dark')} aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'} title={isDark ? 'Light mode' : 'Dark mode'}>
              {isDark ? <Sun className="i" aria-hidden="true" /> : <Moon className="i" aria-hidden="true" />}
            </button>
          </div>
        </div>
      </header>
      <main id="main" tabIndex={-1}>{body}</main>
    </>
  )
}
