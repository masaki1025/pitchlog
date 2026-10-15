type Row = { amount: bigint; active: boolean; code: string }

export const definition = {
  count: (row: Row, threshold: bigint): boolean =>
    row.active && row.amount >= threshold,
  sum: (row: Row, threshold: bigint): bigint =>
    row.active && row.amount >= threshold ? row.amount : 0n,
}
