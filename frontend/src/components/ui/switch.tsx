import * as React from 'react'
import * as SwitchPrimitive from '@radix-ui/react-switch'
import { cn } from '@/lib/utils'

export const Switch = React.forwardRef<HTMLButtonElement, React.ComponentPropsWithoutRef<typeof SwitchPrimitive.Root>>(({ className, ...p }, ref) => (
  <SwitchPrimitive.Root ref={ref} className={cn('inline-flex h-4.5 w-8 shrink-0 items-center rounded-full border border-input bg-muted transition-colors data-[state=checked]:bg-primary', className)} {...p}>
    <SwitchPrimitive.Thumb className="block size-3.5 translate-x-0.5 rounded-full bg-white shadow-sm transition-transform data-[state=checked]:translate-x-[16px]" />
  </SwitchPrimitive.Root>
))
Switch.displayName = 'Switch'
