import { Highlight, themes } from 'prism-react-renderer'
import '@/lib/prism-langs'
import { useTheme } from '@/theme/useTheme'
import { cn } from '@/lib/utils'

export type Lang = 'bash' | 'python' | 'diff' | 'plain'

export function CodeBlock({ code, language = 'plain', className, maxHeight = 260 }: { code: string; language?: Lang; className?: string; maxHeight?: number }) {
  const { dark } = useTheme()
  return (
    <Highlight code={code.replace(/\n$/, '')} language={language === 'plain' ? 'text' : language} theme={dark ? themes.vsDark : themes.github}>
      {({ tokens, getLineProps, getTokenProps }) => (
        <pre className={cn('mono scroll-thin overflow-auto rounded border bg-code p-2', className)} style={{ maxHeight, background: undefined, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }} data-testid="code-block">
          {tokens.map((line, i) => (
            <div key={i} {...getLineProps({ line })} style={{ ...getLineProps({ line }).style, background: undefined }}>
              {line.map((token, k) => <span key={k} {...getTokenProps({ token })} />)}
            </div>
          ))}
        </pre>
      )}
    </Highlight>
  )
}

/** str_replace: old → new com linhas removidas/adicionadas coloridas (cor + sinal −/+). */
export function DiffBlock({ oldStr, newStr, maxHeight = 280 }: { oldStr: string; newStr: string; maxHeight?: number }) {
  const rows = [
    ...oldStr.split('\n').map((t) => ({ sign: '−', t, cls: 'bg-[#D55E00]/15 text-[#a04000] dark:text-[#ffb27a]' })),
    ...newStr.split('\n').map((t) => ({ sign: '+', t, cls: 'bg-[#009E73]/15 text-[#00694c] dark:text-[#6ee7b7]' })),
  ]
  return (
    <pre className="mono scroll-thin overflow-auto rounded border bg-code" style={{ maxHeight }} data-testid="diff-block">
      {rows.map((r, i) => <div key={i} className={cn('flex px-1', r.cls)}><span className="w-4 shrink-0 select-none font-bold">{r.sign}</span><span className="whitespace-pre-wrap break-words">{r.t || ' '}</span></div>)}
    </pre>
  )
}
