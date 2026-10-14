import { clusterColor } from '../lib/clusters.js'
import { initials } from '../lib/hotel.js'
import { splitHighlights } from '../lib/search.js'

export function Thumb({ hotel, size = 'md' }) {
  return (
    <div className={`thumb thumb-${size}`} style={{ background: clusterColor(hotel.sid[0]) }} aria-hidden="true">
      {initials(hotel.name)}
    </div>
  )
}

export function Rating({ hotel }) {
  return (
    <span className="rating">
      <span className="star">★</span> {hotel.rating.toFixed(1)}
      <span className="muted"> · 리뷰 {hotel.reviews.toLocaleString()}</span>
    </span>
  )
}

export function Sid({ sid }) {
  return <code className="sid" title="Semantic ID [C1, C2, C3, C4]">{sid.join('-')}</code>
}

export function WarnBadge({ hotel }) {
  if (!hotel.warn) return null
  return <span className="badge badge-warn" title="최근 1년 평균 평점이 전체 평균보다 0.5점 이상 낮음">최근 평점 하락</span>
}

export function Highlighted({ text, matched }) {
  return splitHighlights(text, matched).map((part, i) => (i % 2 ? <mark key={i}>{part}</mark> : part))
}
