/** 'YYYY-MM-DD'（input[type=date]）→ 'YYYY/MM/DD'（88列契約の試合日時形式） */
export function isoToSlashDate(iso: string): string {
  return iso.replaceAll('-', '/')
}

export function todayIso(): string {
  const d = new Date()
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${mm}-${dd}`
}

/** className 結合ヘルパー */
export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(' ')
}
