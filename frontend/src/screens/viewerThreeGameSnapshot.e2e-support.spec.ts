import { afterEach, describe, expect, it, vi } from 'vitest'
import { observeCompleteViewerSnapshot } from './viewerThreeGameSnapshot.e2e-support'

const completeScore =
  '先攻 0 – 後攻 0 / 1回表 / 0アウト / 1ボール 0ストライク / 走者: なし'
const expected = {
  wave: 1,
  result: 'batting-result.ball',
  balls: '1',
  strikes: '0',
}
function markup(score: string, status = '更新済み', count = 18) {
  document.body.innerHTML = `<p data-testid="viewer-status">${status}</p>
    <p data-testid="viewer-score">${score}</p><p data-testid="viewer-saved-at">2026-11-08T00:00:00.000Z</p>
    <section data-testid="viewer-lineup"><ol>${'<li>選手</li>'.repeat(count)}</ol></section>
    <section data-testid="viewer-history"><ol><li>第1球: batting-result.ball</li></ol></section>`
}
afterEach(() => {
  vi.useRealTimers()
  document.body.innerHTML = ''
})

describe('全表示同時snapshotの計時', () => {
  it('全表示が同時に揃ったときの保存時刻・全値・観測時刻を返す', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-11-08T00:00:05.000Z'))
    markup(completeScore)
    const snapshot = await observeCompleteViewerSnapshot(expected)
    expect(snapshot.at - Date.parse(snapshot.savedAt)).toBe(5000)
    expect(snapshot.score).toBe(completeScore)
    expect(snapshot.history).toEqual(['第1球: batting-result.ball'])
    expect(snapshot.lineup).toHaveLength(18)
  })
  it.each([
    ['score', completeScore.replace('先攻 0', '先攻 1')],
    ['inning', completeScore.replace('1回表', '1回裏')],
    ['outs', completeScore.replace('0アウト', '1アウト')],
    ['count', completeScore.replace('1ボール', '0ボール')],
    ['runners', completeScore.replace('走者: なし', '走者: 1塁')],
  ])(
    '履歴だけ5秒で見えても%sが20秒なら20秒として検出する',
    async (_field, partial) => {
      vi.useFakeTimers()
      vi.setSystemTime(new Date('2026-11-08T00:00:05.000Z'))
      markup(partial)
      const done = vi.fn()
      const promise = observeCompleteViewerSnapshot(expected).then((value) => {
        done()
        return value
      })
      await vi.advanceTimersByTimeAsync(14_999)
      expect(done).not.toHaveBeenCalled()
      await vi.advanceTimersByTimeAsync(1)
      document.querySelector('[data-testid="viewer-score"]')!.textContent =
        completeScore
      const snapshot = await promise
      expect(snapshot.at - Date.parse(snapshot.savedAt)).toBe(20_000)
      expect(snapshot.at - Date.parse(snapshot.savedAt)).toBeGreaterThan(10_000)
    },
  )
  it.each(['status', 'lineup'])(
    '全scoreが見えても%s欠落時は観測完了にしない',
    async (field) => {
      vi.useFakeTimers()
      vi.setSystemTime(new Date('2026-11-08T00:00:05.000Z'))
      markup(
        completeScore,
        field === 'status' ? '未更新' : '更新済み',
        field === 'lineup' ? 17 : 18,
      )
      const done = vi.fn()
      const promise = observeCompleteViewerSnapshot(expected).then((value) => {
        done()
        return value
      })
      await vi.advanceTimersByTimeAsync(15_000)
      expect(done).not.toHaveBeenCalled()
      if (field === 'status')
        document.querySelector('[data-testid="viewer-status"]')!.textContent =
          '更新済み'
      else
        document
          .querySelector('[data-testid="viewer-lineup"] ol')!
          .append(
            Object.assign(document.createElement('li'), {
              textContent: '選手',
            }),
          )
      const snapshot = await promise
      expect(snapshot.at - Date.parse(snapshot.savedAt)).toBe(20_000)
    },
  )
})
