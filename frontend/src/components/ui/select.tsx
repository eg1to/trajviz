import * as React from 'react'
import * as SelectPrimitive from '@radix-ui/react-select'
import { Check, ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'

export const Select = SelectPrimitive.Root
export const SelectValue = SelectPrimitive.Value

export const SelectTrigger = React.forwardRef<HTMLButtonElement, React.ComponentPropsWithoutRef<typeof SelectPrimitive.Trigger>>(({ className, children, ...p }, ref) => (
  <SelectPrimitive.Trigger ref={ref} className={cn('flex h-8 w-full items-center justify-between gap-2 whitespace-nowrap rounded-md border border-input bg-card px-2.5 text-[13px] data-[placeholder]:text-muted-foreground', className)} {...p}>
    {children}
    <SelectPrimitive.Icon asChild><ChevronDown className="size-3.5 opacity-60" /></SelectPrimitive.Icon>
  </SelectPrimitive.Trigger>
))
SelectTrigger.displayName = 'SelectTrigger'

export const SelectContent = React.forwardRef<HTMLDivElement, React.ComponentPropsWithoutRef<typeof SelectPrimitive.Content>>(({ className, children, ...p }, ref) => (
  <SelectPrimitive.Portal>
    <SelectPrimitive.Content ref={ref} position="popper" sideOffset={4} className={cn('z-50 max-h-72 min-w-[var(--radix-select-trigger-width)] overflow-auto rounded-md border bg-card p-1 text-[13px] shadow-sm', className)} {...p}>
      <SelectPrimitive.Viewport>{children}</SelectPrimitive.Viewport>
    </SelectPrimitive.Content>
  </SelectPrimitive.Portal>
))
SelectContent.displayName = 'SelectContent'

export const SelectItem = React.forwardRef<HTMLDivElement, React.ComponentPropsWithoutRef<typeof SelectPrimitive.Item> & { hint?: string }>(({ className, children, hint, ...p }, ref) => (
  <SelectPrimitive.Item ref={ref} className={cn('relative flex cursor-pointer select-none items-center gap-2 rounded px-2 py-1.5 pl-6 outline-none data-[highlighted]:bg-muted', className)} {...p}>
    <span className="absolute left-1.5 flex size-3.5 items-center justify-center"><SelectPrimitive.ItemIndicator><Check className="size-3" /></SelectPrimitive.ItemIndicator></span>
    <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
    {hint && <span className="ml-auto text-[11px] text-muted-foreground">{hint}</span>}
  </SelectPrimitive.Item>
))
SelectItem.displayName = 'SelectItem'
