import { expect, test } from '@playwright/test'
import { openSample } from './helpers'

test('biblioteca lista as amostras dos três datasets e filtra', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByTestId('lib-row').first()).toBeVisible()
  const total = await page.getByTestId('lib-row').count()
  expect(total).toBeGreaterThan(50)
  for (const ds of ['swe-rebench', 'swe-smith', 'codetracebench']) await expect(page.locator(`[data-testid=lib-row][data-dataset="${ds}"]`).first()).toBeVisible()
  await page.getByTestId('lib-search').fill('zzzz-nao-existe')
  await expect(page.getByTestId('lib-empty')).toBeVisible()
  await page.getByTestId('lib-search').fill('')
  await expect(page.getByTestId('lib-row').first()).toBeVisible()
  // SWE-smith traz o selo "não validado"
  await expect(page.locator('[data-testid=lib-row][data-dataset="swe-smith"]').first()).toContainText('não validado')
})

for (const ds of ['swe-rebench', 'swe-smith', 'codetracebench']) {
  test(`abre uma amostra de ${ds}, seleciona um passo e vai ao dashboard`, async ({ page }) => {
    await openSample(page, ds)
    await expect(page.getByTestId('traj-header')).toBeVisible()
    await expect(page.getByTestId('outcome-badge')).toBeVisible()
    // clique num passo (faixa de fases) → inspetor e URL
    const strip = page.getByTestId('phase-strip')
    const box = (await strip.boundingBox())!
    await page.mouse.click(box.x + box.width * 0.3, box.y + 20)
    await expect(page.getByTestId('inspector-idx')).toBeVisible()
    await expect(page).toHaveURL(/step=\d+/)
    const idxText = await page.getByTestId('inspector-idx').textContent()
    // clique num nó do grafo
    await page.getByTestId('step-node').first().click()
    await expect(page.getByTestId('inspector-idx')).toContainText('#')
    expect(idxText).toContain('Passo #')
    // dashboard → clicar num problema → passo selecionado no grafo
    await page.getByTestId('tab-dashboard').click()
    await expect(page.getByTestId('dashboard-tab')).toBeVisible()
    await expect(page.getByTestId('card-esforco')).toBeVisible()
    const chip = page.getByTestId('problem-chip').first()
    await expect(chip).toBeVisible()
    const want = await chip.getAttribute('data-idx')
    await chip.click()
    await expect(page.getByTestId('graph-tab')).toBeVisible()
    await expect(page.getByTestId('inspector-idx')).toHaveText(`Passo #${want}`)
    await expect(page).toHaveURL(new RegExp(`step=${want}(&|$)`))
  })
}

test('abre direto num passo pela URL, alterna tema e corrige um rótulo', async ({ page }) => {
  await openSample(page, 'swe-rebench')
  const base = page.url().split('?')[0]
  await page.goto(`${base}?step=7&view=graph&filter=error`)
  await expect(page.getByTestId('inspector-idx')).toHaveText('Passo #7')
  await expect(page.getByTestId('f-errors')).toBeChecked()
  await page.getByTestId('theme-toggle').click()
  await expect(page.locator('html')).toHaveClass(/dark/)
  await page.getByTestId('theme-toggle').click()
  // correção de rótulo (PATCH) reflete sem recarregar
  await page.goto(`${base}?step=3`)
  await page.getByTestId('label-select').click()
  await page.getByRole('option', { name: /Preparar/ }).click()
  await expect(page.getByTestId('label-source')).toHaveText('usuário')
  await expect(page.locator('[data-testid=step-node][data-idx="3"]')).toHaveAttribute('data-kind', 'setup')
})

test('teclas j/k navegam e o modo compacto expande um grupo', async ({ page }) => {
  await openSample(page, 'swe-rebench')
  await page.goto(page.url().split('?')[0] + '?step=10')
  await expect(page.getByTestId('inspector-idx')).toHaveText('Passo #10')
  await page.keyboard.press('j')
  await expect(page.getByTestId('inspector-idx')).toHaveText('Passo #11')
  await page.keyboard.press('k'); await page.keyboard.press('k')
  await expect(page.getByTestId('inspector-idx')).toHaveText('Passo #9')
  const groups = page.getByTestId('group-node')
  if (await groups.count()) {
    const nodes = async () => Number(((await page.getByTestId('visible-count').textContent()) ?? '').match(/(\d+) nós/)?.[1] ?? 0)
    const before = await nodes()
    await groups.first().click()
    await expect.poll(nodes).toBeGreaterThan(before)  // o grupo "read × 3" virou 3 nós
  }
})

test('revisão visual: rótulo do nó, numeração, arquivos criados e minimapa', async ({ page }) => {
  await openSample(page, 'swe-rebench')
  // 1) o rótulo mostra o segmento que definiu a categoria (sem `cd …` nem /workspace/<repo>/)
  const labels = await page.locator('[data-testid=step-node] .mono.truncate').allTextContents()
  expect(labels.length).toBeGreaterThan(5)
  for (const l of labels) { expect(l.startsWith('cd ')).toBe(false); expect(l).not.toContain('/workspace/'); expect(l).not.toContain('/testbed/') }
  // 3) numeração: #idx (0-based) + ordinal de 1 a N
  const n = Number(((await page.getByTestId('n-steps').textContent()) ?? '0').replace(/\D/g, ''))
  await page.goto(page.url().split('?')[0] + '?step=4')
  await expect(page.getByTestId('inspector-idx')).toHaveText('Passo #4')
  await expect(page.getByTestId('inspector-ordinal')).toHaveText(`· 5º de ${n}`)
  // 5) minimapa recolhível
  await expect(page.locator('.react-flow__minimap')).toBeVisible()
  await page.getByTestId('toggle-minimap').click()
  await expect(page.locator('.react-flow__minimap')).toHaveCount(0)
  await page.getByTestId('toggle-minimap').click()
  await expect(page.locator('.react-flow__minimap')).toBeVisible()
  // 2) arquivos criados pelo agente nunca aparecem como "editado sem ler"
  await page.getByTestId('tab-dashboard').click()
  await expect(page.getByTestId('files-table')).toBeVisible()
  const rows = page.locator('[data-testid=files-table] tbody tr')
  const total = await rows.count()
  let created = 0
  for (let i = 0; i < total; i++) {
    const r = rows.nth(i)
    const isCreated = (await r.getByTestId('badge-created').count()) > 0
    created += isCreated ? 1 : 0
    if (isCreated) await expect(r.getByTestId('warn-never-read')).toHaveCount(0)
  }
  expect(created).toBeGreaterThan(0)  // essa amostra cria scripts de reprodução
  // 4) KPI "passos" cabe no cartão
  const kpi = page.locator('[data-testid=card-kpis] >> text=úteis')
  await expect(kpi).toBeVisible()
  const box = await kpi.boundingBox(), card = await page.getByTestId('card-kpis').boundingBox()
  expect(box!.x + box!.width).toBeLessThanOrEqual(card!.x + card!.width)
})
