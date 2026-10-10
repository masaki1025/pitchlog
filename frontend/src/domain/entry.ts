import { domainOperations } from './publicApi'

// ステップ 6 の単一 IIFE が公開する入口。
;(globalThis as { PitchlogDomain?: typeof domainOperations }).PitchlogDomain =
  domainOperations
