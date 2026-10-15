// 両経路の比較は、数値型を拒否し、object のキーを再帰的に辞書順へ並べる。
// 配列順を保持した JSON.stringify の UTF-8 バイト列を唯一の正規形とする。
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

export function canonicalJson(value) {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') {
    return JSON.stringify(value)
  }
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`
  if (typeof value !== 'object') throw new TypeError('JSON 数値型を含められない')
  return `{${
    Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`)
      .join(',')
  }}`
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const document = JSON.parse(readFileSync(0, 'utf8'))
  process.stdout.write(canonicalJson(document))
}
