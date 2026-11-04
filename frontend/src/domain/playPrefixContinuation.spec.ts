import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import vm from 'node:vm'
import { describe, expect, it } from 'vitest'
import { domainOperations } from './publicApi'

const vectors = JSON.parse(
  readFileSync(
    resolve(
      process.cwd(),
      '../contracts/state-transition/play_prefix_v2_cases.json',
    ),
    'utf8',
  ),
)
const cross = JSON.parse(
  readFileSync(
    resolve(
      process.cwd(),
      '../contracts/state-transition/terminal_pitch_cases_v1.json',
    ),
    'utf8',
  ),
).crossProduct
const context = vm.createContext({})
vm.runInContext(
  readFileSync(
    resolve(process.cwd(), 'public/domain/pitchlog-domain.js'),
    'utf8',
  ),
  context,
)
const callers = {
  source: domainOperations.derivePlayPrefixWithContinuation,
  artifact: (text: string): string =>
    vm.runInContext(
      `PitchlogDomain.derivePlayPrefixWithContinuation(${JSON.stringify(text)})`,
      context,
    ) as string,
}
for (const [name, call] of Object.entries(callers))
  describe(`v2 ${name}`, () => {
    const invoke = (request: unknown) =>
      JSON.parse(call(JSON.stringify(request)))
    it('BB/HBP15・後続ordinary37・責任投手4の56全値', () => {
      expect(vectors.cases).toHaveLength(56)
      for (const c of vectors.cases)
        expect(invoke(c.request), c.caseId).toEqual(c.expected)
    })
    it('42拒否とraw2拒否', () => {
      for (const c of vectors.rejectionCases) {
        const q = structuredClone(
          vectors.cases.find(
            (r: { caseId: string }) => r.caseId === c.baseCaseId,
          ).request,
        )
        let target = q
        for (const key of c.path.slice(0, -1)) target = target[key]
        target[c.path.at(-1)] = c.value
        expect(invoke(q), c.caseId).toEqual(c.expected)
      }
      for (const c of vectors.rawRejections)
        expect(JSON.parse(call(c.requestJson))).toEqual(c.expected)
    })
    it('terminal実応答をordinaryへ接続して帰属/今回1entryを保つ', () => {
      for (const index of [0, 52]) {
        const terminal = invoke(vectors.cases[index].request).value
        const q = structuredClone(vectors.cases[15].request),
          expected = structuredClone(vectors.cases[15].expected)
        q.prefixRef = terminal.nextPrefixRef
        q.t1.before = terminal.t1.after
        Object.assign(q.source, {
          prefixRef: terminal.nextPrefixRef,
          after: terminal.t1.after,
          t2: terminal.t2,
          runners: terminal.runners,
          participants: terminal.participants,
          lastSource: terminal.playIdentity,
          historyDepth: terminal.nextPrefixRef.length,
          playCount: terminal.nextPrefixRef.length,
        })
        const normativeTerminal = vectors.cases[index].expected.value
        expected.value.previousPrefixRef = structuredClone(
          normativeTerminal.nextPrefixRef,
        )
        expected.value.nextPrefixRef = Object.assign(
          structuredClone(normativeTerminal.nextPrefixRef),
          {
            length: (
              BigInt(normativeTerminal.nextPrefixRef.length) + 1n
            ).toString(),
            historyVersion: (
              BigInt(normativeTerminal.nextPrefixRef.historyVersion) + 1n
            ).toString(),
            checkpoint: q.nextCheckpoint,
          },
        )
        expected.value.runners = normativeTerminal.runners
        const actual = invoke(q)
        expect(actual).toEqual(expected)
        expect(actual.value).not.toHaveProperty('historyContext')
        expect(actual.value.t1).not.toHaveProperty('historyContext')
      }
    })
    it('確認済v2 sourceのouts/表裏/打順810交差', () => {
      let count = 0
      for (const row of vectors.cases.slice(0, 15))
        for (const outs of cross.outs)
          for (const half of cross.half)
            for (const order of cross.battingOrder) {
              const q = structuredClone(row.request),
                e = structuredClone(row.expected)
              q.prefixRef.origin.length = '0'
              q.prefixRef.length = '9'
              q.prefixRef.historyVersion = '10'
              q.prefixRef.checkpoint.revision = '10'
              q.nextCheckpoint.revision = '11'
              Object.assign(q.t1.before.stateFields, {
                'state.outs': outs,
                'state.half': half,
                'state.battingOrder': order,
              })
              Object.assign(q.source, {
                kind: 'evaluated-prefix-v2',
                prefixRef: structuredClone(q.prefixRef),
                after: structuredClone(q.t1.before),
                bridge: null,
                historyDepth: '9',
                playCount: '9',
                lastSource: structuredClone(
                  vectors.cases[0].request.source.lastSource,
                ),
                t2: structuredClone(row.expected.value.t2),
              })
              q.source.t2.basis.half = half
              q.source.participants.battingOrder = order
              q.source.nextBatter.battingOrder = cross.nextBattingOrder[order]
              e.value.previousPrefixRef = structuredClone(q.prefixRef)
              e.value.nextPrefixRef = Object.assign(
                structuredClone(q.prefixRef),
                {
                  length: '10',
                  historyVersion: '11',
                  checkpoint: q.nextCheckpoint,
                },
              )
              Object.assign(e.value.t1.after.stateFields, {
                'state.outs': outs,
                'state.half': half,
                'state.battingOrder': cross.nextBattingOrder[order],
              })
              e.value.t2.basis.half = half
              e.value.participants.battingOrder = cross.nextBattingOrder[order]
              e.value.newHistoryEntry.difference.stateFields[
                'state.battingOrder'
              ] = { before: order, after: cross.nextBattingOrder[order] }
              expect(invoke(q)).toEqual(e)
              count += 1
            }
      expect(count).toBe(810)
    })
    it('ordinary37の全8占有をcanonical v2と実runnerへ対応し旧loadedを外へ漏らさない', () => {
      for (const row of vectors.cases.slice(15, 52))
        for (const bases of [
          [],
          ['1'],
          ['2'],
          ['3'],
          ['1', '2'],
          ['1', '3'],
          ['2', '3'],
          ['1', '2', '3'],
        ]) {
          const q = structuredClone(row.request),
            e = structuredClone(row.expected)
          const names: Record<string, string> = {
            '1': 'first',
            '2': 'second',
            '3': 'third',
          }
          const state =
            bases.length === 0 ? 'empty' : bases.map((b) => names[b]).join('-')
          const runners = bases.map((b) => ({
            runnerId: `10000000-0000-0000-0000-00000000010${b}`,
            responsiblePitcherId: `10000000-0000-0000-0000-00000000020${b}`,
            base: b,
            status: '継続',
            statusSource: 'auto',
          }))
          q.t1.before.stateFields['state.runners'] = state
          q.source.after = structuredClone(q.t1.before)
          q.source.runners = runners
          e.value.t1.after.stateFields['state.runners'] = state
          e.value.runners = runners
          for (const [base, name] of Object.entries(names))
            e.value.t1.runnerDefaultAdvance[name] = {
              modality: bases.includes(base) ? 'hold' : 'not-applicable',
              destination: null,
            }
          expect(invoke(q)).toEqual(e)
        }
    })
    it('規定回/延長/TB/coldを共通T2核で実評価する', () => {
      for (const data of [
        {
          inning: '9',
          half: 'top',
          home: '6',
          away: '7',
          extension: '9',
          tb: null,
          active: false,
          cold: [],
          branches: [],
        },
        {
          inning: '9',
          half: 'bottom',
          home: '6',
          away: '7',
          extension: '9',
          tb: null,
          active: false,
          cold: [],
          branches: [],
        },
        {
          inning: '10',
          half: 'top',
          home: '7',
          away: '7',
          extension: '20',
          tb: {
            startInning: '10',
            runnerPlacement: 'second',
            leadoffRule: 'continue',
          },
          active: true,
          cold: [],
          branches: [],
        },
        {
          inning: '4',
          half: 'top',
          home: '0',
          away: '5',
          extension: '9',
          tb: null,
          active: false,
          cold: [{ pointDifference: '5', startInning: '3' }],
          branches: ['COLD-04'],
        },
      ]) {
        const q = structuredClone(vectors.cases[15].request),
          e = structuredClone(vectors.cases[15].expected)
        Object.assign(q.rules, {
          extensionLimit: data.extension,
          tiebreak: data.tb,
          coldConditions: data.cold,
        })
        q.source.rules = structuredClone(q.rules)
        for (const s of [q.t1.before, e.value.t1.after]) {
          Object.assign(s.stateFields, {
            'state.inning': data.inning,
            'state.half': data.half,
            'state.score': { home: data.home, away: data.away },
            'state.tiebreakActive': data.active,
          })
          s.scoreboard.inningScores = { home: data.home, away: data.away }
        }
        q.source.after = structuredClone(q.t1.before)
        for (const t2 of [q.source.t2, e.value.t2])
          Object.assign(t2.basis, {
            inning: data.inning,
            half: data.half,
            tiebreakActive: data.active,
            coldBranches: data.branches,
            configuredExtensionLimit: data.extension,
          })
        expect(invoke(q)).toEqual(e)
      }
      for (const kind of ['walk-off', 'tb', 'extension', 'cold']) {
        const q = structuredClone(vectors.cases[15].request)
        if (kind === 'walk-off') {
          Object.assign(q.t1.before.stateFields, {
            'state.inning': '9',
            'state.half': 'bottom',
            'state.score': { home: '1', away: '0' },
          })
          q.t1.before.scoreboard.inningScores = { home: '1', away: '0' }
        }
        if (kind === 'cold') {
          Object.assign(q.t1.before.stateFields, {
            'state.inning': '4',
            'state.half': 'bottom',
            'state.score': { home: '5', away: '0' },
          })
          q.t1.before.scoreboard.inningScores = { home: '5', away: '0' }
          q.rules.coldConditions = [{ pointDifference: '5', startInning: '3' }]
        }
        if (kind === 'tb')
          q.t1.before.stateFields['state.tiebreakActive'] = true
        if (kind === 'extension') q.t1.before.stateFields['state.inning'] = '10'
        q.source.after = structuredClone(q.t1.before)
        q.source.rules = structuredClone(q.rules)
        expect(invoke(q), kind).toEqual({
          ok: false,
          error: { code: 'T2_NOT_EVALUATED' },
        })
      }
    })
  })
