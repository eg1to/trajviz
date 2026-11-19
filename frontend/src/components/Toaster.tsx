import { Toaster as Sonner } from 'sonner'
import { useTheme } from '@/theme/useTheme'

export function Toaster() {
  const { dark } = useTheme()
  return <Sonner theme={dark ? 'dark' : 'light'} position="bottom-right" richColors closeButton />
}
