# Design Presets

> 앱 유형별 비주얼 테마. scaffold에서 shadcn/ui 테마 변수에 적용.

## productivity (할일, 칸반, 대시보드, 프로젝트 관리)

```
색상:
  background: slate-50 (#f8fafc)
  foreground: slate-900 (#0f172a)
  primary: blue-600 (#2563eb)
  secondary: slate-100 (#f1f5f9)
  accent: blue-50 (#eff6ff)
  danger: red-500 (#ef4444)
  muted: slate-500 (#64748b)

레이아웃: 좌측 사이드바 (240px) + 메인 콘텐츠
border-radius: rounded-lg (8px)
shadow: shadow-sm
특징: 깔끔, 밀도 높음, 정보 중심
```

## creative (블로그, 포트폴리오, 미디어)

```
색상:
  background: gray-950 (#030712)
  foreground: gray-50 (#f9fafb)
  primary: violet-500 (#8b5cf6)
  secondary: gray-800 (#1f2937)
  accent: violet-950 (#2e1065)
  danger: rose-500 (#f43f5e)
  muted: gray-400 (#9ca3af)

레이아웃: 중앙 정렬, max-w-4xl, 넓은 여백
border-radius: rounded-xl (12px)
shadow: shadow-lg
특징: 다크 모드, 강한 콘트라스트, 이미지 중심
```

## minimal (랜딩, 유틸리티, 계산기)

```
색상:
  background: white (#ffffff)
  foreground: gray-900 (#111827)
  primary: gray-900 (#111827)
  secondary: gray-100 (#f3f4f6)
  accent: gray-50 (#f9fafb)
  danger: red-600 (#dc2626)
  muted: gray-500 (#6b7280)

레이아웃: 중앙 단일 컬럼, max-w-2xl
border-radius: rounded-md (6px)
shadow: shadow-none 또는 shadow-sm
특징: 텍스트 중심, 장식 최소화, 여백 넉넉
```

## playful (게임, 소셜, 교육, 퀴즈)

```
색상:
  background: indigo-50 (#eef2ff)
  foreground: indigo-900 (#312e81)
  primary: indigo-600 (#4f46e5)
  secondary: amber-100 (#fef3c7)
  accent: amber-400 (#fbbf24)
  danger: rose-500 (#f43f5e)
  muted: indigo-400 (#818cf8)

레이아웃: 카드 기반, 중앙 정렬
border-radius: rounded-2xl (16px)
shadow: shadow-md
특징: 큰 글씨, 둥근 모서리, 밝은 색, 인터랙티브
```

## shadcn/ui 테마 적용 방법

scaffold에서 `npx shadcn@latest init` 후, `app/globals.css`의 CSS 변수를 프리셋에 맞게 설정:

```css
@layer base {
  :root {
    --background: <preset.background>;
    --foreground: <preset.foreground>;
    --primary: <preset.primary>;
    --secondary: <preset.secondary>;
    --accent: <preset.accent>;
    --destructive: <preset.danger>;
    --muted: <preset.muted>;
    --radius: <preset.border-radius>;
  }
}
```
