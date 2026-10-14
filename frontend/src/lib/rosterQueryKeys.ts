export const rosterQueryKeys = {
  teamRecords: {
    all: (teamId: string) => ['team-records', teamId] as const,
    pages: (teamId: string | null, authEpoch: number, limit: number) =>
      [
        'team-records',
        teamId,
        'pages',
        { authEpoch, includeHidden: false, limit },
      ] as const,
  },
  players: {
    all: (teamId: string) => ['players', teamId] as const,
    pages: (
      teamId: string | null,
      authEpoch: number,
      teamRecordId: string | null,
      limit: number,
    ) =>
      [
        'players',
        teamId,
        'pages',
        { authEpoch, includeHidden: false, limit, teamRecordId },
      ] as const,
  },
} as const
