import { useEffect } from 'react'
import { clusterLabel } from '../lib/clusters.js'
import { bookingLinks, similarHotels } from '../lib/hotel.js'
import { Rating, Sid, Thumb, WarnBadge } from './common.jsx'

// 중간보고서 1의 레벨별 분석 결과
const SID_LEVELS = [
  ['C1', '숙소 유형·품질'],
  ['C2', '서비스 세부 특성'],
  ['C3', '세부 뉘앙스'],
  ['C4', '중복 구분 번호'],
]

export default function HotelModal({ hotel, hotels, recentSince, onClose, onOpen, onBook }) {
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const similar = similarHotels(hotel, hotels)

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={hotel.name} onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose} aria-label="닫기">×</button>

        <header className="modal-head">
          <Thumb hotel={hotel} size="xl" />
          <div>
            <div className="card-tags">
              <span className="badge">{clusterLabel(hotel.sid[0])}</span>
              <WarnBadge hotel={hotel} />
            </div>
            <h2>{hotel.name}</h2>
            <Rating hotel={hotel} />
          </div>
        </header>

        <div className="booking-row">
          {bookingLinks(hotel).map((link, i) => (
            <a key={link.platform} className={`btn ${i === 0 ? 'btn-primary' : 'btn-ghost'}`} href={link.href}
              target="_blank" rel="noreferrer" onClick={() => onBook(hotel, link.platform, 'detail')}>
              {link.label} ↗
            </a>
          ))}
        </div>

        <section>
          <h4>리뷰 요약 프로파일</h4>
          <p>{hotel.profile}</p>
        </section>

        <section>
          <h4>최근 평점 추세</h4>
          {hotel.recent ? (
            <div className={`trend ${hotel.warn ? 'trend-warn' : ''}`}>
              <div>
                최근 1년({recentSince} 이후) <strong>★ {hotel.recent.avg.toFixed(2)}</strong>
                <span className="muted"> · 리뷰 {hotel.recent.count}개</span>
              </div>
              <div className="muted">전체 기간 ★ {hotel.rating.toFixed(2)}</div>
              {hotel.warn && <p>최근 리뷰 평점이 전체 평균보다 0.5점 이상 낮아요. 예약 전에 최근 리뷰를 확인하세요.</p>}
            </div>
          ) : (
            <p className="muted">최근 1년 리뷰가 5개 미만이라 추세를 표시하지 않아요.</p>
          )}
        </section>

        <section>
          <h4>Semantic ID <Sid sid={hotel.sid} /></h4>
          <dl className="sid-levels">
            {SID_LEVELS.map(([level, meaning], i) => (
              <div key={level}>
                <dt>{level} = {hotel.sid[i]}</dt>
                <dd>{i === 0 ? `${meaning} · ${clusterLabel(hotel.sid[0])}` : meaning}</dd>
              </div>
            ))}
          </dl>
          <p className="muted small note">C1 유형 이름은 클러스터 전체의 평균적인 경향이라 개별 호텔과 다를 수 있어요.</p>
        </section>

        <section>
          <h4>리뷰 샘플</h4>
          <p className="muted small">프로파일 생성에 쓰인 리뷰 중 최신 {hotel.samples.length}개</p>
          {hotel.samples.map((r) => (
            <blockquote key={r.date + r.title} className="review">
              <div><strong>★ {r.rating}</strong> {r.title} <span className="muted">· {r.date}</span></div>
              <p>{r.text}</p>
            </blockquote>
          ))}
        </section>

        {similar.length > 0 && (
          <section>
            <h4>비슷한 호텔</h4>
            <p className="muted small">Semantic ID 앞자리가 같은 호텔</p>
            <ul className="similar">
              {similar.map((h) => (
                <li key={h.id}>
                  <button onClick={() => onOpen(h, 'similar')}>
                    <Thumb hotel={h} size="sm" />
                    <span className="similar-name">{h.name}</span>
                    <Sid sid={h.sid} />
                    <span className="muted">★ {h.rating.toFixed(1)}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </div>
  )
}
