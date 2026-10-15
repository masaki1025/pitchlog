import { readFileSync } from 'node:fs'

// 合成 TS 正本だけを Node で実行し、DB の結果と比較する試験補助。
const fixtures = {
  aggregate: new URL('./fixtures/aggregate.ts', import.meta.url),
  classify: new URL('./fixtures/classify.ts', import.meta.url),
}

const mode = process.argv[2]
if (!Object.hasOwn(fixtures, mode)) throw new Error('未知の合成操作')
const source = await import(fixtures[mode].href)
const input = JSON.parse(readFileSync(0, 'utf8'))
const rows = input.rows.map((row) => ({ ...row, amount: BigInt(row.amount) }))
const threshold = BigInt(input.bindings.threshold)

if (mode === 'aggregate') {
  let count = 0n
  let sum = 0n
  for (const row of rows) {
    if (source.definition.count(row, threshold)) count += 1n
    sum += source.definition.sum(row, threshold)
  }
  process.stdout.write(
    `${JSON.stringify({ count: count.toString(), sum: sum.toString() })}\n`,
  )
} else {
  const values = rows.map((row) => source.definition(row, threshold))
  process.stdout.write(`${JSON.stringify(values)}\n`)
}
