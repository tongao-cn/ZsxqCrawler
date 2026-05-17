"use client"

import * as React from "react"
import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Calendar } from "@/components/ui/calendar"
import { cn } from "@/lib/utils"

const MONTH_LABELS = Array.from({ length: 12 }, (_, index) => `${index + 1}月`)

function formatDate(date: Date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, "0")
  const day = String(date.getDate()).padStart(2, "0")
  return `${year}-${month}-${day}`
}

function parseDate(value?: string) {
  return value ? new Date(`${value}T00:00:00`) : undefined
}

function formatDateLabel(value?: string) {
  return value?.replaceAll("-", "/") || "选择日期"
}

function isDateDisabled(date: Date, min?: string, max?: string) {
  const value = formatDate(date)
  return Boolean((min && value < min) || (max && value > max))
}

interface DatePickerButtonProps {
  align?: "start" | "end"
  className?: string
  max?: string
  min?: string
  onChange: (value: string) => void
  placeholder?: string
  value: string
}

export function DatePickerButton({
  align = "start",
  className,
  max,
  min,
  onChange,
  placeholder = "选择日期",
  value,
}: DatePickerButtonProps) {
  const [open, setOpen] = React.useState(false)
  const selectedDate = parseDate(value)
  const [viewMonth, setViewMonth] = React.useState(selectedDate || new Date())
  const rootRef = React.useRef<HTMLDivElement>(null)

  React.useEffect(() => {
    const nextSelectedDate = parseDate(value)
    if (nextSelectedDate) {
      setViewMonth(nextSelectedDate)
    }
  }, [value])

  React.useEffect(() => {
    if (!open) {
      return
    }

    const closeOnOutside = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false)
      }
    }

    document.addEventListener("pointerdown", closeOnOutside)
    document.addEventListener("keydown", closeOnEscape)
    return () => {
      document.removeEventListener("pointerdown", closeOnOutside)
      document.removeEventListener("keydown", closeOnEscape)
    }
  }, [open])

  const jumpYear = (offset: number) => {
    setViewMonth(new Date(viewMonth.getFullYear() + offset, viewMonth.getMonth(), 1))
  }

  const jumpMonth = (monthIndex: number) => {
    setViewMonth(new Date(viewMonth.getFullYear(), monthIndex, 1))
  }

  return (
    <div ref={rootRef} className={cn("relative", className)}>
      <Button
        type="button"
        variant="outline"
        className="h-9 w-full justify-between text-xs"
        onClick={() => setOpen((current) => !current)}
      >
        {value ? formatDateLabel(value) : placeholder}
        <CalendarDays className="h-3.5 w-3.5 text-muted-foreground" />
      </Button>
      {open && (
        <div
          className={cn(
            "absolute top-[calc(100%+0.375rem)] z-50 w-[19rem] rounded-md border bg-background p-3 shadow-lg",
            align === "end" ? "right-0" : "left-0"
          )}
        >
          <div className="mb-3 flex items-center justify-between">
            <Button
              type="button"
              variant="outline"
              size="icon"
              className="h-7 w-7"
              onClick={() => jumpYear(-1)}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <div className="text-sm font-medium">{viewMonth.getFullYear()}</div>
            <Button
              type="button"
              variant="outline"
              size="icon"
              className="h-7 w-7"
              onClick={() => jumpYear(1)}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
          <div className="mb-3 grid grid-cols-6 gap-1">
            {MONTH_LABELS.map((label, index) => (
              <Button
                key={label}
                type="button"
                variant={viewMonth.getMonth() === index ? "secondary" : "ghost"}
                size="sm"
                className="h-7 px-1 text-xs"
                onClick={() => jumpMonth(index)}
              >
                {label}
              </Button>
            ))}
          </div>
          <Calendar
            mode="single"
            month={viewMonth}
            onMonthChange={setViewMonth}
            selected={selectedDate}
            disabled={(date) => isDateDisabled(date, min, max)}
            onSelect={(date) => {
              if (!date) {
                return
              }
              onChange(formatDate(date))
              setOpen(false)
            }}
          />
        </div>
      )}
    </div>
  )
}

interface MonthPickerButtonProps {
  className?: string
  onChange: (value: string) => void
  placeholder?: string
  value: string
}

export function MonthPickerButton({
  className,
  onChange,
  placeholder = "选择月份",
  value,
}: MonthPickerButtonProps) {
  const [open, setOpen] = React.useState(false)
  const rootRef = React.useRef<HTMLDivElement>(null)
  const selectedYear = value ? Number(value.slice(0, 4)) : new Date().getFullYear()
  const selectedMonth = value ? Number(value.slice(5, 7)) : undefined
  const [viewYear, setViewYear] = React.useState(selectedYear)

  React.useEffect(() => {
    if (value) {
      setViewYear(Number(value.slice(0, 4)))
    }
  }, [value])

  React.useEffect(() => {
    if (!open) {
      return
    }

    const closeOnOutside = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false)
      }
    }

    document.addEventListener("pointerdown", closeOnOutside)
    document.addEventListener("keydown", closeOnEscape)
    return () => {
      document.removeEventListener("pointerdown", closeOnOutside)
      document.removeEventListener("keydown", closeOnEscape)
    }
  }, [open])

  return (
    <div ref={rootRef} className={cn("relative", className)}>
      <Button
        type="button"
        variant="outline"
        className="h-9 w-full justify-between text-xs"
        onClick={() => setOpen((current) => !current)}
      >
        {value ? value.replace("-", "/") : placeholder}
        <CalendarDays className="h-3.5 w-3.5 text-muted-foreground" />
      </Button>
      {open && (
        <div className="absolute left-0 top-[calc(100%+0.375rem)] z-50 w-64 rounded-md border bg-background p-3 shadow-lg">
          <div className="mb-3 flex items-center justify-between">
            <Button
              type="button"
              variant="outline"
              size="icon"
              className="h-7 w-7"
              onClick={() => setViewYear((year) => year - 1)}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <div className="text-sm font-medium">{viewYear}</div>
            <Button
              type="button"
              variant="outline"
              size="icon"
              className="h-7 w-7"
              onClick={() => setViewYear((year) => year + 1)}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
          <div className="grid grid-cols-3 gap-2">
            {MONTH_LABELS.map((label, index) => {
              const month = index + 1
              const selected = viewYear === selectedYear && month === selectedMonth
              return (
                <Button
                  key={label}
                  type="button"
                  variant={selected ? "default" : "ghost"}
                  size="sm"
                  className="h-8 text-xs"
                  onClick={() => {
                    onChange(`${viewYear}-${String(month).padStart(2, "0")}`)
                    setOpen(false)
                  }}
                >
                  {label}
                </Button>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
