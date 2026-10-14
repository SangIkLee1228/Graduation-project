import { useCallback, useEffect, useMemo, useState } from 'react'
import ChatWidget from './components/ChatWidget.jsx'
import HotelCard from './components/HotelCard.jsx'
import HotelModal from './components/HotelModal.jsx'
import { track } from './lib/analytics.js'
import { CATEGORIES, categoryOf } from './lib/clusters.js'
import { popularity } from './lib/hotel.js'
import { searchHotels } from './lib/search.js'

const EXAMPLES = ['하이드파크 근처 조용한 호텔', '킹스크로스 가성비 숙소', '가족 여행용 아파트호텔', '수영장 있는 고급 호텔']
const SORTS = {
  relevance: ['관련도순', null],
  recommended: ['추천순', (a, b) => popularity(b) - popularity(a)],
  rating: ['평점순', (a, b) => b.rating - a.rating || b.reviews - a.reviews],
  reviews: ['리뷰 많은순', (a, b) => b.reviews - a.reviews],
}
const PAGE = 24

export default function App() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [input, setInput] = useState('')
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('all')
  const [sort, setSort] = useState('recommended')
  const [limit, setLimit] = useState(PAGE)
  const [selected, setSelected] = useState(null)

  useEffect(() => {
    fetch('/data/hotels.json')
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then(setData)
      .catch((e) => setError(e.message))
  }, [])

  const search = useMemo(() => (data && query ? searchHotels(data.hotels, query) : null), [data, query])

  const base = useMemo(() => {
    if (!data) return []
    return search ? search.results : data.hotels.map((hotel) => ({ hotel, matched: [] }))
  }, [data, search])

  const counts = useMemo(() => {
    const c = { all: base.length }
    for (const { hotel } of base) c[categoryOf(hotel)] = (c[categoryOf(hotel)] ?? 0) + 1
    return c
  }, [base])

  const list = useMemo(() => {
    const items = category === 'all' ? base : base.filter(({ hotel }) => categoryOf(hotel) === category)
    const compare = SORTS[sort][1]
    return compare ? [...items].sort((a, b) => compare(a.hotel, b.hotel)) : items
  }, [base, category, sort])

  const runSearch = (text, source) => {
    const q = text.trim()
    setInput(q)
    setQuery(q)
    setSort(q ? 'relevance' : 'recommended')
    setCategory('all')
    setLimit(PAGE)
    if (q) track('search_submitted', { query: q, source, results: searchHotels(data.hotels, q).results.length })
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const openHotel = useCallback((hotel, source = 'list') => {
    track('hotel_opened', { hotel_id: hotel.id, source })
    setSelected(hotel)
  }, [])
  const closeHotel = useCallback(() => setSelected(null), [])
  const book = (hotel, platform, source) => track('booking_clicked', { hotel_id: hotel.id, platform, source })

  return (
    <>
      <header className="topbar">
        <div className="container topbar-inner">
          <button className="logo" onClick={() => runSearch('', 'logo')}>Talk to Book</button>
          <span className="muted">런던 호텔 추천 <span className="badge badge-demo">데모</span></span>
        </div>
      </header>

      <section className="hero">
        <div className="container">
          <h1>말로 찾는 런던 호텔</h1>
          <p className="hero-sub">TripAdvisor 리뷰 72만 건을 요약한 호텔 1,619곳 · Semantic ID 기반 추천</p>
          <form className="searchbar" onSubmit={(e) => { e.preventDefault(); runSearch(input, 'searchbar') }}>
            <input value={input} onChange={(e) => setInput(e.target.value)}
              placeholder="어떤 숙소를 찾으세요? 예: 하이드파크 근처 조용한 부티크 호텔" aria-label="호텔 검색" />
            <button className="btn btn-primary" disabled={!data}>검색</button>
          </form>
          <div className="examples">
            {EXAMPLES.map((ex) => (
              <button key={ex} className="chip chip-light" onClick={() => runSearch(ex, 'example')} disabled={!data}>{ex}</button>
            ))}
          </div>
        </div>
      </section>

      <main className="container">
        {error && <p className="notice">호텔 데이터를 불러오지 못했어요 ({error}). README의 데이터 생성 단계를 확인하세요.</p>}
        {!data && !error && <p className="notice">호텔 데이터를 불러오는 중…</p>}

        {data && (
          <>
            <div className="toolbar">
              <div>
                <h2 className="result-title">
                  {query ? <>'{query}' 검색 결과</> : '런던 인기 호텔'}
                  <span className="muted"> {list.length.toLocaleString()}곳</span>
                </h2>
                {search?.concepts.length > 0 && (
                  <div className="parsed">
                    해석된 조건 {search.concepts.map((c) => <span key={c.label} className="chip chip-match">{c.label}</span>)}
                    <button className="link-btn" onClick={() => runSearch('', 'clear')}>검색 초기화</button>
                  </div>
                )}
              </div>
              <select value={sort} onChange={(e) => setSort(e.target.value)} aria-label="정렬">
                {Object.entries(SORTS)
                  .filter(([key]) => key !== 'relevance' || query)
                  .map(([key, [label]]) => <option key={key} value={key}>{label}</option>)}
              </select>
            </div>

            <nav className="tabs" aria-label="Semantic ID 카테고리">
              {CATEGORIES.map(([key, label]) => (
                <button key={key} className={`tab ${category === key ? 'active' : ''}`} disabled={!counts[key]}
                  onClick={() => { setCategory(key); setLimit(PAGE); track('category_selected', { category: key }) }}>
                  {label} <span className="tab-count">{counts[key] ?? 0}</span>
                </button>
              ))}
            </nav>

            {list.length === 0 ? (
              <p className="notice">
                {search?.concepts.some((c) => c.ko.length)
                  ? '조건에 맞는 호텔이 없어요. 조건을 줄여 보세요.'
                  : '이해하지 못한 표현이에요. 지역(하이드파크, 킹스크로스)이나 분위기(조용한, 가성비)로 검색해 보세요.'}
              </p>
            ) : (
              <div className="grid">
                {list.slice(0, limit).map(({ hotel, matched }) => (
                  <HotelCard key={hotel.id} hotel={hotel} matched={matched} onOpen={openHotel} onBook={book} />
                ))}
              </div>
            )}
            {list.length > limit && (
              <div className="more">
                <button className="btn btn-ghost" onClick={() => setLimit(limit + PAGE)}>
                  더 보기 ({(list.length - limit).toLocaleString()}곳 남음)
                </button>
              </div>
            )}
          </>
        )}
      </main>

      <footer className="footer container muted small">
        데이터: HotelRec(TripAdvisor) 런던 g186338 · 프로파일: GPT-4o-mini 요약 · Semantic ID: K-means RQ [C1-C2-C3-C4]
        <br />평점은 원본 리뷰 전체 평균이며, 가격·사진 정보는 데이터셋에 없어 표시하지 않아요.
      </footer>

      {data && (
        <ChatWidget hotels={data.hotels} examples={EXAMPLES.slice(0, 3)} onOpen={openHotel}
          onShowAll={(q) => runSearch(q, 'chat')} />
      )}
      {selected && (
        <HotelModal hotel={selected} hotels={data.hotels} recentSince={data.meta.recent_since}
          onClose={closeHotel} onOpen={openHotel} onBook={book} />
      )}
    </>
  )
}
