import { format, formatDistanceToNowStrict, isValid } from 'date-fns'

const toDate = (value) => {
  if (!value) return null
  const d = new Date(value)
  return isValid(d) ? d : null
}

/** "3 hours ago" — or '' for missing/invalid dates (never throws). */
export function timeAgo(value) {
  const d = toDate(value)
  return d ? formatDistanceToNowStrict(d, { addSuffix: true }) : ''
}

/** "Sep 27, 2026 · 14:05" */
export function dateline(value) {
  const d = toDate(value)
  return d ? format(d, "MMM d, yyyy '·' HH:mm") : ''
}

/** Masthead date: "Sunday, September 27, 2026" */
export const editionDate = (d = new Date()) => format(d, 'EEEE, MMMM d, yyyy')

/** Volume/issue numbers derived from the date so every day reads as a new edition. */
export function editionNumber(d = new Date()) {
  const start = new Date(d.getFullYear(), 0, 0)
  const day = Math.floor((d - start) / 86400000)
  return { vol: d.getFullYear() - 2025, no: day }
}

export const capitalize = (s = '') => s.charAt(0).toUpperCase() + s.slice(1)

/** Split long AI text into paragraphs for column layout. */
export const paragraphs = (text) =>
  (text || '').split(/\n\s*\n|\n/).map(p => p.trim()).filter(Boolean)
