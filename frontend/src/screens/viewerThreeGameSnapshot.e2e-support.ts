/** 試験専用。同じDOMで全表示と保存時刻が揃った瞬間だけ採る。 */
export type ViewerSnapshotExpectation = {
  wave: number
  result: string
  balls: string
  strikes: string
}
export type CompleteViewerSnapshot = {
  at: number
  savedAt: string
  score: string
  status: string
  history: string[]
  lineup: string[]
}
export const observeCompleteViewerSnapshot: (
  expected: ViewerSnapshotExpectation,
) => Promise<CompleteViewerSnapshot> = (expected) =>
  new Promise<{
    at: number
    savedAt: string
    score: string
    status: string
    history: string[]
    lineup: string[]
  }>((resolve, reject) => {
    const normalized = (value: string | null | undefined) =>
      value?.replace(/\s+/g, ' ').trim() ?? ''
    const text = (id: string) =>
      normalized(document.querySelector(`[data-testid="${id}"]`)?.textContent)
    const items = (id: string) =>
      [...document.querySelectorAll(`[data-testid="${id}"] ol > li`)].map(
        (node) => normalized(node.textContent),
      )
    function check() {
      const status = text('viewer-status')
      const score = text('viewer-score')
      const history = items('viewer-history')
      const lineup = items('viewer-lineup')
      const savedAt = text('viewer-saved-at')
      if (
        status !== '更新済み' ||
        !savedAt ||
        savedAt === '未取得' ||
        !score.includes('先攻 0 – 後攻 0') ||
        !score.includes('1回表') ||
        !score.includes('0アウト') ||
        !score.includes('走者: なし') ||
        !score.includes(
          `${expected.balls}ボール ${expected.strikes}ストライク`,
        ) ||
        history.length !== expected.wave ||
        lineup.length !== 18 ||
        lineup.some((label) => label.length === 0) ||
        !history[expected.wave - 1]?.includes(
          `第${expected.wave}球: ${expected.result}`,
        )
      )
        return
      const at = Date.now()
      observer.disconnect()
      window.clearTimeout(timer)
      resolve({ at, savedAt, status, score, history, lineup })
    }
    const observer = new MutationObserver(check)
    const timer = window.setTimeout(() => {
      observer.disconnect()
      reject(new Error('閲覧全表示の同時成立が未達'))
    }, 120_000)
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
    })
    check()
  })
