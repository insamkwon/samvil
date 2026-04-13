# Dashboard Recipes

> Recharts chart patterns, data fetching, responsive grid, data tables, CSV export, loading skeletons.
> For `solution_type: "dashboard"` (web-app subset).

---

## 1. Recharts Chart Patterns

### LineChart — Time Series Trend

```tsx
'use client'

import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import { format, parseISO } from 'date-fns'

interface DataPoint {
  date: string
  value: number
  label?: string
}

interface MetricLineChartProps {
  data: DataPoint[]
  xKey?: string
  yKey?: string
  color?: string
  height?: number
  showGrid?: boolean
}

export function MetricLineChart({
  data,
  xKey = 'date',
  yKey = 'value',
  color = 'hsl(var(--primary))',
  height = 300,
  showGrid = true,
}: MetricLineChartProps) {
  if (data.length === 0) {
    return <EmptyChart />
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data}>
        {showGrid && <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />}
        <XAxis
          dataKey={xKey}
          tick={{ fontSize: 12 }}
          tickFormatter={(v: string) => format(parseISO(v), 'MMM dd')}
        />
        <YAxis tick={{ fontSize: 12 }} />
        <Tooltip
          labelFormatter={(v: string) => format(parseISO(v), 'yyyy-MM-dd')}
          contentStyle={{ borderRadius: '8px', border: '1px solid hsl(var(--border))' }}
        />
        <Legend />
        <Line
          type="monotone"
          dataKey={yKey}
          stroke={color}
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 4 }}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
```

### BarChart — Categorical Comparison

```tsx
'use client'

import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer,
} from 'recharts'

interface BarDataPoint {
  category: string
  value: number
}

interface CategoryBarChartProps {
  data: BarDataPoint[]
  xKey?: string
  yKey?: string
  color?: string
  height?: number
}

export function CategoryBarChart({
  data,
  xKey = 'category',
  yKey = 'value',
  color = 'hsl(var(--primary))',
  height = 300,
}: CategoryBarChartProps) {
  if (data.length === 0) {
    return <EmptyChart />
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data}>
        <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
        <XAxis dataKey={xKey} tick={{ fontSize: 12 }} />
        <YAxis tick={{ fontSize: 12 }} />
        <Tooltip contentStyle={{ borderRadius: '8px', border: '1px solid hsl(var(--border))' }} />
        <Bar dataKey={yKey} fill={color} maxBarSize={50} radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}
```

### PieChart — Distribution

```tsx
'use client'

import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts'

interface PieDataPoint {
  name: string
  value: number
}

interface DistributionPieChartProps {
  data: PieDataPoint[]
  colors?: string[]
  innerRadius?: number
  outerRadius?: number
  height?: number
}

const DEFAULT_COLORS = [
  'hsl(var(--primary))',
  'hsl(220, 70%, 50%)',
  'hsl(280, 60%, 50%)',
  'hsl(340, 70%, 50%)',
  'hsl(40, 80%, 50%)',
  'hsl(160, 60%, 40%)',
]

export function DistributionPieChart({
  data,
  colors = DEFAULT_COLORS,
  innerRadius = 60,
  outerRadius = 100,
  height = 300,
}: DistributionPieChartProps) {
  if (data.length === 0) {
    return <EmptyChart />
  }

  // Limit to 8 slices max; group small slices into "Other"
  const chartData = data.length > 8
    ? [...data.slice(0, 7), { name: 'Other', value: data.slice(7).reduce((s, d) => s + d.value, 0) }]
    : data

  return (
    <ResponsiveContainer width="100%" height={height}>
      <PieChart>
        <Pie
          data={chartData}
          cx="50%"
          cy="50%"
          innerRadius={innerRadius}
          outerRadius={outerRadius}
          paddingAngle={2}
          dataKey="value"
          label={({ name, percent }: { name: string; percent: number }) =>
            `${name} ${(percent * 100).toFixed(0)}%`
          }
        >
          {chartData.map((_, index) => (
            <Cell key={`cell-${index}`} fill={colors[index % colors.length]} />
          ))}
        </Pie>
        <Tooltip contentStyle={{ borderRadius: '8px', border: '1px solid hsl(var(--border))' }} />
        <Legend />
      </PieChart>
    </ResponsiveContainer>
  )
}
```

### AreaChart — Cumulative Trend with Fill

```tsx
'use client'

import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer,
} from 'recharts'
import { format, parseISO } from 'date-fns'

interface AreaDataPoint {
  date: string
  value: number
}

interface MetricAreaChartProps {
  data: AreaDataPoint[]
  color?: string
  height?: number
}

export function MetricAreaChart({
  data,
  color = 'hsl(var(--primary))',
  height = 300,
}: MetricAreaChartProps) {
  if (data.length === 0) {
    return <EmptyChart />
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data}>
        <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 12 }}
          tickFormatter={(v: string) => format(parseISO(v), 'MMM dd')}
        />
        <YAxis tick={{ fontSize: 12 }} />
        <Tooltip
          labelFormatter={(v: string) => format(parseISO(v), 'yyyy-MM-dd')}
          contentStyle={{ borderRadius: '8px', border: '1px solid hsl(var(--border))' }}
        />
        <Area
          type="monotone"
          dataKey="value"
          stroke={color}
          fill={color}
          fillOpacity={0.3}
          strokeWidth={2}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
```

### EmptyChart — No Data Placeholder

```tsx
import { BarChart3 } from 'lucide-react'

export function EmptyChart({ message = 'No data for this period' }: { message?: string }) {
  return (
    <div className="flex h-[300px] items-center justify-center rounded-lg border border-dashed">
      <div className="text-center text-muted-foreground">
        <BarChart3 className="mx-auto mb-2 h-8 w-8" />
        <p className="text-sm">{message}</p>
      </div>
    </div>
  )
}
```

---

## 2. Data Fetching with SWR

### Basic Fetcher

```typescript
// lib/fetcher.ts
export async function fetcher<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) {
    const error = new Error('An error occurred while fetching data.')
    throw error
  }
  return res.json()
}
```

### Analytics Data Hook (no auto-refresh)

```typescript
// lib/use-metrics.ts
import useSWR from 'swr'
import { fetcher } from './fetcher'
import { subDays, format } from 'date-fns'

interface Metric {
  metric: string
  value: number
  date: string
  category?: string
}

interface UseMetricsOptions {
  dateFrom?: Date
  dateTo?: Date
  category?: string
}

export function useMetrics(options: UseMetricsOptions = {}) {
  const dateFrom = options.dateFrom || subDays(new Date(), 30)
  const dateTo = options.dateTo || new Date()

  const params = new URLSearchParams({
    from: format(dateFrom, 'yyyy-MM-dd'),
    to: format(dateTo, 'yyyy-MM-dd'),
  })
  if (options.category) params.set('category', options.category)

  const { data, error, isLoading } = useSWR<Metric[]>(
    `/api/metrics?${params.toString()}`,
    fetcher,
    { revalidateOnFocus: false }
  )

  return { data: data || [], error, isLoading }
}
```

### Real-time Data Hook (monitoring)

```typescript
// lib/use-realtime-data.ts
import useSWR from 'swr'
import { fetcher } from './fetcher'

interface RealtimeMetric {
  metric: string
  value: number
  timestamp: string
  status: 'ok' | 'warning' | 'critical'
  unit?: string
}

export function useRealtimeData(refreshInterval = 5000) {
  const { data, error, isLoading, mutate } = useSWR<RealtimeMetric[]>(
    '/api/status',
    fetcher,
    {
      refreshInterval,
      dedupingInterval: Math.max(refreshInterval - 1000, 1000),
      onSuccess: (newData) => {
        // Keep only last 100 data points to prevent memory leak
        if (newData.length > 100) {
          mutate(newData.slice(-100), { revalidate: false })
        }
      },
    }
  )

  return { data: data || [], error, isLoading, lastUpdated: data ? new Date() : null }
}
```

---

## 3. Real-time Update (Polling)

### Status Dashboard with Auto-refresh

```tsx
'use client'

import { useRealtimeData } from '@/lib/use-realtime-data'
import { MetricCard } from '@/components/metric-card'
import { format } from 'date-fns'

export function StatusDashboard() {
  const { data, isLoading, lastUpdated } = useRealtimeData(5000) // 5s polling

  if (isLoading) {
    return <DashboardSkeleton />
  }

  return (
    <div>
      <div className="mb-4 text-right text-sm text-muted-foreground">
        Last updated: {lastUpdated ? format(lastUpdated, 'HH:mm:ss') : '--:--:--'}
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
        {data.map((metric) => (
          <MetricCard
            key={metric.metric}
            label={metric.metric}
            value={`${metric.value}${metric.unit || ''}`}
            status={metric.status}
          />
        ))}
      </div>
    </div>
  )
}
```

---

## 4. Responsive Grid Layout

### Dashboard Grid

```tsx
import { MetricCard } from '@/components/metric-card'
import { MetricLineChart } from '@/components/charts/metric-line-chart'
import { CategoryBarChart } from '@/components/charts/category-bar-chart'

interface DashboardGridProps {
  metrics: Array<{ label: string; value: string; change: number }>
  trendData: Array<Record<string, unknown>>
  categoryData: Array<Record<string, unknown>>
}

export function DashboardGrid({ metrics, trendData, categoryData }: DashboardGridProps) {
  return (
    <div className="space-y-4">
      {/* KPI Metric Cards — 4 columns on desktop, 2 on tablet, 1 on mobile */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {metrics.map((m) => (
          <MetricCard key={m.label} {...m} />
        ))}
      </div>

      {/* Charts — 2 columns on desktop, 1 on mobile */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="rounded-lg border bg-card p-4">
          <h3 className="mb-4 text-sm font-medium text-muted-foreground">Trend</h3>
          <MetricLineChart data={trendData as any} />
        </div>
        <div className="rounded-lg border bg-card p-4">
          <h3 className="mb-4 text-sm font-medium text-muted-foreground">By Category</h3>
          <CategoryBarChart data={categoryData as any} />
        </div>
      </div>

      {/* Full-width table */}
      <div className="rounded-lg border bg-card p-4">
        <h3 className="mb-4 text-sm font-medium text-muted-foreground">Details</h3>
        {/* DataTable component here */}
      </div>
    </div>
  )
}
```

---

## 5. Data Table Patterns

### Sortable Table with Search

```tsx
'use client'

import { useState, useMemo } from 'react'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { Input } from '@/components/ui/input'
import { ArrowUpDown } from 'lucide-react'

interface Column<T> {
  key: keyof T
  label: string
  sortable?: boolean
  render?: (value: T[keyof T], row: T) => React.ReactNode
}

interface DataTableProps<T> {
  data: T[]
  columns: Column<T>[]
  searchPlaceholder?: string
  searchKeys?: Array<keyof T>
}

export function DataTable<T extends Record<string, unknown>>({
  data,
  columns,
  searchPlaceholder = 'Search...',
  searchKeys,
}: DataTableProps<T>) {
  const [search, setSearch] = useState('')
  const [sortKey, setSortKey] = useState<keyof T | null>(null)
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')

  const filteredData = useMemo(() => {
    let result = data

    if (search && searchKeys) {
      const q = search.toLowerCase()
      result = result.filter((row) =>
        searchKeys.some((key) => String(row[key]).toLowerCase().includes(q))
      )
    }

    if (sortKey) {
      result = [...result].sort((a, b) => {
        const aVal = a[sortKey]
        const bVal = b[sortKey]
        const cmp = aVal < bVal ? -1 : aVal > bVal ? 1 : 0
        return sortDir === 'asc' ? cmp : -cmp
      })
    }

    return result
  }, [data, search, searchKeys, sortKey, sortDir])

  const handleSort = (key: keyof T) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir('asc')
    }
  }

  if (data.length === 0) {
    return (
      <div className="py-8 text-center text-muted-foreground">
        No data available.
      </div>
    )
  }

  return (
    <div>
      {searchKeys && (
        <Input
          placeholder={searchPlaceholder}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="mb-4 max-w-sm"
        />
      )}
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              {columns.map((col) => (
                <TableHead key={String(col.key)}>
                  {col.sortable ? (
                    <button
                      className="flex items-center gap-1 hover:text-foreground"
                      onClick={() => handleSort(col.key)}
                    >
                      {col.label}
                      <ArrowUpDown className="h-3 w-3" />
                    </button>
                  ) : (
                    col.label
                  )}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {filteredData.map((row, i) => (
              <TableRow key={i}>
                {columns.map((col) => (
                  <TableCell key={String(col.key)}>
                    {col.render
                      ? col.render(row[col.key], row)
                      : String(row[col.key] ?? '')}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      {filteredData.length === 0 && search && (
        <p className="py-4 text-center text-sm text-muted-foreground">
          No results for &quot;{search}&quot;
        </p>
      )}
    </div>
  )
}
```

---

## 6. CSV Export

### CSV Export Button

```tsx
'use client'

import { Download } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface CsvExportButtonProps {
  data: Record<string, unknown>[]
  filename?: string
  label?: string
}

function escapeCsvField(value: unknown): string {
  const str = String(value ?? '')
  if (str.includes(',') || str.includes('"') || str.includes('\n')) {
    return `"${str.replace(/"/g, '""')}"`
  }
  return str
}

export function CsvExportButton({
  data,
  filename = 'export.csv',
  label = 'Export CSV',
}: CsvExportButtonProps) {
  const handleExport = () => {
    if (data.length === 0) return

    const headers = Object.keys(data[0])
    const csvRows = [
      headers.map(escapeCsvField).join(','),
      ...data.map((row) =>
        headers.map((h) => escapeCsvField(row[h])).join(',')
      ),
    ]
    const csvContent = csvRows.join('\n')

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <Button variant="outline" size="sm" onClick={handleExport} disabled={data.length === 0}>
      <Download className="mr-2 h-4 w-4" />
      {label}
    </Button>
  )
}
```

---

## 7. Loading Skeletons

### Dashboard Skeleton

```tsx
import { Skeleton } from '@/components/ui/skeleton'

export function DashboardSkeleton() {
  return (
    <div className="space-y-4">
      {/* Metric cards skeleton */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="rounded-lg border bg-card p-4 space-y-3">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-8 w-16" />
            <Skeleton className="h-3 w-20" />
          </div>
        ))}
      </div>

      {/* Charts skeleton */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {Array.from({ length: 2 }).map((_, i) => (
          <div key={i} className="rounded-lg border bg-card p-4 space-y-3">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-[300px] w-full rounded-md" />
          </div>
        ))}
      </div>

      {/* Table skeleton */}
      <div className="rounded-lg border bg-card p-4 space-y-3">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-10 w-full" />
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-8 w-full" />
        ))}
      </div>
    </div>
  )
}

export function ChartSkeleton() {
  return (
    <div className="flex h-[300px] items-center justify-center rounded-md bg-muted/50">
      <Skeleton className="h-[280px] w-[90%] rounded-md" />
    </div>
  )
}
```

### Usage with SWR loading state

```tsx
import { useMetrics } from '@/lib/use-metrics'
import { DashboardSkeleton } from '@/components/dashboard-skeleton'
import { DashboardGrid } from '@/components/dashboard-grid'

export function DashboardPage() {
  const { data, isLoading, error } = useMetrics()

  if (isLoading) return <DashboardSkeleton />
  if (error) {
    return (
      <div className="py-8 text-center text-destructive">
        Failed to load dashboard data. Please try again.
      </div>
    )
  }

  return <DashboardGrid metrics={data} />
}
```

---

## 8. Metric Card Component

```tsx
'use client'

import { TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { cn } from '@/lib/utils'

interface MetricCardProps {
  label: string
  value: string
  change?: number
  status?: 'ok' | 'warning' | 'critical'
  className?: string
}

export function MetricCard({ label, value, change, status, className }: MetricCardProps) {
  const isPositive = change !== undefined && change > 0
  const isNegative = change !== undefined && change < 0
  const isNeutral = change === 0

  const statusColor = status
    ? status === 'ok'
      ? 'text-green-600'
      : status === 'warning'
        ? 'text-yellow-600'
        : 'text-red-600'
    : ''

  return (
    <div className={cn('rounded-lg border bg-card p-4', className)}>
      <p className="text-sm font-medium text-muted-foreground">{label}</p>
      <div className="mt-1 flex items-baseline gap-2">
        <p className={cn('text-2xl font-bold', statusColor)}>{value}</p>
        {change !== undefined && (
          <span
            className={cn(
              'flex items-center text-xs font-medium',
              isPositive && 'text-green-600',
              isNegative && 'text-red-600',
              isNeutral && 'text-muted-foreground'
            )}
          >
            {isPositive && <TrendingUp className="mr-0.5 h-3 w-3" />}
            {isNegative && <TrendingDown className="mr-0.5 h-3 w-3" />}
            {isNeutral && <Minus className="mr-0.5 h-3 w-3" />}
            {isPositive ? '+' : ''}
            {change}%
          </span>
        )}
      </div>
    </div>
  )
}
```

---

## 9. Date Range Filter

```tsx
'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { subDays, format } from 'date-fns'

interface DateRange {
  from: Date
  to: Date
}

interface DateRangeFilterProps {
  onChange: (range: DateRange) => void
  defaultPreset?: string
}

const PRESETS = [
  { label: '7d', days: 7 },
  { label: '30d', days: 30 },
  { label: '90d', days: 90 },
  { label: '1y', days: 365 },
] as const

export function DateRangeFilter({ onChange, defaultPreset = '30d' }: DateRangeFilterProps) {
  const [activePreset, setActivePreset] = useState(defaultPreset)

  const handlePreset = (days: number, label: string) => {
    setActivePreset(label)
    onChange({
      from: subDays(new Date(), days),
      to: new Date(),
    })
  }

  return (
    <div className="flex gap-2">
      {PRESETS.map((preset) => (
        <Button
          key={preset.label}
          variant={activePreset === preset.label ? 'default' : 'outline'}
          size="sm"
          onClick={() => handlePreset(preset.days, preset.label)}
        >
          {preset.label}
        </Button>
      ))}
    </div>
  )
}
```
