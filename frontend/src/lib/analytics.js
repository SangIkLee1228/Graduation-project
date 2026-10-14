// 클릭률·전환률 측정용 이벤트 기록.
// 지금은 콘솔과 window.dataLayer(GA4 형식)에만 쌓는다. GA4나 Amplitude를 붙일 때 이 함수만 바꾼다.
export function track(event, params = {}) {
  window.dataLayer = window.dataLayer || []
  window.dataLayer.push({ event, ...params })
  console.info('[track]', event, params)
}
