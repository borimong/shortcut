// 랜딩 화면 캡처는 2배 해상도 원본과 휴대폰용 800px 판(small/)을 함께 둔다.
// 원본 주소로 작은 판을 찾아 srcset을 만들어 주면 브라우저가 화면 너비에 맞는 쪽을 받는다.
const full = import.meta.glob('./*.webp', { eager: true, import: 'default' })
const small = import.meta.glob('./small/*.webp', { eager: true, import: 'default' })

const smallByFull = Object.fromEntries(
  Object.entries(full)
    .filter(([path]) => small[path.replace('./', './small/')])
    .map(([path, url]) => [url, small[path.replace('./', './small/')]])
)

// naturalWidth는 원본의 실제 픽셀 너비다. 작은 판이 없으면(원본이 이미 작으면) 원본만 쓴다.
export function screenSrcset(src, naturalWidth) {
  const smallUrl = smallByFull[src]
  return smallUrl ? `${smallUrl} 800w, ${src} ${naturalWidth}w` : undefined
}
