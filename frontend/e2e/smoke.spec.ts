import { expect, test } from '@playwright/test'
import { openSample } from './helpers'

test('biblioteca lista as amostras dos datasets e filtra', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByTestId('lib-row').first()).toBeVisible()
  const total = await page.getByTestId('lib-row').count()
  expect(total).toBeGreaterThan(50)
  for (const ds of ['swe-rebench', 'swe-smith', 'codetracebench', 'ark']) await expect(page.locator(`[data-testid=lib-row][data-dataset="${ds}"]`).first()).toBeVisible()
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

// ---------------------------------------------------------------- 2ª revisão
const zoomOf = async (page: import('@playwright/test').Page) => {
  const t = (await page.locator('.react-flow__viewport').getAttribute('style')) ?? ''
  return Number(t.match(/scale\(([\d.]+)\)/)?.[1] ?? 0)
}

test('upload de log genérico: formato generic_chat, agente "desconhecido" e título = nome do arquivo', async ({ page }) => {
  await page.goto('/')
  await page.waitForSelector('[data-testid=lib-row]')
  await page.getByTestId('file-input').setInputFiles('../backend/tests/fixtures/generic_calc.json')
  await page.waitForSelector('[data-testid=step-node]')
  await expect(page.getByTestId('traj-title')).toHaveText('generic_calc')
  await expect(page.getByTestId('format-badge')).toContainText('generic_chat')
  await expect(page.getByTestId('traj-header')).toContainText('desconhecido')
  await expect(page.getByTestId('traj-header')).not.toContainText('OpenHands')
  await expect(page.getByTestId('n-steps')).toHaveText('10')
})

test('404 mostra "reabra pela biblioteca"; falha de rede é outra tela', async ({ page }) => {
  await page.goto('/t/0000000000000000')
  await expect(page.getByTestId('not-found')).toContainText('Trajetória não encontrada — reabra pela biblioteca')
  await expect(page.getByTestId('network-error')).toHaveCount(0)
  await page.route('**/api/trajectories/**', (r) => r.abort())
  await page.goto('/t/1111111111111111')
  await expect(page.getByTestId('network-error')).toContainText('API indisponível')
  await expect(page.getByTestId('not-found')).toHaveCount(0)
})

test('tema escuro: o nó "Entregar" não some no fundo escuro', async ({ page }) => {
  await openSample(page, 'swe-rebench')
  const n = Number(((await page.getByTestId('n-steps').textContent()) ?? '0').replace(/\D/g, ''))
  await page.goto(page.url().split('?')[0] + `?step=${n - 1}`)  // o último passo (finish) é o nó "Entregar"; a vista centraliza nele
  await page.waitForSelector('[data-testid=step-node][data-kind=submit]')
  await page.getByTestId('theme-toggle').click()
  await expect(page.locator('html')).toHaveClass(/dark/)
  const bg = await page.locator('[data-testid=step-node][data-kind=submit]').first().evaluate((e) => getComputedStyle(e).backgroundColor)
  expect(bg).not.toBe('rgb(34, 34, 34)')  // #222 → variante clara no escuro
  const [r, g, b] = bg.match(/\d+/g)!.map(Number)
  expect((r + g + b) / 3).toBeGreaterThan(180)
  await page.getByTestId('theme-toggle').click()
  const light = await page.locator('[data-testid=step-node][data-kind=submit]').first().evaluate((e) => getComputedStyle(e).backgroundColor)
  expect(light).toBe('rgb(34, 34, 34)')
})

test('SWE-smith: um único selo "não validado" no cabeçalho', async ({ page }) => {
  await openSample(page, 'swe-smith')
  await expect(page.getByTestId('outcome-badge')).toHaveText('não validado')
  const n = await page.getByTestId('traj-header').getByText('não validado').count()
  expect(n).toBe(1)
})

test('Enquadrar respeita o zoom mínimo legível; esconde observações em barras', async ({ page }) => {
  await page.goto('/')
  await page.getByTestId('lib-search').fill('fix-ocaml-gc')
  await page.locator('[data-testid=lib-row]').first().click()  // 141 passos
  await page.waitForSelector('[data-testid=step-node]')
  await page.waitForTimeout(500)
  expect(await zoomOf(page)).toBeGreaterThanOrEqual(0.74)
  await page.getByTestId('fit').click()
  await page.waitForTimeout(500)
  expect(await zoomOf(page)).toBeGreaterThanOrEqual(0.74)
  await page.getByTestId('tab-dashboard').click()
  await expect(page.locator('[data-testid=chart-obs] .recharts-bar-rectangle').first()).toBeVisible()
  await expect(page.locator('[data-testid=chart-obs] .recharts-line')).toHaveCount(0)  // sem curva suavizada
})

test('Ark: observação não registrada mostra o aviso; a edição mostra o diff; upload de .log', async ({ page }) => {
  await openSample(page, 'ark')
  await expect(page.getByTestId('traj-header')).toContainText('Ark')
  await expect(page.getByTestId('traj-header')).toContainText('claude-haiku-5-5')
  const base = page.url().split('?')[0]
  await page.goto(`${base}?step=1`) // read_file: o Ark não grava a saída
  await expect(page.getByTestId('observation-unrecorded')).toHaveText('saída não registrada pelo trace do Ark')
  await expect(page.getByTestId('observation')).toHaveCount(0)
  await page.goto(`${base}?step=2`) // edit_file: diff registrado
  await expect(page.getByTestId('observation')).toContainText('--- a/')
  await page.goto('/')
  await page.waitForSelector('[data-testid=lib-row]')
  await page.getByTestId('file-input').setInputFiles('../backend/tests/fixtures/ark/bugfix_002_order_totals__claude-haiku-5-5__reject-first__1.log')
  await page.waitForSelector('[data-testid=step-node]')
  await expect(page.getByTestId('format-badge')).toContainText('ark_trace')
  await expect(page.getByTestId('n-steps')).toHaveText('9')
})
