// Valida as URLs do roteiro da demo (docs/roteiro_demo.md) e salva as capturas do plano B em results/screenshots/demo/.
// Uso (stack no ar): node e2e/demo-urls.mjs [url_base]
import fs from 'node:fs'
import path from 'node:path'
import { chromium } from '@playwright/test'

const base = process.argv[2] ?? 'http://localhost:5173'
const out = path.resolve(import.meta.dirname, '../../results/screenshots/demo')
fs.mkdirSync(out, { recursive: true })
const MOMENTOS = [
  ['02-faixa-resolvida', '/t/afc56e3505505b81', 'phase-strip'],
  ['03-faixa-nao-resolvida', '/t/dfe5dad526a8d88f', 'phase-strip'],
  ['04-detector-no-new-info-passo-30', '/t/dfe5dad526a8d88f?step=30&view=graph', 'step-node'],
  ['04b-passo-original-9', '/t/dfe5dad526a8d88f?step=9&view=graph', 'step-node'],
  ['04c-detector-loop-passo-24', '/t/dfe5dad526a8d88f?step=24&view=graph&filter=loop', 'step-node'],
  ['05-dashboard-nao-resolvida', '/t/dfe5dad526a8d88f?view=dashboard', 'tab-dashboard'],
  ['05b-dashboard-resolvida', '/t/afc56e3505505b81?view=dashboard', 'tab-dashboard'],
  ['06-mesma-traj-do-traceview', '/t/90b7a9c28a9c71a3', 'phase-strip'],
]
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
let ok = true
for (const [nome, url, sel] of MOMENTOS) {
  const resp = await page.goto(base + url)
  try {
    await page.getByTestId(sel).first().waitFor({ timeout: 15000 })
    await page.waitForTimeout(1200)
    await page.screenshot({ path: `${out}/${nome}.png` })
    console.log('ok  ', url)
  } catch {
    ok = false
    console.log('FALHA', url, resp?.status(), (await page.innerText('body')).slice(0, 120).replace(/\n/g, ' '))
  }
}
await browser.close()
process.exit(ok ? 0 : 1)
