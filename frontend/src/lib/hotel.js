const SKIP_WORDS = new Set(['the', 'hotel', 'london', 'by', 'at', 'and', '&', '-'])

export function initials(name) {
  const words = name.split(/\s+/).filter((w) => !SKIP_WORDS.has(w.toLowerCase()))
  return (words.length ? words : [name]).slice(0, 2).map((w) => w[0].toUpperCase()).join('')
}

// 리뷰 수가 적은 호텔의 평점이 과대평가되지 않도록 전체 평균 쪽으로 당긴 베이지안 평균
export function popularity(hotel) {
  const prior = 3.8
  const weight = 50
  return (hotel.rating * hotel.reviews + prior * weight) / (hotel.reviews + weight)
}

export function bookingLinks(hotel) {
  const query = encodeURIComponent(`${hotel.name} London`)
  return [
    { platform: 'tripadvisor', label: 'TripAdvisor', href: `https://www.tripadvisor.com/${hotel.url}` },
    { platform: 'booking', label: 'Booking.com', href: `https://www.booking.com/searchresults.html?ss=${query}` },
    { platform: 'google_maps', label: '지도', href: `https://www.google.com/maps/search/?api=1&query=${query}` },
  ]
}

// Semantic ID 앞 두 토큰(C1-C2)이 같은 호텔. 부족하면 C1만 같은 호텔로 채운다.
export function similarHotels(hotel, hotels, count = 4) {
  const others = hotels.filter((h) => h.id !== hotel.id && h.sid[0] === hotel.sid[0])
  const byPopularity = (a, b) => popularity(b) - popularity(a)
  const sameC2 = others.filter((h) => h.sid[1] === hotel.sid[1]).sort(byPopularity)
  const rest = others.filter((h) => h.sid[1] !== hotel.sid[1]).sort(byPopularity)
  return [...sameC2, ...rest].slice(0, count)
}
