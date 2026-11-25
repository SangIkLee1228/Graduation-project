import { useEffect, useRef, useState } from 'react'
import { track } from '../lib/analytics.js'
import { Sid, Thumb } from './common.jsx'

const GREETING = {
  role: 'agent',
  text: '어떤 런던 숙소를 찾으세요? 원하는 지역, 분위기, 숙소 유형이나 편의시설을 말해 주세요.',
}

const ERROR_MESSAGES = {
  conversation_expired: '대화가 만료됐어요. 새 대화를 시작해 주세요.',
  conversation_conflict: '대화가 업데이트되는 중이에요. 다시 시도해 주세요.',
  llm_not_configured: '추천 서비스를 사용하려면 서버에 Luxia API 키를 설정해 주세요.',
  llm_unavailable: '조건을 해석하지 못했어요. 다시 시도해 주세요.',
  conversation_store_unavailable: '대화를 저장할 수 없어요. 잠시 후 다시 시도해 주세요.',
}

function ChatPick({ hotel, onOpen, onBook }) {
  return (
    <article className="chat-pick">
      <button className="pick" onClick={onOpen}>
        <Thumb hotel={hotel} size="sm" />
        <span className="pick-info">
          <span className="pick-name">{hotel.name}</span>
          <span className="muted">★ {hotel.rating.toFixed(1)} · <Sid sid={hotel.sid} /></span>
        </span>
      </button>
      <p className="pick-reason">{hotel.reason}</p>
      <div className="pick-links">
        {hotel.booking_links.map((link) => (
          <a key={link.platform} href={link.href} target="_blank" rel="noreferrer"
            onClick={() => onBook(link.platform)}>{link.label}</a>
        ))}
      </div>
    </article>
  )
}

export default function ChatWidget({ examples, onOpen, onBook }) {
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState([GREETING])
  const [input, setInput] = useState('')
  const [conversation, setConversation] = useState(null)
  const [preferences, setPreferences] = useState([])
  const [typing, setTyping] = useState(false)
  const [failure, setFailure] = useState(null)
  const inFlight = useRef(false)
  const endRef = useRef(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' })
  }, [messages, typing, failure, open])

  const toggle = () => {
    if (!open) track('chat_opened')
    setOpen(!open)
  }

  const reset = () => {
    if (inFlight.current) return
    setMessages([GREETING])
    setPreferences([])
    setConversation(null)
    setInput('')
    setFailure(null)
  }

  const submit = async (body) => {
    inFlight.current = true
    setFailure(null)
    setTyping(true)
    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await response.json()
      if (!response.ok) {
        setFailure({ code: data.detail, body })
        return
      }
      setConversation(data.conversation_id)
      setPreferences(data.preferences)
      setMessages((current) => [...current, {
        role: 'agent', text: data.reply, picks: data.recommendations,
      }])
    } catch {
      setFailure({ body })
    } finally {
      setTyping(false)
      inFlight.current = false
    }
  }

  const send = (text) => {
    const message = text.trim()
    if (!message || inFlight.current || failure) return
    track('chat_message_sent')
    setMessages((current) => [...current, { role: 'user', text: message }])
    setInput('')
    void submit({ message, request_id: crypto.randomUUID(), conversation_id: conversation })
  }

  const pick = (hotel, rank) => {
    track('chat_recommendation_clicked', { hotel_id: hotel.id, rank })
    onOpen(hotel.id)
  }

  return (
    <div className="chat">
      {open && (
        <section className="chat-panel" aria-label="추천 에이전트">
          <header className="chat-head">
            <strong>Talk to Book 에이전트</strong>
            <div className="chat-head-actions">
              <button className="chat-reset" onClick={reset} disabled={typing}>새 대화</button>
              <button className="chat-close" onClick={toggle} aria-label="닫기">×</button>
            </div>
          </header>

          {preferences.length > 0 && (
            <div className="chat-preferences" aria-label="적용 중인 조건">
              <span>적용 중인 조건</span>
              {preferences.map(({ label, mode }) => (
                <span className="chip chip-match" key={label}>
                  {mode === 'excluded' ? '제외 · ' : mode === 'required' ? '필수 · ' : ''}{label}
                </span>
              ))}
            </div>
          )}

          <div className="chat-body" role="log" aria-label="대화">
            {messages.map((message, index) => (
              <div key={index} className={`msg msg-${message.role}`}>
                <p>{message.text}</p>
                {message.picks?.map((hotel, rank) => (
                  <ChatPick key={hotel.id} hotel={hotel} onOpen={() => pick(hotel, rank + 1)}
                    onBook={(platform) => onBook(hotel, platform, 'chat')} />
                ))}
              </div>
            ))}
            {messages.length === 1 && (
              <div className="chat-examples">
                {examples.map((example) => (
                  <button key={example} className="chip" onClick={() => send(example)}>{example}</button>
                ))}
              </div>
            )}
            {typing && <p className="msg msg-agent" role="status">조건을 확인하고 있어요…</p>}
            {failure && (
              <div className="msg msg-agent">
                <p role="alert">{ERROR_MESSAGES[failure.code] ?? '응답을 받지 못했어요. 다시 시도해 주세요.'}</p>
                {failure.code !== 'conversation_expired' && (
                  <button className="btn btn-ghost" onClick={() => {
                    if (!inFlight.current) void submit(failure.body)
                  }}>다시 시도</button>
                )}
              </div>
            )}
            <div ref={endRef} />
          </div>

          <form className="chat-input" onSubmit={(event) => { event.preventDefault(); send(input) }}>
            <input value={input} onChange={(event) => setInput(event.target.value)} maxLength={1000}
              aria-label="숙소 추천 메시지" placeholder="예: 조용한 곳으로 바꿔줘" disabled={typing || Boolean(failure)} />
            <button className="btn btn-primary" disabled={!input.trim() || typing || Boolean(failure)}>전송</button>
          </form>
          <p className="chat-note">과거 리뷰를 사용합니다. 요금과 예약 가능 여부는 예약 사이트에서 확인하세요.</p>
        </section>
      )}
      <button className="chat-fab" onClick={toggle} aria-expanded={open}
        aria-label={open ? '에이전트 닫기' : '숙소 추천받기'}>
        {open ? '×' : '숙소 추천받기'}
      </button>
    </div>
  )
}
