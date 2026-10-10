export interface TeamSearchModel {
  options: string[]
  matchCount: number
  selectionTarget?: string
}

export function normalizeTeamSearch(value: string): string {
  const normalized = value.normalize('NFKC').toLocaleLowerCase('ja')
  return normalized.replace(/\s+/g, '')
}

export function buildTeamSearchModel(
  teams: readonly string[],
  query: string,
): TeamSearchModel {
  const uniqueTeams: string[] = []
  const seenTeams = new Set<string>()

  // 名前の重複は正規化前に判定し、最初に現れた順序を保つ。
  for (const team of teams) {
    if (team === '' || seenTeams.has(team)) continue
    seenTeams.add(team)
    uniqueTeams.push(team)
  }

  const normalizedQuery = normalizeTeamSearch(query)
  const options =
    normalizedQuery === ''
      ? uniqueTeams
      : uniqueTeams.filter((team) =>
          normalizeTeamSearch(team).includes(normalizedQuery),
        )

  // 完全一致を先に選び、一致がなければ単独候補だけを確定候補にする。
  let selectionTarget: string | undefined
  if (normalizedQuery !== '') {
    selectionTarget = options.find(
      (team) => normalizeTeamSearch(team) === normalizedQuery,
    )
  }
  if (selectionTarget === undefined && options.length === 1) {
    selectionTarget = options[0]
  }

  return { options, matchCount: options.length, selectionTarget }
}
