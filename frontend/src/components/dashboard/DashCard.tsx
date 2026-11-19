import { useRef } from 'react'
import { Download } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/card'
import { exportElementPng } from '@/lib/export'
import { cn } from '@/lib/utils'

export function DashCard({ title, subtitle, children, className, id, actions, bodyClass }: {
  title: string; subtitle?: string; children: React.ReactNode; className?: string; id: string; actions?: React.ReactNode; bodyClass?: string
}) {
  const ref = useRef<HTMLDivElement>(null)
  return (
    <Card ref={ref} className={cn('flex flex-col', className)} data-testid={`card-${id}`}>
      <CardHeader>
        <div className="min-w-0"><CardTitle>{title}</CardTitle>{subtitle && <p className="text-[11px] text-muted-foreground">{subtitle}</p>}</div>
        <div className="flex items-center gap-1.5" data-no-export>
          {actions}
          <Button variant="ghost" size="icon" aria-label={`Exportar ${title} como PNG`} title="Exportar PNG" data-no-export
            onClick={() => ref.current && exportElementPng(ref.current, `dashboard-${id}.png`).catch((e) => toast.error(`Falha ao exportar PNG: ${(e as Error).message}`))}><Download /></Button>
        </div>
      </CardHeader>
      <CardBody className={cn('min-h-0 flex-1', bodyClass)}>{children}</CardBody>
    </Card>
  )
}
