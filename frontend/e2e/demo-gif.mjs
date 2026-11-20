// Grava o fluxo da demo (biblioteca → upload → grafo → inspetor → dashboard) em vídeo (webm). Uso: node e2e/demo-gif.mjs <saida_dir> [url]
// Conversão para GIF: ver docs/roteiro_demo.md / README (ffmpeg, paleta + 12 fps, ≤ 8 MB).
import fs from 'node:fs'
import path from 'node:path'
import { chromium } from '@playwright/test'

const out = path.resolve(process.argv[2] ?? 'demo-video')
const base = process.argv[3] ?? 'http://localhost:5173'
const file = path.resolve(import.meta.dirname, '../../data/samples/swe-rebench/chatcmpl-831fa55b3ab429d20cf66336189bc3b1.json') // resolvida, 96 passos
fs.mkdirSync(out, { recursive: true })
const browser = await chromium.launch()
const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, recordVideo: { dir: out, size: { width: 1280, height: 800 } } })
const page = await ctx.newPage()
const wait = (ms) => page.waitForTimeout(ms)
await page.goto(base + '/')
await page.waitForSelector('[data-testid=lib-row]')
await wait(1800)
await page.getByTestId('file-input').setInputFiles(file)           // upload do log bruto
await page.waitForSelector('[data-testid=step-node]')
await wait(2200)
const nodes = page.getByTestId('step-node')
await nodes.nth(12).click()                                         // inspetor de um passo
await wait(1800)
for (let i = 0; i < 4; i++) { await page.keyboard.press('j'); await wait(700) }
await page.getByTestId('tab-dashboard').click()                     // dashboard
await wait(2500)
await page.mouse.wheel(0, 700); await wait(1800)
await page.mouse.wheel(0, 700); await wait(1800)
await ctx.close()
await browser.close()
console.log(fs.readdirSync(out).filter((f) => f.endsWith('.webm')))
