type Row = { amount: bigint; active: boolean; code: string }

export const definition = (row: Row, threshold: bigint): string =>
  row.active && row.amount >= threshold ? 'accepted' : 'rejected'
