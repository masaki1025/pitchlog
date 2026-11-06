import type { Runners } from './stateTypes'

/** 起点塁の占有を既存8値から読む。 */
export function hasRunner(runners: Runners, base: bigint): boolean {
  if (runners === 'loaded') return true
  if (base === 1n)
    return (
      runners === 'first' ||
      runners === 'first-second' ||
      runners === 'first-third'
    )
  if (base === 2n)
    return (
      runners === 'second' ||
      runners === 'first-second' ||
      runners === 'second-third'
    )
  return (
    runners === 'third' ||
    runners === 'first-third' ||
    runners === 'second-third'
  )
}
