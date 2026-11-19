import fs from 'node:fs'
import path from 'node:path'

// cada execução começa com cache e resultados do e2e vazios: o teste de PATCH não suja o cache nem results/ reais
export default function globalSetup() {
  const root = path.resolve(import.meta.dirname, '..', 'test-results')
  fs.rmSync(path.join(root, 'e2e-cache'), { recursive: true, force: true })
  fs.rmSync(path.join(root, 'e2e-results'), { recursive: true, force: true })
  fs.mkdirSync(root, { recursive: true })
}
