import { domainOperations } from './publicApi'

// ステップ 6 の単一 IIFE が公開する入口。
const domainGlobal: typeof globalThis & {
  PitchlogDomain?: typeof domainOperations
} = globalThis
domainGlobal.PitchlogDomain = domainOperations
