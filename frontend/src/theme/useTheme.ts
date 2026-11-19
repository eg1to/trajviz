import { useSyncExternalStore } from 'react'

const listeners = new Set<() => void>()
const isDark = () => document.documentElement.classList.contains('dark')

export function setTheme(dark: boolean) {
  document.documentElement.classList.toggle('dark', dark)
  try { localStorage.setItem('trajviz-theme', dark ? 'dark' : 'light') } catch { /* sem storage */ }
  listeners.forEach((l) => l())
}

export function useTheme() {
  const dark = useSyncExternalStore((cb) => { listeners.add(cb); return () => listeners.delete(cb) }, isDark)
  return { dark, toggle: () => setTheme(!dark) }
}
