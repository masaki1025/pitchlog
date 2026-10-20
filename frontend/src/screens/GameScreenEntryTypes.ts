import { getActivePinia } from 'pinia'
import type { RouteLocationNormalizedLoaded } from 'vue-router'
import { canonicalUuid } from '../api/authIntent'
import { pinia } from '../appProviders'
import type { useAuthStore } from '../stores/authStore'

export type EntryStatus = 'ready' | 'pending' | 'denied' | 'failed'
export interface EntrySupply<T> {
  tenantId: string
  authEpoch: number
  path: string
  requestKey?: string | null
  status: EntryStatus
  data?: T
}

export interface EntryDatum<T> {
  status: EntryStatus
  value?: T
}

export interface GameListItem {
  gameId: string
  tenantId: string
  label: string
  stateLabel: string
}

export interface GameListPage {
  items: readonly GameListItem[]
  pageLabel: string
  previousKey: string | null
  nextKey: string | null
}

export type ExistingGameState =
  'draft' | 'in-progress' | 'suspended' | 'finished' | 'unknown'

export interface StartCandidate {
  gameId: string
  tenantId: string
  label: string
  lineup: EntryDatum<string>
  rules: EntryDatum<string>
  recordingRight: 'held' | 'denied' | 'unknown'
  existingState: ExistingGameState
}

export interface RecordDetail extends StartCandidate {
  draftRestoration: EntryDatum<string>
}

export type PremiseStatus = 'met' | 'unmet' | 'unknown'
export interface EntryEnvironment {
  premises: { 1: PremiseStatus; 5: PremiseStatus; 6: PremiseStatus }
  persistence: 'granted' | 'denied' | 'unknown'
  queuedCount: number | null
}

type AuthStore = ReturnType<typeof useAuthStore>

/** 異なる認証世代・tenant・経路・ページ要求の旧応答を表示へ採用しない。 */
export function currentEntrySupply<T>(
  supply: EntrySupply<T> | null | undefined,
  auth: AuthStore,
  route: RouteLocationNormalizedLoaded,
  requestKey?: string | null,
): EntrySupply<T> | null {
  if (
    !supply ||
    getActivePinia() !== pinia ||
    !auth.hasHydrated ||
    !auth.isAuthenticated ||
    auth.teamId === null ||
    !canonicalUuid.test(auth.teamId) ||
    supply.tenantId !== auth.teamId ||
    supply.authEpoch !== auth.authEpoch ||
    supply.path !== route.path ||
    (requestKey !== undefined && (supply.requestKey ?? null) !== requestKey)
  )
    return null
  return supply
}

export function isStartCandidate(
  value: StartCandidate,
  tenantId: string,
): boolean {
  return (
    typeof value === 'object' &&
    value !== null &&
    canonicalUuid.test(value.gameId) &&
    value.tenantId === tenantId &&
    typeof value.label === 'string' &&
    isDatum(value.lineup) &&
    isDatum(value.rules) &&
    ['held', 'denied', 'unknown'].includes(value.recordingRight) &&
    ['draft', 'in-progress', 'suspended', 'finished', 'unknown'].includes(
      value.existingState,
    )
  )
}

export function areStartCandidates(
  values: readonly StartCandidate[],
  tenantId: string,
): boolean {
  if (!Array.isArray(values)) return false
  for (let index = 0; index < values.length; index += 1) {
    if (
      !Object.hasOwn(values, index) ||
      !isStartCandidate(values[index]!, tenantId)
    )
      return false
  }
  return true
}

function isDatum(value: EntryDatum<string>): boolean {
  return (
    typeof value === 'object' &&
    value !== null &&
    ['ready', 'pending', 'denied', 'failed'].includes(value.status) &&
    (value.status !== 'ready' || typeof value.value === 'string')
  )
}

export function isGameListPage(value: GameListPage, tenantId: string): boolean {
  if (
    typeof value !== 'object' ||
    value === null ||
    !Array.isArray(value.items) ||
    typeof value.pageLabel !== 'string' ||
    (value.previousKey !== null && typeof value.previousKey !== 'string') ||
    (value.nextKey !== null && typeof value.nextKey !== 'string')
  )
    return false
  for (let index = 0; index < value.items.length; index += 1) {
    if (!Object.hasOwn(value.items, index)) return false
    const item = value.items[index]
    if (
      typeof item !== 'object' ||
      item === null ||
      !canonicalUuid.test(item.gameId) ||
      item.tenantId !== tenantId ||
      typeof item.label !== 'string' ||
      typeof item.stateLabel !== 'string'
    )
      return false
  }
  return true
}

export function isRecordDetail(value: RecordDetail, tenantId: string): boolean {
  return isStartCandidate(value, tenantId) && isDatum(value.draftRestoration)
}

export function entryStatusLabel(status: EntryStatus | undefined): string {
  if (status === 'pending') return '確認中'
  if (status === 'denied') return 'この試合の情報を確認できません'
  if (status === 'failed') return '読み取れません'
  return '未取得'
}

export function datumLabel(datum: EntryDatum<string> | undefined): string {
  return datum?.status === 'ready' && typeof datum.value === 'string'
    ? datum.value
    : entryStatusLabel(datum?.status)
}

export function existingStateLabel(state: unknown): string {
  const labels: Record<ExistingGameState, string> = {
    draft: '準備中',
    'in-progress': '進行中',
    suspended: '中断中',
    finished: '終了',
    unknown: '未取得',
  }
  return typeof state === 'string' && Object.hasOwn(labels, state)
    ? labels[state as ExistingGameState]
    : '未取得'
}
