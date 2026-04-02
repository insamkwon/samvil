# Web Recipes — Next.js 14 + Tailwind

## Layout (App Router)

```tsx
// app/layout.tsx
import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "App Name",
  description: "App description",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${inter.className} antialiased`}>{children}</body>
    </html>
  );
}
```

## Client Component

```tsx
// components/ComponentName.tsx
'use client'

import { useState } from 'react'

interface Props {
  // typed props
}

export function ComponentName({ ...props }: Props) {
  return <div>...</div>
}
```

**Rule:** Add `'use client'` to every component that uses hooks, event handlers, or browser APIs.

## Zustand Store with Persist

```tsx
// lib/store.ts
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface AppState {
  items: Item[]
  addItem: (item: Item) => void
  removeItem: (id: string) => void
}

export const useStore = create<AppState>()(
  persist(
    (set) => ({
      items: [],
      addItem: (item) => set((state) => ({
        items: [...state.items, item]
      })),
      removeItem: (id) => set((state) => ({
        items: state.items.filter(i => i.id !== id)
      })),
    }),
    { name: 'app-storage' }
  )
)
```

## localStorage (no Zustand)

```tsx
// lib/storage.ts
export function loadState<T>(key: string, fallback: T): T {
  if (typeof window === 'undefined') return fallback
  const saved = localStorage.getItem(key)
  return saved ? JSON.parse(saved) : fallback
}

export function saveState<T>(key: string, state: T): void {
  localStorage.setItem(key, JSON.stringify(state))
}
```

## Hydration-Safe Pattern

```tsx
'use client'
import { useState, useEffect } from 'react'

export function MyComponent() {
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  if (!mounted) return null  // or skeleton

  return <div>Client-only content</div>
}
```

**Why:** Next.js SSR renders on server first. If component reads localStorage or browser APIs during SSR, hydration mismatch occurs. The `mounted` pattern ensures client-only rendering.

## Drag and Drop

```tsx
// npm install @hello-pangea/dnd
import { DragDropContext, Droppable, Draggable, type DropResult } from '@hello-pangea/dnd'

// Must be inside 'use client' component
// Wrap board in DragDropContext
// Each column is a Droppable
// Each card is a Draggable
```

## Common Tailwind UI

```tsx
// Card
<div className="rounded-lg border bg-white p-4 shadow-sm">

// Button (primary)
<button className="rounded-md bg-blue-600 px-4 py-2 text-white hover:bg-blue-700">

// Button (secondary)
<button className="rounded-md border border-gray-300 px-4 py-2 hover:bg-gray-50">

// Input
<input className="w-full rounded-md border px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500" />

// Responsive grid
<div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">

// Center content
<main className="flex min-h-screen items-center justify-center">

// Empty state
{items.length === 0 && (
  <p className="text-center text-gray-500">No items yet. Add one above!</p>
)}
```

## Responsive Breakpoints

```
sm: 640px   — mobile landscape
md: 768px   — tablet
lg: 1024px  — desktop
xl: 1280px  — large desktop
```

Always use `md:` and `lg:` for layout changes. Mobile-first.
