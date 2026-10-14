import { useEffect, useRef, useState } from 'react'
import { track } from '../lib/analytics.js'
import { searchHotels } from '../lib/search.js'
import { Sid, Thumb } from './common.jsx'

const TOP_N = 3
const GREETING = {
  role: 'agent',
  text: '안녕하세요! 원하는 런던 숙소를 편하게 말로 설명해 주세요. 지역, 분위기, 예산 등을 함께 말해 주시면 더 잘 찾아요.',
}

// 데모 에이전트: 키워드 매칭으로 응답을 흉내 낸다. 모델 API가 생기면 reply()만 서버 호출로 바꾼다.
function reply(hotels, query) {
  const { concepts, results } = searchHotels(hotels, query)
  const top = results.slice(0, TOP_N)
  if (!top.length) {
    const known = concepts.length && concepts.some((c) => c.ko.length)
    return {
      role: 'agent',
      text: known
        ? '조건에 모두 맞는 호텔을 찾지 못했어요. 조건을 줄여서 다시 말씀해 주세요.'
        : '아직 이해하지 못한 표현이에요. 지역(하이드파크, 킹스크로스 등)이나 분위기(조용한, 가성비, 부티크 등)로 말씀해 주세요.',
    }
  }
  const labels = concepts.map((c) => c.label).join(', ')
  let text = `'${labels}' 조건에 맞는 호텔 ${results.length.toLocaleString()}곳 중, 조건이 가장 많이 맞고 평점·리뷰 수가 좋은 ${top.length}곳을 골랐어요.`
  if (top.some((r) => r.hotel.warn)) text += ' ⚠ 표시는 최근 1년 평점이 떨어진 곳이에요.'
  return { role: 'agent', text, query, picks: top }
}

export default function ChatWidget({ hotels, examples, onOpen, onShowAll }) {
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState([GREETING])
  const [input, setInput] = useState('')
  const [typing, setTyping] = useState(false)
  const endRef = useRef(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' })
  }, [messages, typing, open])

  const toggle = () => {
    if (!open) track('chat_opened')
    setOpen(!open)
  }

  const send = (text) => {
    const query = text.trim()
    if (!query || typing) return
    track('chat_message_sent', { query })
    setMessages((m) => [...m, { role: 'user', text: query }])
    setInput('')
    setTyping(true)
    setTimeout(() => {
      setMessages((m) => [...m, reply(hotels, query)])
      setTyping(false)
    }, 600)
  }

  const pick = (hotel, rank) => {
    track('chat_recommendation_clicked', { hotel_id: hotel.id, rank })
    onOpen(hotel, 'chat')
  }

  return (
    <div className="chat">
      {open && (
        <section className="chat-panel" aria-label="추천 에이전트">
          <header className="chat-head">
            <div>
              <strong>Talk to Book 에이전트</strong>
              <span className="badge badge-demo">데모</span>
            </div>
            <button className="chat-close" onClick={toggle} aria-label="닫기">×</button>
          </header>

          <div className="chat-body">
            {messages.map((m, i) => (
              <div key={i} className={`msg msg-${m.role}`}>
                <p>{m.text}</p>
                {m.picks?.map(({ hotel, matched }, rank) => (
                  <button key={hotel.id} className="pick" onClick={() => pick(hotel, rank + 1)}>
                    <Thumb hotel={hotel} size="sm" />
                    <span className="pick-info">
                      <span className="pick-name">{hotel.warn && '⚠ '}{hotel.name}</span>
                      <span className="muted">★ {hotel.rating.toFixed(1)} · <Sid sid={hotel.sid} /></span>
                      <span className="pick-matched">✓ {matched.map((c) => c.label).join(' · ')}</span>
                    </span>
                  </button>
                ))}
                {m.picks && (
                  <button className="link-btn" onClick={() => onShowAll(m.query)}>목록에서 전체 결과 보기 →</button>
                )}
              </div>
            ))}
            {messages.length === 1 && (
              <div className="chat-examples">
                {examples.map((ex) => <button key={ex} className="chip" onClick={() => send(ex)}>{ex}</button>)}
              </div>
            )}
            {typing && <div className="msg msg-agent typing"><span /><span /><span /></div>}
            <div ref={endRef} />
          </div>

          <form className="chat-input" onSubmit={(e) => { e.preventDefault(); send(input) }}>
            <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="예: 하이드파크 근처 조용한 호텔" />
            <button className="btn btn-primary" disabled={!input.trim() || typing}>전송</button>
          </form>
          <p className="chat-note">키워드 매칭으로 만든 데모 응답이에요. 추천 모델은 아직 연결되지 않았어요.</p>
        </section>
      )}
      <button className="chat-fab" onClick={toggle} aria-label={open ? '에이전트 닫기' : '에이전트에게 물어보기'}>
        {open ? '×' : '숙소 추천받기'}
      </button>
    </div>
  )
}
