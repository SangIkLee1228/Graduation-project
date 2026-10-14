import { popularity } from './hotel.js'

// 한국어 질의를 영어 호텔 프로파일과 맞추기 위한 데모용 키워드 사전.
// 실제 서비스에서는 "자연어 질의 → Semantic ID 생성 모델"로 대체한다.
// ko는 질의에서 공백을 지운 뒤 포함 여부로 찾고, en은 프로파일에서 단어 단위로 찾는다.
const CONCEPTS = [
  { label: '조용함', ko: ['조용', '한적'], en: ['quiet', 'peaceful', 'tranquil'] },
  { label: '가성비', ko: ['저렴', '가성비', '저가', '예산'], en: ['budget', 'affordable', 'value', 'cheap', 'inexpensive'] },
  { label: '고급', ko: ['고급', '럭셔리', '5성', '호화'], en: ['luxury', 'luxurious', 'elegant', 'upscale', 'opulent'] },
  { label: '청결', ko: ['깨끗', '청결', '깔끔'], en: ['clean', 'spotless', 'immaculate'] },
  { label: '친절', ko: ['친절', '서비스좋'], en: ['friendly', 'helpful', 'attentive', 'welcoming'] },
  { label: '넓은 객실', ko: ['넓', '큰방'], en: ['spacious', 'roomy'] },
  { label: '가족', ko: ['가족', '아이', '아기', '키즈'], en: ['family', 'families', 'children', 'kids'] },
  { label: '커플', ko: ['커플', '연인', '로맨틱', '신혼', '허니문'], en: ['romantic', 'couple', 'honeymoon'] },
  { label: '출장', ko: ['출장', '비즈니스', '업무'], en: ['business'] },
  { label: '조식', ko: ['조식', '아침'], en: ['breakfast'] },
  { label: '교통', ko: ['교통', '지하철', '튜브', '역근처', '역세권', '역가까'], en: ['station', 'tube', 'underground', 'transport'] },
  { label: '공항', ko: ['공항', '히드로'], en: ['airport', 'heathrow'] },
  { label: '중심가', ko: ['중심', '시내', '관광', '명소'], en: ['central', 'attractions', 'sightseeing'] },
  { label: '하이드파크', ko: ['하이드파크'], en: ['hyde park'] },
  { label: '킹스크로스', ko: ['킹스크로스', '판크라스'], en: ["king's cross", 'kings cross', 'st pancras'] },
  { label: '패딩턴', ko: ['패딩턴'], en: ['paddington'] },
  { label: '소호', ko: ['소호'], en: ['soho'] },
  { label: '코벤트가든', ko: ['코벤트가든'], en: ['covent garden'] },
  { label: '웨스트민스터', ko: ['웨스트민스터', '빅벤', '국회의사당'], en: ['westminster', 'big ben'] },
  { label: '대영박물관', ko: ['대영박물관', '블룸즈버리'], en: ['british museum', 'bloomsbury'] },
  { label: '옥스퍼드 스트리트', ko: ['옥스퍼드'], en: ['oxford street', 'oxford circus'] },
  { label: '피카딜리', ko: ['피카딜리'], en: ['piccadilly'] },
  { label: '켄싱턴', ko: ['켄싱턴'], en: ['kensington'] },
  { label: '타워브리지', ko: ['타워브리지', '런던탑'], en: ['tower bridge', 'tower of london'] },
  { label: '템스강', ko: ['템스', '강변'], en: ['thames', 'river', 'riverside'] },
  { label: '워털루', ko: ['워털루', '런던아이'], en: ['waterloo', 'london eye'] },
  { label: '빅토리아', ko: ['빅토리아'], en: ['victoria'] },
  { label: '쇼디치', ko: ['쇼디치'], en: ['shoreditch'] },
  { label: '그리니치', ko: ['그리니치'], en: ['greenwich'] },
  { label: '부티크', ko: ['부티크', '감성', '아늑'], en: ['boutique', 'charming', 'cozy', 'cosy'] },
  { label: '아파트·취사', ko: ['아파트', '레지던스', '취사', '주방', '장기'], en: ['apartment', 'kitchen', 'kitchenette', 'serviced'] },
  { label: '호스텔', ko: ['호스텔', '게스트하우스', '배낭'], en: ['hostel', 'backpacker', 'dorm'] },
  { label: '수영장·스파', ko: ['수영장', '스파'], en: ['pool', 'spa', 'swimming'] },
  { label: '피트니스', ko: ['헬스', '피트니스', '운동'], en: ['gym', 'fitness'] },
  { label: '바·펍', ko: ['펍', '칵테일', '술집', '루프탑'], en: ['bar', 'pub', 'cocktail', 'rooftop'] },
  { label: '레스토랑', ko: ['레스토랑', '식당', '맛집', '음식'], en: ['restaurant', 'dining', 'food'] },
  { label: '전망', ko: ['전망', '뷰', '경치', '야경'], en: ['view', 'skyline'] },
  { label: '와이파이', ko: ['와이파이', '인터넷'], en: ['wifi', 'wi-fi', 'internet'] },
  { label: '주차', ko: ['주차'], en: ['parking'] },
  { label: '반려동물', ko: ['반려', '강아지', '애견'], en: ['pet', 'dog'] },
  { label: '클래식', ko: ['역사', '클래식', '고풍', '전통'], en: ['historic', 'victorian', 'georgian', 'traditional'] },
  { label: '모던', ko: ['모던', '현대적', '신축', '세련'], en: ['modern', 'contemporary', 'stylish', 'renovated'] },
]

const STOPWORDS = new Set([
  'the', 'and', 'with', 'for', 'near', 'hotel', 'hotels', 'london', 'room', 'rooms', 'stay',
  'good', 'great', 'nice', 'best', 'want', 'looking', 'place', 'that', 'this', 'from',
])

const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const wordRe = (words, flags = 'i') => new RegExp(`\\b(${words.map(escapeRe).join('|')})(?:s|es)?\\b`, flags)

// 질의를 개념 목록으로 바꾼다. 영어 단어는 사전에 없으면 그대로 하나의 개념이 된다.
export function parseQuery(query) {
  const lower = query.toLowerCase()
  const compact = lower.replace(/\s+/g, '')
  const concepts = CONCEPTS.filter((c) => c.ko.some((k) => compact.includes(k)) || wordRe(c.en).test(lower))
  // 사전 개념(예: "hyde park")에 이미 포함된 영어 단어는 따로 개념으로 만들지 않는다.
  const covered = new Set(concepts.flatMap((c) => c.en.flatMap((phrase) => phrase.split(/\s+/))))
  for (const word of lower.match(/[a-z][a-z'-]{2,}/g) ?? []) {
    if (STOPWORDS.has(word) || covered.has(word)) continue
    covered.add(word)
    concepts.push({ label: word, ko: [], en: [word] })
  }
  return concepts.map((c) => ({ ...c, re: wordRe(c.en) }))
}

// 맞는 개념이 많은 순, 같으면 평점·리뷰 수(popularity) 순으로 정렬한다.
export function searchHotels(hotels, query) {
  const concepts = parseQuery(query)
  const results = []
  if (concepts.length) {
    for (const hotel of hotels) {
      const text = `${hotel.name} ${hotel.profile}`
      const matched = concepts.filter((c) => c.re.test(text))
      if (matched.length) results.push({ hotel, matched })
    }
  }
  results.sort((a, b) => b.matched.length - a.matched.length || popularity(b.hotel) - popularity(a.hotel))
  return { concepts, results }
}

// 프로파일에서 맞은 단어를 <mark>로 감쌀 수 있도록 [일반, 강조, 일반, ...] 조각으로 나눈다.
export function splitHighlights(text, matched) {
  if (!matched?.length) return [text]
  const re = new RegExp(`(\\b(?:${matched.flatMap((c) => c.en).map(escapeRe).join('|')})(?:s|es)?\\b)`, 'gi')
  return text.split(re)
}
