import { toPng } from 'html-to-image'
import { getNodesBounds, getViewportForBounds, type Node } from '@xyflow/react'

export function download(dataUrl: string, name: string) {
  const a = document.createElement('a')
  a.href = dataUrl
  a.download = name
  a.click()
}

const bg = () => getComputedStyle(document.documentElement).getPropertyValue('--background').trim() || '#ffffff'

/** PNG 2× de um elemento DOM (cartão do dashboard, faixa de fases…). */
export async function exportElementPng(el: HTMLElement, name: string) {
  const url = await toPng(el, { pixelRatio: 2, backgroundColor: bg(), cacheBust: true, filter: (n) => !(n instanceof HTMLElement && n.dataset.noExport !== undefined) })
  download(url, name)
}

/** PNG 2× do grafo inteiro (enquadra todos os nós, independentemente do zoom atual). */
export async function exportGraphPng(container: HTMLElement, nodes: Node[], name: string) {
  const viewport = container.querySelector<HTMLElement>('.react-flow__viewport')
  if (!viewport) return
  const real = nodes.filter((n) => n.type !== 'loopArc')
  const b = getNodesBounds(real.length ? real : nodes)
  const pad = 40
  const w = Math.min(Math.max(b.width + pad * 2, 600), 6000), h = Math.min(Math.max(b.height + pad * 2 + 40, 300), 6000)
  const vp = getViewportForBounds({ x: b.x, y: b.y - 40, width: b.width, height: b.height + 40 }, w, h, 0.2, 2, pad / Math.max(w, h))
  const url = await toPng(viewport, {
    pixelRatio: 2, width: w, height: h, backgroundColor: bg(), cacheBust: true,
    style: { width: `${w}px`, height: `${h}px`, transform: `translate(${vp.x}px, ${vp.y}px) scale(${vp.zoom})` },
  })
  download(url, name)
}
