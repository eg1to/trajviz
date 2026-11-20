// Comparação trajviz × TraceView (Fase 7). Uso: node e2e/comparacao.mjs  (trajviz em :5173 com a API em :8010; TraceView em :8601)
// Mede, para duas trajetórias: (a) trajviz: upload → grafo visível; (b) TraceView: nº de rotulações e de interações até liberar a visualização.
import fs from 'node:fs'
import path from 'node:path'
import { chromium } from '@playwright/test'

const OUT = path.resolve(import.meta.dirname, '../../results/screenshots/comparacao')
const TV = process.env.TRACEVIEW_URL ?? 'http://localhost:8601'
const TJ = process.env.TRAJVIZ_URL ?? 'http://localhost:5173'
const SAMPLES = [
  { key: 'pytest-5692', file: '/home/eg1to/tcc/traceview/evaluation_samples/pytest-dev__pytest-5692__eval_02_fix-and-test.traj', fullLabel: true },
  { key: 'express-3870', file: process.env.CTB_TRAJ, fullLabel: false },
]
fs.mkdirSync(OUT, { recursive: true })
const browser = await chromium.launch()
const result = {}

for (const s of SAMPLES) {
  const r = (result[s.key] = {})
  // ---- trajviz: upload → visualização
  {
    const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
    await page.goto(TJ + '/')
    await page.waitForSelector('[data-testid=lib-row]')
    const t0 = Date.now()
    await page.getByTestId('file-input').setInputFiles(s.file)
    await page.waitForSelector('[data-testid=step-node]')
    await page.getByTestId('phase-strip').waitFor()
    r.trajviz = { acoes_do_usuario: 2, upload_ate_grafo_ms: Date.now() - t0, url: page.url(), rotulacoes_manuais: 0 }
    await page.waitForTimeout(800)
    await page.screenshot({ path: `${OUT}/${s.key}-trajviz-grafo.png` })
    await page.close()
  }
  // ---- TraceView
  {
    const page = await browser.newPage({ viewport: { width: 1600, height: 1400 } })
    let interacoes = 0
    await page.goto(TV)
    await page.waitForSelector('input[type=file]', { state: 'attached' })
    await page.waitForTimeout(2500)
    const t0 = Date.now()
    await page.setInputFiles('input[type=file]', s.file); interacoes++
    await page.getByText('Open in single-run workspace').waitFor()
    const txt = await page.innerText('body')
    r.traceview = { nIter: +/Iterations\s+(\d+)/.exec(txt)[1], acoes_total: +/Action labels\s+0 of (\d+)/.exec(txt)[1], relacoes_total: +/Relationship labels\s+0 of (\d+)/.exec(txt)[1] }
    await page.screenshot({ path: `${OUT}/${s.key}-traceview-ingest.png` })
    await page.getByText('Open in single-run workspace').click(); interacoes++
    await page.getByText('ACTION PREVIEW').waitFor()
    await page.screenshot({ path: `${OUT}/${s.key}-traceview-rotulacao-acoes.png`, fullPage: true })
    const nA = s.fullLabel ? r.traceview.acoes_total : Math.min(5, r.traceview.acoes_total)
    const pick = async (i, label) => {
      await page.locator('[data-baseweb=select]').nth(i).click()
      await page.locator('[role=option]').filter({ hasText: new RegExp(`^${label}$`) }).first().click()
      interacoes += 2
      await page.waitForTimeout(700)
    }
    const cats = ['Generate fix', 'Run tests', 'Run tests', 'Generate fix', 'Run tests', 'Generate fix', 'Run tests', 'Generate fix']
    for (let i = 0; i < nA; i++) await pick(i + 1, cats[i % cats.length])
    await page.getByRole('button', { name: 'Continue to relationship labels' }).click(); interacoes++
    await page.getByText('Relationship Labels:').waitFor()
    await page.screenshot({ path: `${OUT}/${s.key}-traceview-rotulacao-relacoes.png`, fullPage: true })
    // relações: família Thought→Action (selects 2..); o mínimo é 5; no modo completo, as 5 famílias
    const fams = s.fullLabel ? ['Thought -> Action', 'Thought -> Thought', 'Action -> Action', 'Result -> Thought', 'Result -> Action'] : ['Thought -> Action']
    const opt = { 'Thought -> Action': 'Alignment', 'Thought -> Thought': 'Follow-up', 'Action -> Action': 'Follow-up', 'Result -> Thought': 'Follow-up', 'Result -> Action': 'Informative' }
    let nRel = 0
    for (const [fi, fam] of fams.entries()) {
      if (fi > 0) {
        await page.locator('[data-baseweb=select]').nth(1).click()
        await page.locator('[role=option]').filter({ hasText: fam }).first().click(); interacoes += 2
        await page.waitForTimeout(1200)
      }
      const rows = (await page.locator('[data-baseweb=select]').count()) - 2
      const want = s.fullLabel ? rows : Math.min(5, rows)
      for (let i = 0; i < want; i++) { await pick(i + 2, opt[fam]); nRel++ }
    }
    const btn = page.getByRole('button', { name: 'Send to overview' })
    await btn.waitFor(); await page.waitForTimeout(800)
    r.traceview.rotulacoes_feitas = { acoes: nA, relacoes: nRel, total: nA + nRel }
    r.traceview.minimo_exigido = { acoes: Math.min(5, r.traceview.acoes_total), relacoes: Math.min(5, r.traceview.relacoes_total) }
    r.traceview.completo = r.traceview.acoes_total + r.traceview.relacoes_total
    await page.screenshot({ path: `${OUT}/${s.key}-traceview-pronto-para-enviar.png` })
    await btn.click(); interacoes++
    await page.waitForTimeout(3000)
    // Overview → Analysis (grafo)
    r.traceview.interacoes_ate_liberar = interacoes
    r.traceview.tempo_script_ms = Date.now() - t0
    await page.screenshot({ path: `${OUT}/${s.key}-traceview-overview.png`, fullPage: true })
    await page.getByRole('button', { name: 'Open analysis' }).click(); interacoes++
    await page.waitForTimeout(6000)
    await page.screenshot({ path: `${OUT}/${s.key}-traceview-analise.png`, fullPage: true })
    r.traceview.interacoes_ate_liberar = interacoes
    r.traceview.tempo_script_ms = Date.now() - t0
    r.traceview.overview_botoes = (await page.locator('button').allInnerTexts()).filter(Boolean).slice(0, 20)
    await page.close()
  }
  console.log(s.key, JSON.stringify(r))
}
fs.writeFileSync(`${OUT}/medidas.json`, JSON.stringify(result, null, 1))
await browser.close()
