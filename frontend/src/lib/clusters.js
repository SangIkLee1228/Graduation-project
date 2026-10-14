// K-means Semantic ID 첫 토큰(C1)의 의미. 중간보고서 1의 C1 클러스터 분석 결과를 따른다.
const GROUPS = {
  boutique: { label: '부티크·B&B', codes: [11] },
  upper: { label: '중상급·펍 호텔', codes: [13, 15] },
  apart: { label: '아파트호텔', codes: [4] },
  suburban: { label: '교외 체인', codes: [8] },
  budget: { label: '저가·호스텔', codes: [6, 9, 12] },
}

export const CATEGORIES = [
  ['all', '전체'],
  ...Object.entries(GROUPS).map(([key, group]) => [key, group.label]),
  ['other', '기타'],
]

export function categoryOf(hotel) {
  return Object.keys(GROUPS).find((key) => GROUPS[key].codes.includes(hotel.sid[0])) ?? 'other'
}

export function clusterLabel(c1) {
  return Object.values(GROUPS).find((group) => group.codes.includes(c1))?.label ?? `클러스터 ${c1}`
}

export function clusterColor(c1) {
  return `hsl(${Math.round(c1 * 22.5)} 55% 45%)`
}
