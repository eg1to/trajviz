import { Moon, Sun } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useTheme } from '@/theme/useTheme'

export function ThemeToggle() {
  const { dark, toggle } = useTheme()
  return (
    <Button variant="ghost" size="icon" onClick={toggle} aria-label={dark ? 'Tema claro' : 'Tema escuro'} title={dark ? 'Tema claro' : 'Tema escuro'} data-testid="theme-toggle">
      {dark ? <Sun /> : <Moon />}
    </Button>
  )
}
