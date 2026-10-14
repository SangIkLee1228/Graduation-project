import { clusterLabel } from '../lib/clusters.js'
import { bookingLinks } from '../lib/hotel.js'
import { Highlighted, Rating, Sid, Thumb, WarnBadge } from './common.jsx'

export default function HotelCard({ hotel, matched, onOpen, onBook }) {
  const booking = bookingLinks(hotel)[0]
  return (
    <article className="card">
      <button className="card-main" onClick={() => onOpen(hotel)}>
        <div className="card-cover">
          <Thumb hotel={hotel} size="lg" />
          <Sid sid={hotel.sid} />
        </div>
        <div className="card-body">
          <div className="card-tags">
            <span className="badge">{clusterLabel(hotel.sid[0])}</span>
            <WarnBadge hotel={hotel} />
          </div>
          <h3>{hotel.name}</h3>
          <Rating hotel={hotel} />
          {matched?.length > 0 && (
            <div className="matched">
              {matched.map((c) => <span key={c.label} className="chip chip-match">✓ {c.label}</span>)}
            </div>
          )}
          <p className="card-profile"><Highlighted text={hotel.profile} matched={matched} /></p>
        </div>
      </button>
      <div className="card-actions">
        <button className="btn btn-ghost" onClick={() => onOpen(hotel)}>상세 보기</button>
        <a className="btn btn-primary" href={booking.href} target="_blank" rel="noreferrer"
          onClick={() => onBook(hotel, booking.platform, 'card')}>
          예약 사이트로 이동 ↗
        </a>
      </div>
    </article>
  )
}
