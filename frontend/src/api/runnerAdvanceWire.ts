import type { RunnerAdvanceOverride } from '../domain/battedHit'

/** V7観測の既存not-appliedと、記録者が確認した明示進塁の候補。 */
export type RunnerAdvanceOverridesByRunner =
  | { kind: 'not-applied'; overrides: readonly [] }
  | {
      kind: 'applied'
      overrides: ReadonlyArray<RunnerAdvanceOverride>
    }
