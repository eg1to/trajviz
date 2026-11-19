import { cn } from '@/lib/utils'

export function Badge({ className, tone = 'default', ...p }: React.HTMLAttributes<HTMLSpanElement> & { tone?: 'default' | 'ok' | 'danger' | 'muted' | 'warn' }) {
  const tones = {
    default: 'bg-accent text-primary border-primary/30',
    ok: 'bg-ok/15 text-ok border-ok/40',
    danger: 'bg-danger/15 text-danger border-danger/40',
    warn: 'bg-[#E69F00]/15 text-[#9a6a00] dark:text-[#E69F00] border-[#E69F00]/50',
    muted: 'bg-muted text-muted-foreground border-border',
  }
  return <span className={cn('inline-flex items-center gap-1 rounded border px-1.5 py-px text-[11px] font-medium leading-4', tones[tone], className)} {...p} />
}
