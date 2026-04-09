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

## Server Component with Data Fetching

```tsx
// app/page.tsx — Server Component (default, no 'use client')
// No useState, no useEffect, no browser APIs

interface PageProps {
  searchParams?: { q?: string }
}

export default async function Page({ searchParams }: PageProps) {
  const query = searchParams?.q || ''
  // Fetch in server — no loading spinner needed
  const res = await fetch(`https://api.example.com/items?q=${query}`, {
    next: { revalidate: 60 } // ISR: revalidate every 60s
  })
  const items = await res.json()

  return (
    <main>
      {items.map((item: { id: string; name: string }) => (
        <div key={item.id}>{item.name}</div>
      ))}
    </main>
  )
}
```

**Rule:** Default to Server Components. Only add `'use client'` when you need hooks, event handlers, or browser APIs.

## Error Boundary (error.tsx)

```tsx
// app/error.tsx — MUST be 'use client'
'use client'

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  return (
    <div className="flex min-h-[50vh] flex-col items-center justify-center gap-4">
      <h2 className="text-xl font-semibold text-red-600">Something went wrong</h2>
      <p className="text-gray-500">{error.message || 'An unexpected error occurred'}</p>
      <button
        onClick={reset}
        className="rounded-md bg-blue-600 px-4 py-2 text-white hover:bg-blue-700"
      >
        Try again
      </button>
    </div>
  )
}
```

**Rule:** Every route segment can have its own `error.tsx`. Always provide user-friendly message + retry action. Never expose raw error objects.

## Loading State (loading.tsx)

```tsx
// app/loading.tsx — Automatic Suspense boundary
export default function Loading() {
  return (
    <div className="flex min-h-[50vh] items-center justify-center">
      <div className="flex flex-col items-center gap-3">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-gray-200 border-t-blue-600" />
        <p className="text-sm text-gray-500">Loading...</p>
      </div>
    </div>
  )
}

// Skeleton variant for lists
export function ListSkeleton({ count = 3 }: { count?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="h-16 animate-pulse rounded-lg bg-gray-100" />
      ))}
    </div>
  )
}
```

**Rule:** Add `loading.tsx` to any route that fetches data. Use skeleton for lists, spinner for single items.

## Form Handling with Server Action

```tsx
// app/actions.ts — Server Actions
'use server'

import { revalidatePath } from 'next/cache'

export async function createItem(formData: FormData) {
  const title = formData.get('title') as string
  if (!title || title.trim().length === 0) {
    return { error: 'Title is required' }
  }
  // Save to DB or API
  revalidatePath('/') // Refresh cache
  return { success: true }
}

// components/CreateForm.tsx
'use client'

import { useFormState, useFormStatus } from 'react-dom'
import { createItem } from '@/app/actions'

function SubmitButton() {
  const { pending } = useFormStatus()
  return (
    <button
      type="submit"
      disabled={pending}
      className="rounded-md bg-blue-600 px-4 py-2 text-white hover:bg-blue-700 disabled:opacity-50"
    >
      {pending ? 'Creating...' : 'Create'}
    </button>
  )
}

export function CreateForm() {
  const [state, formAction] = useFormState(createItem, null)

  return (
    <form action={formAction} className="space-y-3">
      <input
        name="title"
        type="text"
        placeholder="Enter title..."
        className="w-full rounded-md border px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
        required
      />
      {state?.error && <p className="text-sm text-red-600">{state.error}</p>}
      {state?.success && <p className="text-sm text-green-600">Created!</p>}
      <SubmitButton />
    </form>
  )
}
```

**Rule:** Use Server Actions for mutations (create, update, delete). Use `useFormState` for error handling. Use `useFormStatus` for pending state.

## Dark Mode Toggle

```tsx
// components/ThemeToggle.tsx
'use client'

import { useEffect, useState } from 'react'

export function ThemeToggle() {
  const [dark, setDark] = useState(false)

  useEffect(() => {
    const saved = localStorage.getItem('theme')
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
    const isDark = saved === 'dark' || (!saved && prefersDark)
    setDark(isDark)
    document.documentElement.classList.toggle('dark', isDark)
  }, [])

  const toggle = () => {
    const next = !dark
    setDark(next)
    document.documentElement.classList.toggle('dark', next)
    localStorage.setItem('theme', next ? 'dark' : 'light')
  }

  return (
    <button
      onClick={toggle}
      className="rounded-md p-2 hover:bg-gray-100 dark:hover:bg-gray-800"
      aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
    >
      {dark ? '☀️' : '🌙'}
    </button>
  )
}
```

**Prerequisite:** Scaffold의 `globals.css`에 `@layer base`에서 `.dark` CSS 변수가 정의되어 있어야 함.
**Rule:** Toggle은 localStorage에 저장. 시스템 prefers-color-scheme을 초기값으로 사용.
