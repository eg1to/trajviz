import * as React from 'react'
import { cn } from '@/lib/utils'

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(({ className, ...p }, ref) => (
  <input ref={ref} className={cn('h-8 w-full rounded-md border border-input bg-card px-2.5 text-[13px] placeholder:text-muted-foreground', className)} {...p} />
))
Input.displayName = 'Input'
