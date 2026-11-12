import React from 'react'
import { AlertTriangle, Check, CircleAlert, Heart, Info, LoaderCircle, X } from 'lucide-react'
import { fmtShort, pct } from '../api.js'

const VERDICT_ICON = { approve: Check, borderline: AlertTriangle, reject: X }

/** Verdict as a filled chip: icon + words, never colour alone. */
export function VerdictChip({ level, children }) {
  const I = VERDICT_ICON[level] || Info
  return <span className={`chip ${level || ''}`}><I className="i" aria-hidden="true" />{children}</span>
}

const MARK = { ok: [Check, 'fits'], bad: [X, 'off'], warn: [AlertTriangle, 'worth a look'], info: [Info, 'note'] }
export function Mark({ kind = 'info', label }) {
  const [I, l] = MARK[kind] || MARK.info
  return <span className={`mark ${kind}`} role="img" aria-label={label || l}><I aria-hidden="true" /></span>
}

/** The rubber stamp. `press` animates it once (skipped with reduced motion). */
export function Stamp({ text, sub, press = false, small = false }) {
  return (
    <span className={`stamp${small ? ' sm' : ''}${press ? ' press' : ''}`} aria-hidden={small ? undefined : 'true'}>
      {text}{sub && !small && <small>{sub}</small>}
    </span>
  )
}

const TILTS = ['1.3deg', '-0.9deg', '0.6deg', '-1.2deg', '0.9deg', '-0.5deg']
/** A team post pinned to the board with fixed nameplate furniture: match, date, likes. */
export function PinnedPost({ post, i = 0, href, match }) {
  const Tag = href ? 'a' : 'figure'
  return (
    <Tag className="pinned" style={{ '--tilt': TILTS[i % TILTS.length], margin: 0 }} href={href}>
      <img src={post.image_url} loading="lazy" alt={post.caption ? `Team post: ${post.caption.slice(0, 100)}` : 'Team post'} />
      <div className="nameplate">
        {match != null ? <strong className="num">{pct(match)}%</strong> : <strong className="num">{fmtShort(post.posted_at)}</strong>}
        <span className="num">
          {match != null && fmtShort(post.posted_at)}
          {post.likes != null && <><Heart aria-label="likes" /> {post.likes}</>}
        </span>
      </div>
    </Tag>
  )
}

export function Notice({ kind = '', children, role }) {
  const I = kind === 'error' ? CircleAlert : kind === 'ok' ? Check : Info
  return <div className={`notice ${kind}`} role={role || (kind === 'error' ? 'alert' : 'status')}><I className="i" aria-hidden="true" /><div>{children}</div></div>
}

export function Loading({ children = 'Loading…' }) {
  return <p className="loading" role="status"><LoaderCircle className="i spin" aria-hidden="true" />{children}</p>
}

export function Empty({ icon: I = Info, title, children }) {
  return <div className="empty"><I aria-hidden="true" /><h2>{title}</h2><div>{children}</div></div>
}

export function PageHead({ title, meta, lead, actions }) {
  return (
    <div className="page-head">
      <div className="titles">
        <h1>{title}</h1>
        {meta && <p className="meta">{meta}</p>}
        {lead && <p className="lead">{lead}</p>}
      </div>
      {actions && <div className="actions">{actions}</div>}
    </div>
  )
}

/** The brand mark: a stamped tick. */
export function BrandMark() {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true">
      <defs><linearGradient id="bm" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#f2493b" /><stop offset="1" stopColor="#c4261a" /></linearGradient></defs>
      <rect x="1" y="1" width="30" height="30" rx="9" fill="url(#bm)" />
      <rect x="1.5" y="1.5" width="29" height="29" rx="8.5" fill="none" stroke="rgba(255,255,255,.28)" />
      <path d="M9.5 16.5l4.5 4.5 8.5-10" stroke="#fff" strokeWidth="3.2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
