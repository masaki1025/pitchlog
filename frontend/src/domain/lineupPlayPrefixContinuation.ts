import { applyGameLifecycle } from './gameLifecycle'
import { walkResponsiblePitcher } from './substitutionKernel'
import { formatDecimalInteger, parseDecimalInteger } from './decimalCodec'
import { readContinuationRules } from './firstPitchContinuation'
import { evaluateEndCondition, validEndRules } from './endConditionCore'
import {
  canonicalContinuationUuid,
  canonicalContinuationGeneration,
  sameContinuationValue,
} from './ordinaryPitchContinuation'

type Json = Record<string, unknown>
type Prepared =
  | { ok: true; request: Json; t1: Json; battedHit: boolean }
  | { ok: false; response: string }
/** 閉shapeを再検証し、余剰/欠落を補完しない。 */
function object(value: unknown, keys: Array<string>): Json | null {
  if (value === null || typeof value !== 'object' || Array.isArray(value))
    return null
  const v = value as Json
  if (
    !Object.keys(v).every((k) => keys.includes(k)) ||
    !keys.every((k) => Object.prototype.hasOwnProperty.call(v, k))
  )
    return null
  return v
}
function read(v: Json, key: string): unknown {
  for (const p of Object.entries(v))
    if (p.slice().shift() === key) return p.slice().pop()
  return null
}
function unsigned(v: unknown): bigint | null {
  if (typeof v !== 'string' || v.startsWith('-')) return null
  const n = parseDecimalInteger(v)
  if (n === null || n < 0n) return null
  return n
}
function digest(v: unknown): boolean {
  if (typeof v !== 'string') return false
  let n = 0n
  for (const c of v) {
    if (!((c >= 'a' && c <= 'f') || (c >= '0' && c <= '9'))) return false
    n = n + 1n
  }
  return n === 64n
}
function checkpoint(v: unknown): Json | null {
  const c = object(v, ['id', 'revision', 'digest'])
  if (c === null || !canonicalContinuationUuid(c.id) || !digest(c.digest))
    return null
  const n = unsigned(c.revision)
  if (n === null || n < 1n) return null
  return c
}
function identity(v: unknown): Json | null {
  const c = object(v, ['eventId', 'd5', 'playId'])
  if (c === null || !Object.values(c).every(canonicalContinuationUuid))
    return null
  return c
}
function prefix(v: unknown): Json | null {
  const r = object(v, [
    'version',
    'scope',
    'tenantId',
    'gameId',
    'generation',
    'length',
    'checkpoint',
    'historyVersion',
    'origin',
  ])
  if (
    r === null ||
    r.version !== '3' ||
    r.scope !== 'play-prefix-v3' ||
    !canonicalContinuationUuid(r.tenantId) ||
    !canonicalContinuationUuid(r.gameId) ||
    !canonicalContinuationGeneration(r.generation) ||
    unsigned(r.length) === null ||
    unsigned(r.historyVersion) === null ||
    checkpoint(r.checkpoint) === null
  )
    return null
  const o = object(r.origin, ['kind', 'eventId'])
  if (
    o === null ||
    o.kind !== 'started-game' ||
    !canonicalContinuationUuid(o.eventId)
  )
    return null
  return r
}
function failure(code: string): string {
  return JSON.stringify({ ok: false, error: { code: code } })
}
function reject(code: string): Prepared {
  return { ok: false, response: failure(code) }
}
/** 全配置のIDを実sourceと照合するための、閉じた名簿の外形。 */
function lineup(value: unknown, dh: boolean): Json | null {
  const l = object(value, ['away', 'home'])
  if (l === null) return null
  let teams: Array<unknown> = []
  let all: Array<unknown> = []
  for (const side of Object.values(l)) {
    const t = object(side, ['teamId', 'battingOrder', 'pitcherId', 'catcherId'])
    if (
      t === null ||
      !canonicalContinuationUuid(t.teamId) ||
      !canonicalContinuationUuid(t.pitcherId) ||
      !canonicalContinuationUuid(t.catcherId) ||
      t.pitcherId === t.catcherId ||
      teams.includes(t.teamId)
    )
      return null
    teams = teams.concat([t.teamId])
    const order = object(t.battingOrder, [
      '1',
      '2',
      '3',
      '4',
      '5',
      '6',
      '7',
      '8',
      '9',
    ])
    if (order === null) return null
    const players = Object.values(order)
    let seen: Array<unknown> = []
    for (const player of players) {
      if (
        !canonicalContinuationUuid(player) ||
        seen.includes(player) ||
        all.includes(player)
      )
        return null
      seen = seen.concat([player])
    }
    if (!players.includes(t.catcherId) || players.includes(t.pitcherId) === dh)
      return null
    if (!players.includes(t.pitcherId)) {
      if (all.includes(t.pitcherId)) return null
      seen = seen.concat([t.pitcherId])
    }
    all = all.concat(seen)
  }
  return l
}
/** next側の選択は同artifactだけが所有する。BE/UIには半回/打順算式を置かない。 */
function participant(snapshot: Json, l: Json): Json | null {
  const fields = snapshot.stateFields as Json
  let batting = l.away as Json
  let fielding = l.home as Json
  if (read(fields, 'state.half') === 'bottom') {
    batting = l.home as Json
    fielding = l.away as Json
  } else if (read(fields, 'state.half') !== 'top') return null
  const slot = read(fields, 'state.battingOrder')
  if (typeof slot !== 'string') return null
  const id = read(batting.battingOrder as Json, slot)
  if (!canonicalContinuationUuid(id)) return null
  return {
    batterId: id,
    pitcherId: fielding.pitcherId,
    catcherId: fielding.catcherId,
    battingOrder: slot,
  }
}
function people(v: unknown): Json | null {
  const p = object(v, ['batterId', 'pitcherId', 'catcherId', 'battingOrder'])
  if (
    p === null ||
    !canonicalContinuationUuid(p.batterId) ||
    !canonicalContinuationUuid(p.pitcherId) ||
    !canonicalContinuationUuid(p.catcherId)
  )
    return null
  return p
}
function responsibility(v: unknown): Json | null {
  const r = object(v, [
    'kind',
    'paStartSource',
    'previousPitcherId',
    'strikesAtChange',
    'ballsAtChange',
  ])
  if (r === null) return null
  const p = object(r.paStartSource, ['kind', 'id'])
  if (
    p === null ||
    !['started-game', 'confirmed-play'].includes(p.kind as string) ||
    !canonicalContinuationUuid(p.id)
  )
    return null
  if (r.kind === 'no-change') {
    if (
      r.previousPitcherId === null &&
      r.strikesAtChange === null &&
      r.ballsAtChange === null
    )
      return r
    return null
  }
  if (
    r.kind === 'changed-mid-plate-appearance' &&
    canonicalContinuationUuid(r.previousPitcherId) &&
    ['0', '1', '2'].includes(r.strikesAtChange as string) &&
    ['0', '1', '2', '3'].includes(r.ballsAtChange as string)
  )
    return r
  return null
}
/** T1の進塁計画を閉じた到達塁だけへ読む。 */
function runnerDestination(
  value: unknown,
): '1' | '2' | '3' | '4' | null | 'invalid' {
  const advance = object(value, ['modality', 'destination'])
  if (advance === null) return 'invalid'
  const modality = read(advance, 'modality')
  const destination = read(advance, 'destination')
  if (modality === 'not-applicable') return 'invalid'
  if (modality === 'hold') {
    if (destination === null) return null
    return 'invalid'
  }
  if (modality !== 'optional' && modality !== 'forced') return 'invalid'
  if (
    destination === '1' ||
    destination === '2' ||
    destination === '3' ||
    destination === '4'
  )
    return destination
  return 'invalid'
}

function slotForBase(value: unknown): string | null {
  if (value === '1') return 'first'
  if (value === '2') return 'second'
  if (value === '3') return 'third'
  return null
}
function runners(value: unknown, snapshot: Json): boolean {
  if (!Array.isArray(value)) return false
  const fields = snapshot.stateFields as Json
  const vocabulary = read(fields, 'state.runners')
  let bases: Array<string> = []
  if (vocabulary === 'first') bases = ['1']
  else if (vocabulary === 'second') bases = ['2']
  else if (vocabulary === 'third') bases = ['3']
  else if (vocabulary === 'first-second') bases = ['1', '2']
  else if (vocabulary === 'first-third') bases = ['1', '3']
  else if (vocabulary === 'second-third') bases = ['2', '3']
  else if (vocabulary === 'first-second-third') bases = ['1', '2', '3']
  else if (vocabulary !== 'empty') return false
  let ids: Array<unknown> = []
  for (const item of value) {
    const r = object(item, [
      'runnerId',
      'responsiblePitcherId',
      'base',
      'status',
      'statusSource',
    ])
    if (
      r === null ||
      !canonicalContinuationUuid(r.runnerId) ||
      !canonicalContinuationUuid(r.responsiblePitcherId) ||
      !bases.includes(r.base as string) ||
      ids.includes(r.runnerId) ||
      r.status !== '継続' ||
      r.statusSource !== 'auto'
    )
      return false
    ids = ids.concat([r.runnerId])
    bases = bases.filter((b) => b !== r.base)
  }
  return !bases.some(() => true)
}

/** 採用Source schemaの閉shapeだけを機械転記する。野球計算・期待caseは含まない。 */
const nonplayShapes: Json = {
  'np.LifecycleState': {
    fields: {
      status: {
        values: ['in_progress', 'finished'],
      },
      lastVersion: {
        scalar: 'unsigned',
      },
      active: {
        choices: [
          {
            type: 'null',
          },
          {
            fields: {
              version: {
                scalar: 'positive',
              },
              eventId: {
                scalar: 'uuid',
              },
              receiptId: {
                scalar: 'uuid',
              },
            },
            required: ['version', 'eventId', 'receiptId'],
          },
        ],
      },
    },
    required: ['status', 'lastVersion', 'active'],
  },
  'np.ActiveFinalization': {
    fields: {
      version: {
        scalar: 'positive',
      },
      eventId: {
        scalar: 'uuid',
      },
      receiptId: {
        scalar: 'uuid',
      },
    },
    required: ['version', 'eventId', 'receiptId'],
  },
  'np.LifecycleControlBridge': {
    fields: {
      source: {
        ref: 'np.EventSource',
      },
      action: {
        values: ['end', 'reopen'],
      },
      anchorEventId: {
        ref: 'np.Uuid',
      },
      beforeContext: {
        ref: 'np.RestoreContext',
      },
      afterContext: {
        ref: 'np.RestoreContext',
      },
      kernel: {
        fields: {
          request: {
            ref: 'gl.Request',
          },
          response: {
            ref: 'gl.Response',
          },
        },
        required: ['request', 'response'],
      },
      frameId: {
        ref: 'np.Uuid',
      },
      checkpointBefore: {
        ref: 'np.CheckpointRef',
      },
    },
    required: [
      'source',
      'action',
      'anchorEventId',
      'beforeContext',
      'afterContext',
      'kernel',
      'frameId',
      'checkpointBefore',
    ],
  },
  'gl.Request': {
    fields: {
      formatVersion: {
        constant: 'native-game-lifecycle-v1',
      },
      action: {
        values: ['end', 'reopen'],
      },
      current: {
        ref: 'np.Current',
      },
      lifecycle: {
        ref: 'np.LifecycleState',
      },
      target: {
        choices: [
          {
            type: 'null',
          },
          {
            fields: {
              version: {
                scalar: 'positive',
              },
              eventId: {
                scalar: 'uuid',
              },
              receiptId: {
                scalar: 'uuid',
              },
            },
            required: ['version', 'eventId', 'receiptId'],
          },
        ],
      },
      event: {
        fields: {
          eventId: {
            scalar: 'uuid',
          },
          receiptId: {
            scalar: 'uuid',
          },
        },
        required: ['eventId', 'receiptId'],
      },
    },
    required: [
      'formatVersion',
      'action',
      'current',
      'lifecycle',
      'target',
      'event',
    ],
  },
  'gl.Response': {
    choices: [
      {
        fields: {
          ok: {
            constant: true,
          },
          value: {
            fields: {
              current: {
                ref: 'np.Current',
              },
              lifecycle: {
                ref: 'np.LifecycleState',
              },
              stateEffect: {
                fields: {
                  gameEnded: {
                    fields: {
                      kind: {
                        values: ['unchanged', 'set'],
                      },
                      before: {
                        type: 'boolean',
                      },
                      after: {
                        type: 'boolean',
                      },
                    },
                    required: ['kind', 'before', 'after'],
                  },
                },
                required: ['gameEnded'],
              },
            },
            required: ['current', 'lifecycle', 'stateEffect'],
          },
        },
        required: ['ok', 'value'],
      },
      {
        fields: {
          ok: {
            constant: false,
          },
          error: {
            fields: {
              code: {
                values: [
                  'INVALID_JSON',
                  'INVALID_REQUEST',
                  'LIFECYCLE_STATE_MISMATCH',
                ],
              },
            },
            required: ['code'],
          },
        },
        required: ['ok', 'error'],
      },
    ],
  },
  'np.Source': {
    fields: {
      formatVersion: { constant: 'nonplay-prefix-source-v1' },
      checkpoint: { ref: 'np.Checkpoint' },
      activeStack: { items: { ref: 'np.ActiveFrame' } },
    },
    required: ['formatVersion', 'checkpoint', 'activeStack'],
  },
  'np.Checkpoint': {
    fields: {
      formatVersion: { constant: 'nonplay-prefix-checkpoint-v1' },
      ref: { ref: 'np.CheckpointRef' },
      content: { ref: 'np.Content' },
    },
    required: ['formatVersion', 'ref', 'content'],
  },
  'np.CheckpointRef': {
    fields: {
      id: { ref: 'np.Uuid' },
      revision: { ref: 'np.Positive' },
      digest: { ref: 'np.Digest' },
    },
    required: ['id', 'revision', 'digest'],
  },
  'np.Uuid': { scalar: 'uuid' },
  'np.Positive': { scalar: 'positive' },
  'np.Digest': { scalar: 'digest' },
  'np.Content': {
    fields: {
      scope: { ref: 'np.Scope' },
      origin: {
        fields: {
          kind: { constant: 'started-game' },
          eventId: { ref: 'np.Uuid' },
        },
        required: ['kind', 'eventId'],
      },
      d3: { ref: 'np.Unsigned' },
      d1Head: { choices: [{ ref: 'np.D1Head' }, { type: 'null' }] },
      projectionHead: { ref: 'np.ProjectionHead' },
      activeHead: { choices: [{ ref: 'np.ActivePlay' }, { type: 'null' }] },
      activeDepth: { ref: 'np.Unsigned' },
      historyVersion: { ref: 'np.Unsigned' },
      storageHistoryEpoch: { ref: 'np.Unsigned' },
      nextPhysicalPlayNumber: { ref: 'np.Positive' },
      executionArtifactSha256: { ref: 'np.Digest' },
      restored: { ref: 'np.RestoreContext' },
      controlBridges: { items: { ref: 'np.LifecycleControlBridge' } },
      substitutionFrames: { items: { ref: 'np.SubstitutionFrame' } },
    },
    required: [
      'scope',
      'origin',
      'd3',
      'd1Head',
      'projectionHead',
      'activeHead',
      'activeDepth',
      'historyVersion',
      'storageHistoryEpoch',
      'nextPhysicalPlayNumber',
      'executionArtifactSha256',
      'restored',
    ],
  },
  'np.Scope': {
    fields: {
      tenantId: { ref: 'np.Uuid' },
      gameId: { ref: 'np.Uuid' },
      generation: { ref: 'np.Generation' },
    },
    required: ['tenantId', 'gameId', 'generation'],
  },
  'np.Generation': { scalar: 'generation' },
  'np.Unsigned': { scalar: 'unsigned' },
  'np.D1Head': {
    fields: {
      kind: { constant: 'accepted-event' },
      source: { ref: 'np.EventSource' },
    },
    required: ['kind', 'source'],
  },
  'np.EventSource': {
    fields: {
      eventId: { ref: 'np.Uuid' },
      gameId: { ref: 'np.Uuid' },
      generation: { ref: 'np.Generation' },
      d1: { ref: 'np.Positive' },
      d5: { ref: 'np.Uuid' },
      fingerprint: { ref: 'np.Fingerprint' },
      eventKind: { values: ['play_input', 'undo', 'substitution', 'game_end_declaration', 'game_reopen'] },
    },
    required: [
      'eventId',
      'gameId',
      'generation',
      'd1',
      'd5',
      'fingerprint',
      'eventKind',
    ],
  },
  'np.Fingerprint': { scalar: 'fingerprint' },
  'np.ProjectionHead': {
    choices: [
      {
        fields: {
          kind: { constant: 'started-game' },
          eventId: { ref: 'np.Uuid' },
        },
        required: ['kind', 'eventId'],
      },
      {
        fields: {
          kind: { constant: 'd1-event' },
          source: { ref: 'np.EventSource' },
        },
        required: ['kind', 'source'],
      },
    ],
  },
  'np.ActivePlay': {
    fields: {
      source: { ref: 'np.EventSource' },
      playId: { ref: 'np.Uuid' },
      d2: { ref: 'np.Unsigned' },
      physicalPlayNumber: { ref: 'np.Positive' },
    },
    required: ['source', 'playId', 'd2', 'physicalPlayNumber'],
  },
  'np.RestoreContext': {
    fields: {
      current: { ref: 'np.Current' },
      rules: { ref: 'lp.SavedRuleWire' },
      rulesDigest: { ref: 'np.Digest' },
      layoutDigest: { ref: 'np.Digest' },
      rosterDigest: { ref: 'np.Digest' },
      lineup: { ref: 'lp.Lineup' },
      participants: { ref: 'lp.Participant' },
      runners: { items: { ref: 'lp.Runner' } },
      responsibility: { ref: 'lp.Responsibility' },
      lastPlayEvaluation: { choices: [{ ref: 'lp.T2' }, { type: 'null' }] },
      substitutionState: { ref: 'np.SubstitutionState' },
    },
    required: [
      'current',
      'rules',
      'rulesDigest',
      'layoutDigest',
      'rosterDigest',
      'lineup',
      'participants',
      'runners',
      'responsibility',
      'lastPlayEvaluation',
    ],
  },
  'np.SubstitutionFrame': {
    fields: {
      source: { ref: 'np.EventSource' },
      afterPlayId: { choices: [{ ref: 'np.Uuid' }, { type: 'null' }] },
      beforeContext: { ref: 'np.RestoreContext' },
      afterContext: { ref: 'np.RestoreContext' },
    },
    required: ['source', 'afterPlayId', 'beforeContext', 'afterContext'],
  },
  'np.SubstitutionTeam': {
    fields: {
      teamId: { ref: 'np.Uuid' },
      battingOrder: {
        fields: {
          '1': { ref: 'np.Uuid' },
          '2': { ref: 'np.Uuid' },
          '3': { ref: 'np.Uuid' },
          '4': { ref: 'np.Uuid' },
          '5': { ref: 'np.Uuid' },
          '6': { ref: 'np.Uuid' },
          '7': { ref: 'np.Uuid' },
          '8': { ref: 'np.Uuid' },
          '9': { ref: 'np.Uuid' },
        },
        required: ['1', '2', '3', '4', '5', '6', '7', '8', '9'],
      },
      fielding: {
        fields: {
          '1': { choices: [{ ref: 'np.Uuid' }, { type: 'null' }] },
          '2': { choices: [{ ref: 'np.Uuid' }, { type: 'null' }] },
          '3': { choices: [{ ref: 'np.Uuid' }, { type: 'null' }] },
          '4': { choices: [{ ref: 'np.Uuid' }, { type: 'null' }] },
          '5': { choices: [{ ref: 'np.Uuid' }, { type: 'null' }] },
          '6': { choices: [{ ref: 'np.Uuid' }, { type: 'null' }] },
          '7': { choices: [{ ref: 'np.Uuid' }, { type: 'null' }] },
          '8': { choices: [{ ref: 'np.Uuid' }, { type: 'null' }] },
          '9': { choices: [{ ref: 'np.Uuid' }, { type: 'null' }] },
        },
        required: ['1', '2', '3', '4', '5', '6', '7', '8', '9'],
      },
      dhSlot: { choices: [{ ref: 'lp.Slot' }, { type: 'null' }] },
    },
    required: ['teamId', 'battingOrder', 'fielding', 'dhSlot'],
  },
  'np.SubstitutionState': {
    fields: {
      attackingSide: { values: ['away', 'home'] },
      away: { ref: 'np.SubstitutionTeam' },
      home: { ref: 'np.SubstitutionTeam' },
      runners: { items: { ref: 'lp.Runner' } },
      exitedPlayerIds: { items: { ref: 'np.Uuid' } },
      responsibility: {
        choices: [
          { fields: { kind: { constant: 'unchanged' } }, required: ['kind'] },
          {
            fields: {
              kind: { constant: 'changed-mid-plate-appearance' },
              previousPitcherId: { ref: 'np.Uuid' },
              reliefPitcherId: { ref: 'np.Uuid' },
              strikesAtChange: { values: ['0', '1', '2'] },
              ballsAtChange: { values: ['0', '1', '2', '3'] },
            },
            required: [
              'kind',
              'previousPitcherId',
              'reliefPitcherId',
              'strikesAtChange',
              'ballsAtChange',
            ],
          },
        ],
      },
    },
    required: [
      'attackingSide',
      'away',
      'home',
      'runners',
      'exitedPlayerIds',
      'responsibility',
    ],
  },
  'np.Current': {
    fields: {
      stateFields: { ref: 'un.StateFields' },
      scoreboard: { ref: 'un.Scoreboard' },
      battingOrderBySide: { ref: 'un.BattingOrderBySide' },
    },
    required: ['stateFields', 'scoreboard', 'battingOrderBySide'],
  },
  'un.StateFields': {
    fields: {
      'state.half': { values: ['top', 'bottom'] },
      'state.count.strikes': { values: ['0', '1', '2'] },
      'state.count.balls': { values: ['0', '1', '2', '3'] },
      'state.outs': { values: ['0', '1', '2'] },
      'state.runners': {
        values: [
          'empty',
          'first',
          'second',
          'third',
          'first-second',
          'first-third',
          'second-third',
          'first-second-third',
        ],
      },
      'state.battingOrder': {
        values: ['1', '2', '3', '4', '5', '6', '7', '8', '9'],
      },
      'state.tiebreakActive': { type: 'boolean' },
      'state.gameEnded': { type: 'boolean' },
      'state.inning': { ref: 'un.CanonicalPositive' },
      'state.score': { ref: 'un.Score' },
    },
    required: [
      'state.half',
      'state.count.strikes',
      'state.count.balls',
      'state.outs',
      'state.runners',
      'state.battingOrder',
      'state.tiebreakActive',
      'state.gameEnded',
      'state.inning',
      'state.score',
    ],
  },
  'un.CanonicalPositive': { scalar: 'positive' },
  'un.Score': {
    fields: {
      home: { ref: 'un.CanonicalUnsigned' },
      away: { ref: 'un.CanonicalUnsigned' },
    },
    required: ['home', 'away'],
  },
  'un.CanonicalUnsigned': { scalar: 'unsigned' },
  'un.Scoreboard': {
    fields: {
      inningScores: { ref: 'un.Score' },
      hits: { ref: 'un.CanonicalUnsigned' },
      errors: { ref: 'un.CanonicalUnsigned' },
      strikeouts: { ref: 'un.CanonicalUnsigned' },
      walks: { ref: 'un.CanonicalUnsigned' },
    },
    required: ['inningScores', 'hits', 'errors', 'strikeouts', 'walks'],
  },
  'un.BattingOrderBySide': {
    fields: {
      away: { values: ['1', '2', '3', '4', '5', '6', '7', '8', '9'] },
      home: { values: ['1', '2', '3', '4', '5', '6', '7', '8', '9'] },
    },
    required: ['away', 'home'],
  },
  'lp.SavedRuleWire': {
    fields: {
      regulationInnings: { scalar: 'regulation-innings' },
      coldConditions: {
        items: {
          fields: {
            pointDifference: { scalar: 'regulation-innings' },
            startInning: { scalar: 'regulation-innings' },
          },
          required: ['pointDifference', 'startInning'],
        },
        maxItems: '16',
      },
      extensionLimit: {
        choices: [{ type: 'null' }, { scalar: 'regulation-innings' }],
      },
      tiebreak: {
        choices: [
          { type: 'null' },
          {
            fields: {
              startInning: { scalar: 'regulation-innings' },
              runnerPlacement: { type: 'string' },
              leadoffRule: { type: 'string' },
            },
            required: ['startInning', 'runnerPlacement', 'leadoffRule'],
          },
        ],
      },
      dh: { type: 'boolean' },
    },
    required: [
      'regulationInnings',
      'coldConditions',
      'extensionLimit',
      'tiebreak',
      'dh',
    ],
  },
  'lp.Lineup': {
    fields: { away: { ref: 'lp.LineupTeam' }, home: { ref: 'lp.LineupTeam' } },
    required: ['away', 'home'],
  },
  'lp.LineupTeam': {
    fields: {
      teamId: { ref: 'lp.Uuid' },
      battingOrder: {
        fields: {
          '1': { ref: 'lp.Uuid' },
          '2': { ref: 'lp.Uuid' },
          '3': { ref: 'lp.Uuid' },
          '4': { ref: 'lp.Uuid' },
          '5': { ref: 'lp.Uuid' },
          '6': { ref: 'lp.Uuid' },
          '7': { ref: 'lp.Uuid' },
          '8': { ref: 'lp.Uuid' },
          '9': { ref: 'lp.Uuid' },
        },
        required: ['1', '2', '3', '4', '5', '6', '7', '8', '9'],
      },
      pitcherId: { ref: 'lp.Uuid' },
      catcherId: { ref: 'lp.Uuid' },
    },
    required: ['teamId', 'battingOrder', 'pitcherId', 'catcherId'],
  },
  'lp.Uuid': { scalar: 'uuid' },
  'lp.Participant': {
    fields: {
      batterId: { ref: 'lp.Uuid' },
      pitcherId: { ref: 'lp.Uuid' },
      catcherId: { ref: 'lp.Uuid' },
      battingOrder: { ref: 'lp.Slot' },
    },
    required: ['batterId', 'pitcherId', 'catcherId', 'battingOrder'],
  },
  'lp.Slot': { values: ['1', '2', '3', '4', '5', '6', '7', '8', '9'] },
  'lp.Runner': {
    fields: {
      runnerId: { ref: 'lp.Uuid' },
      responsiblePitcherId: { ref: 'lp.Uuid' },
      base: { values: ['1', '2', '3'] },
      status: { constant: '継続' },
      statusSource: { constant: 'auto' },
    },
    required: [
      'runnerId',
      'responsiblePitcherId',
      'base',
      'status',
      'statusSource',
    ],
  },
  'lp.Responsibility': {
    choices: [
      {
        fields: {
          kind: { constant: 'no-change' },
          paStartSource: {
            fields: {
              kind: { values: ['started-game', 'confirmed-play'] },
              id: { ref: 'lp.Uuid' },
            },
            required: ['kind', 'id'],
          },
          previousPitcherId: { constant: null },
          strikesAtChange: { constant: null },
          ballsAtChange: { constant: null },
        },
        required: [
          'kind',
          'paStartSource',
          'previousPitcherId',
          'strikesAtChange',
          'ballsAtChange',
        ],
      },
      {
        fields: {
          kind: { constant: 'changed-mid-plate-appearance' },
          paStartSource: {
            fields: {
              kind: { values: ['started-game', 'confirmed-play'] },
              id: { ref: 'lp.Uuid' },
            },
            required: ['kind', 'id'],
          },
          previousPitcherId: { ref: 'lp.Uuid' },
          strikesAtChange: { values: ['0', '1', '2'] },
          ballsAtChange: { values: ['0', '1', '2', '3'] },
        },
        required: [
          'kind',
          'paStartSource',
          'previousPitcherId',
          'strikesAtChange',
          'ballsAtChange',
        ],
      },
    ],
  },
  'lp.T2': {
    fields: {
      kind: { constant: 'evaluated-end-condition' },
      scope: { constant: 'play-prefix-v3' },
      evaluation_point: { constant: 'post-play' },
      facts: { ref: 'lp.BoundaryFacts' },
      decision: { ref: 'lp.Decision' },
      tiebreakStartRequired: { type: 'boolean' },
    },
    required: [
      'kind',
      'scope',
      'evaluation_point',
      'facts',
      'decision',
      'tiebreakStartRequired',
    ],
  },
  'lp.BoundaryFacts': {
    fields: {
      beforeInning: { ref: 'lp.Positive' },
      beforeHalf: { values: ['top', 'bottom'] },
      beforeOuts: { values: ['0', '1', '2'] },
      afterInning: { ref: 'lp.Positive' },
      afterHalf: { values: ['top', 'bottom'] },
      afterOuts: { values: ['0', '1', '2'] },
      halfCompleted: { type: 'boolean' },
      outsUnchanged: { type: 'boolean' },
      scoreUnchanged: { type: 'boolean' },
      priorOpen: { constant: true },
    },
    required: [
      'beforeInning',
      'beforeHalf',
      'beforeOuts',
      'afterInning',
      'afterHalf',
      'afterOuts',
      'halfCompleted',
      'outsUnchanged',
      'scoreUnchanged',
      'priorOpen',
    ],
  },
  'lp.Positive': { scalar: 'positive' },
  'lp.Decision': {
    choices: [
      {
        fields: {
          outcome: { constant: 'normal-end' },
          endConditionDetected: { constant: true },
          lockFurtherPlayInput: { constant: true },
          promptEndDeclaration: { constant: true },
          automaticallyEndsGame: { constant: false },
          xMark: { constant: 'recorded-score' },
        },
        required: [
          'outcome',
          'endConditionDetected',
          'lockFurtherPlayInput',
          'promptEndDeclaration',
          'automaticallyEndsGame',
          'xMark',
        ],
      },
      {
        fields: {
          outcome: { constant: 'extra-continue' },
          endConditionDetected: { constant: false },
          lockFurtherPlayInput: { constant: false },
          promptEndDeclaration: { constant: false },
          automaticallyEndsGame: { constant: false },
          xMark: { constant: 'recorded-score' },
        },
        required: [
          'outcome',
          'endConditionDetected',
          'lockFurtherPlayInput',
          'promptEndDeclaration',
          'automaticallyEndsGame',
          'xMark',
        ],
      },
      {
        fields: {
          outcome: { constant: 'limit-draw' },
          endConditionDetected: { constant: true },
          lockFurtherPlayInput: { constant: true },
          promptEndDeclaration: { constant: true },
          automaticallyEndsGame: { constant: false },
          xMark: { constant: 'recorded-score' },
        },
        required: [
          'outcome',
          'endConditionDetected',
          'lockFurtherPlayInput',
          'promptEndDeclaration',
          'automaticallyEndsGame',
          'xMark',
        ],
      },
      {
        fields: {
          outcome: { constant: 'tiebreak-continue' },
          endConditionDetected: { constant: false },
          lockFurtherPlayInput: { constant: false },
          promptEndDeclaration: { constant: false },
          automaticallyEndsGame: { constant: false },
          xMark: { constant: 'recorded-score' },
        },
        required: [
          'outcome',
          'endConditionDetected',
          'lockFurtherPlayInput',
          'promptEndDeclaration',
          'automaticallyEndsGame',
          'xMark',
        ],
      },
      {
        fields: {
          outcome: { constant: 'cold-end' },
          endConditionDetected: { constant: true },
          lockFurtherPlayInput: { constant: true },
          promptEndDeclaration: { constant: true },
          automaticallyEndsGame: { constant: false },
          xMark: { constant: 'x-mark' },
        },
        required: [
          'outcome',
          'endConditionDetected',
          'lockFurtherPlayInput',
          'promptEndDeclaration',
          'automaticallyEndsGame',
          'xMark',
        ],
      },
      {
        fields: {
          outcome: { constant: 'walk-off' },
          endConditionDetected: { constant: true },
          lockFurtherPlayInput: { constant: true },
          promptEndDeclaration: { constant: true },
          automaticallyEndsGame: { constant: false },
          xMark: { constant: 'recorded-score' },
        },
        required: [
          'outcome',
          'endConditionDetected',
          'lockFurtherPlayInput',
          'promptEndDeclaration',
          'automaticallyEndsGame',
          'xMark',
        ],
      },
      {
        fields: {
          outcome: { constant: 'normal-end' },
          endConditionDetected: { constant: true },
          lockFurtherPlayInput: { constant: true },
          promptEndDeclaration: { constant: true },
          automaticallyEndsGame: { constant: false },
          xMark: { constant: 'x-mark' },
        },
        required: [
          'outcome',
          'endConditionDetected',
          'lockFurtherPlayInput',
          'promptEndDeclaration',
          'automaticallyEndsGame',
          'xMark',
        ],
      },
      {
        fields: {
          outcome: { constant: 'no-end' },
          endConditionDetected: { constant: false },
          lockFurtherPlayInput: { constant: false },
          promptEndDeclaration: { constant: false },
          automaticallyEndsGame: { constant: false },
          xMark: { constant: 'recorded-score' },
        },
        required: [
          'outcome',
          'endConditionDetected',
          'lockFurtherPlayInput',
          'promptEndDeclaration',
          'automaticallyEndsGame',
          'xMark',
        ],
      },
      {
        fields: {
          outcome: { constant: 'cold-end' },
          endConditionDetected: { constant: true },
          lockFurtherPlayInput: { constant: true },
          promptEndDeclaration: { constant: true },
          automaticallyEndsGame: { constant: false },
          xMark: { constant: 'recorded-score' },
        },
        required: [
          'outcome',
          'endConditionDetected',
          'lockFurtherPlayInput',
          'promptEndDeclaration',
          'automaticallyEndsGame',
          'xMark',
        ],
      },
    ],
  },
  'np.ActiveFrame': {
    fields: {
      play: { ref: 'np.ActivePlay' },
      historyEntry: { ref: 'un.HistoryEntry' },
      beforeContext: { ref: 'np.RestoreContext' },
      afterContext: { ref: 'np.RestoreContext' },
    },
    required: ['play', 'historyEntry', 'beforeContext', 'afterContext'],
  },
  'un.HistoryEntry': {
    fields: {
      kind: { constant: 'confirmed-play' },
      difference: {
        fields: {
          stateFields: { ref: 'un.StateDifference' },
          scoreboard: { ref: 'un.ScoreboardDifference' },
          statFlags: { ref: 'un.StatFlags' },
          battingOrderBySide: { ref: 'un.CursorDifference' },
        },
        required: ['stateFields', 'scoreboard', 'statFlags'],
      },
    },
    required: ['kind', 'difference'],
  },
  'un.StateDifference': {
    fields: {
      'state.half': {
        fields: {
          before: { values: ['top', 'bottom'] },
          after: { values: ['top', 'bottom'] },
        },
        required: ['before', 'after'],
      },
      'state.count.strikes': {
        fields: {
          before: { ref: 'un.CanonicalUnsigned' },
          after: { ref: 'un.CanonicalUnsigned' },
        },
        required: ['before', 'after'],
      },
      'state.count.balls': {
        fields: {
          before: { ref: 'un.CanonicalUnsigned' },
          after: { ref: 'un.CanonicalUnsigned' },
        },
        required: ['before', 'after'],
      },
      'state.outs': {
        fields: {
          before: { ref: 'un.CanonicalUnsigned' },
          after: { ref: 'un.CanonicalUnsigned' },
        },
        required: ['before', 'after'],
      },
      'state.runners': {
        fields: {
          before: {
            values: [
              'empty',
              'first',
              'second',
              'third',
              'first-second',
              'first-third',
              'second-third',
              'first-second-third',
            ],
          },
          after: {
            values: [
              'empty',
              'first',
              'second',
              'third',
              'first-second',
              'first-third',
              'second-third',
              'first-second-third',
            ],
          },
        },
        required: ['before', 'after'],
      },
      'state.battingOrder': {
        fields: {
          before: { ref: 'un.CanonicalUnsigned' },
          after: { ref: 'un.CanonicalUnsigned' },
        },
        required: ['before', 'after'],
      },
      'state.tiebreakActive': {
        fields: { before: { type: 'boolean' }, after: { type: 'boolean' } },
        required: ['before', 'after'],
      },
      'state.gameEnded': {
        fields: { before: { type: 'boolean' }, after: { type: 'boolean' } },
        required: ['before', 'after'],
      },
      'state.inning': {
        fields: {
          before: { ref: 'un.CanonicalPositive' },
          after: { ref: 'un.CanonicalPositive' },
        },
        required: ['before', 'after'],
      },
      'state.score': {
        fields: { before: { ref: 'un.Score' }, after: { ref: 'un.Score' } },
        required: ['before', 'after'],
      },
    },
    required: [],
  },
  'un.ScoreboardDifference': {
    fields: {
      inningScores: {
        fields: { before: { ref: 'un.Score' }, after: { ref: 'un.Score' } },
        required: ['before', 'after'],
      },
      hits: {
        fields: {
          before: { ref: 'un.CanonicalUnsigned' },
          after: { ref: 'un.CanonicalUnsigned' },
        },
        required: ['before', 'after'],
      },
      errors: {
        fields: {
          before: { ref: 'un.CanonicalUnsigned' },
          after: { ref: 'un.CanonicalUnsigned' },
        },
        required: ['before', 'after'],
      },
      strikeouts: {
        fields: {
          before: { ref: 'un.CanonicalUnsigned' },
          after: { ref: 'un.CanonicalUnsigned' },
        },
        required: ['before', 'after'],
      },
      walks: {
        fields: {
          before: { ref: 'un.CanonicalUnsigned' },
          after: { ref: 'un.CanonicalUnsigned' },
        },
        required: ['before', 'after'],
      },
    },
    required: [],
  },
  'un.StatFlags': {
    fields: {
      投球回算入アウト: { type: 'boolean' },
      投球数: { type: 'boolean' },
      奪三振: { type: 'boolean' },
      与四球: { type: 'boolean' },
      与死球: { type: 'boolean' },
      被安打: { type: 'boolean' },
      被本塁打: { type: 'boolean' },
      失点: { type: 'boolean' },
      失策: { type: 'boolean' },
      打席: { type: 'boolean' },
      打数: { type: 'boolean' },
      安打: { type: 'boolean' },
      本塁打: { type: 'boolean' },
      塁打: { type: 'boolean' },
      犠打: { type: 'boolean' },
      犠飛: { type: 'boolean' },
      四球: { type: 'boolean' },
      死球: { type: 'boolean' },
      三振: { type: 'boolean' },
      打撃妨害出塁: { type: 'boolean' },
      走塁妨害出塁: { type: 'boolean' },
      得点: { type: 'boolean' },
      打点: { type: 'boolean' },
    },
    required: [
      '投球回算入アウト',
      '投球数',
      '奪三振',
      '与四球',
      '与死球',
      '被安打',
      '被本塁打',
      '失点',
      '失策',
      '打席',
      '打数',
      '安打',
      '本塁打',
      '塁打',
      '犠打',
      '犠飛',
      '四球',
      '死球',
      '三振',
      '打撃妨害出塁',
      '走塁妨害出塁',
      '得点',
      '打点',
    ],
  },
  'un.CursorDifference': {
    fields: {
      away: {
        fields: {
          before: { values: ['1', '2', '3', '4', '5', '6', '7', '8', '9'] },
          after: { values: ['1', '2', '3', '4', '5', '6', '7', '8', '9'] },
        },
        required: ['before', 'after'],
      },
      home: {
        fields: {
          before: { values: ['1', '2', '3', '4', '5', '6', '7', '8', '9'] },
          after: { values: ['1', '2', '3', '4', '5', '6', '7', '8', '9'] },
        },
        required: ['before', 'after'],
      },
    },
    required: [],
  },
}
/** 任意深さ/桁数へ新capを設けず、正準scalarと閉memberだけを検査する。 */
function nonplayFingerprint(value: unknown): boolean {
  if (typeof value !== 'string') return false
  if (digest(value)) return true
  if (!value.startsWith('wire-v1:')) return false
  let suffix = ''
  let offset = 0n
  for (const ch of value) {
    if (offset >= 8n) suffix = suffix + ch
    offset = offset + 1n
  }
  return digest(suffix)
}
function nonplayShape(value: unknown, shape: Json): boolean {
  if (typeof shape.ref === 'string')
    return nonplayShape(value, read(nonplayShapes, shape.ref) as Json)
  if (Object.prototype.hasOwnProperty.call(shape, 'constant'))
    return sameContinuationValue(value, shape.constant)
  if (Array.isArray(shape.values))
    return shape.values.some((v) => sameContinuationValue(v, value))
  if (Array.isArray(shape.choices)) {
    let matches = 0n
    for (const choice of shape.choices)
      if (nonplayShape(value, choice as Json)) matches = matches + 1n
    return matches === 1n
  }
  if (typeof shape.scalar === 'string') {
    if (shape.scalar === 'uuid') return canonicalContinuationUuid(value)
    if (shape.scalar === 'digest') return digest(value)
    if (shape.scalar === 'generation')
      return canonicalContinuationGeneration(value)
    if (shape.scalar === 'fingerprint') return nonplayFingerprint(value)
    if (shape.scalar === 'signed')
      return typeof value === 'string' && parseDecimalInteger(value) !== null
    const n = unsigned(value)
    if (shape.scalar === 'regulation-innings')
      return n !== null && n >= 1n && n <= 99n
    return n !== null && (shape.scalar !== 'positive' || n > 0n)
  }
  if (shape.type === 'null') return value === null
  if (shape.type === 'boolean') return typeof value === 'boolean'
  if (shape.type === 'string') return typeof value === 'string'
  if (typeof shape.fields !== 'undefined') {
    if (value === null || typeof value !== 'object' || Array.isArray(value))
      return false
    const fields = shape.fields as Json
    const required = shape.required as Array<string>
    const obj = value as Json
    if (!required.every((k) => Object.prototype.hasOwnProperty.call(obj, k)))
      return false
    for (const pair of Object.entries(obj)) {
      const key = pair.slice().shift() as string
      const v = pair.slice().pop()
      if (
        !Object.prototype.hasOwnProperty.call(fields, key) ||
        !nonplayShape(v, read(fields, key) as Json)
      )
        return false
    }
    return true
  }
  if (typeof shape.items !== 'undefined') {
    if (!Array.isArray(value)) return false
    let count = 0n
    for (const v of value) {
      if (!nonplayShape(v, shape.items as Json)) return false
      count = count + 1n
    }
    let minimum: bigint | null = null
    let maximum: bigint | null = null
    if (typeof shape.minItems === 'string') minimum = unsigned(shape.minItems)
    if (typeof shape.maxItems === 'string') maximum = unsigned(shape.maxItems)
    return (
      (minimum === null || count >= minimum) &&
      (maximum === null || count <= maximum)
    )
  }
  return false
}
/** 保存全before/after面との観測比較だけを行い、逆計算を複製しない。 */
function nonplayHistoryMatches(frame: Json): boolean {
  const before = (frame.beforeContext as Json).current as Json
  const after = (frame.afterContext as Json).current as Json
  const difference = (frame.historyEntry as Json).difference as Json
  for (const key of ['stateFields', 'scoreboard', 'battingOrderBySide']) {
    const b = read(before, key) as Json
    const a = read(after, key) as Json
    const changes = read(difference, key) as Json | null
    for (const pair of Object.entries(b)) {
      const field = pair.slice().shift() as string
      const old = pair.slice().pop()
      let span: Json | null = null
      if (changes !== null) span = read(changes, field) as Json | null
      if (span === null) {
        if (!sameContinuationValue(old, read(a, field))) return false
      } else if (
        !sameContinuationValue(span.before, old) ||
        !sameContinuationValue(span.after, read(a, field))
      )
        return false
    }
  }
  return true
}
/** 全制御核応答を再確認する。構造と数学の検査であってDB資格ではない。 */
function controlBridges(content: Json): Array<Json> | null {
  let bridges: Array<Json> = []
  if (typeof content.controlBridges !== 'undefined')
    bridges = content.controlBridges as Array<Json>
  let seen: Array<string> = []
  for (const b of bridges) {
    const source = b.source as Json
    const kernel = b.kernel as Json
    const request = kernel.request as Json
    const response = kernel.response as Json
    if (response.ok !== true) return null
    const event = request.event as Json
    const before = b.beforeContext as Json
    const after = b.afterContext as Json
    const scope = content.scope as Json
    let kind = 'game_end_declaration'
    if (b.action === 'reopen') kind = 'game_reopen'
    if (
      seen.includes(source.eventId as string) ||
      source.gameId !== scope.gameId ||
      source.eventKind !== kind ||
      request.action !== b.action ||
      event.eventId !== source.eventId ||
      !sameContinuationValue(request.current, before.current) ||
      !sameContinuationValue((response.value as Json).current, after.current) ||
      !sameContinuationValue(
        JSON.parse(applyGameLifecycle(JSON.stringify(request))) as unknown,
        response,
      )
    )
      return null
    for (const pair of Object.entries(before)) {
      const key = pair.slice().shift() as string
      if (
        key !== 'current' &&
        !sameContinuationValue(pair.slice().pop(), read(after, key))
      )
        return null
    }
    seen = seen.concat([source.eventId as string])
  }
  return bridges
}
/** 交代と終了再開をD1順に各play間へ接続し、文脈の穴を閉じる。 */
function substitutionGaps(
  c: Json,
  stack: Array<Json>,
  bridges: Array<Json>,
): boolean {
  const raw = c.substitutionFrames ?? []
  if (!Array.isArray(raw)) return false
  const frames = raw as Array<Json>
  let used: Array<string> = []
  function gap(
    playAnchor: string | null,
    eventAnchor: string,
    before: unknown,
    after: unknown,
  ): boolean {
    let current = before
    let pending: Array<Json> = []
    for (const frame of frames) {
      if (frame.afterPlayId === playAnchor) pending = pending.concat([frame])
    }
    for (const bridge of bridges) {
      if (bridge.anchorEventId === eventAnchor)
        pending = pending.concat([bridge])
    }
    let ordered: Array<Json> = []
    for (const candidate of pending) {
      const candidateD1 = unsigned((candidate.source as Json).d1)
      if (candidateD1 === null) return false
      let next: Array<Json> = []
      let inserted = false
      for (const prior of ordered) {
        const priorD1 = unsigned((prior.source as Json).d1)
        if (priorD1 === null) return false
        if (!inserted && candidateD1 < priorD1) {
          next = next.concat([candidate])
          inserted = true
        }
        next = next.concat([prior])
      }
      if (!inserted) next = next.concat([candidate])
      ordered = next
    }
    let lastD1: bigint | null = null
    for (const frame of ordered) {
      const src = frame.source as Json
      const d1 = unsigned(src.d1)
      if (d1 === null || (lastD1 !== null && d1 <= lastD1)) return false
      if (
        !canonicalContinuationUuid(src.eventId) ||
        used.includes(src.eventId as string)
      )
        return false
      if (
        Object.prototype.hasOwnProperty.call(frame, 'afterPlayId') &&
        (src.eventKind !== 'substitution' ||
          !Object.prototype.hasOwnProperty.call(
            frame.afterContext,
            'substitutionState',
          ))
      )
        return false
      used = used.concat([src.eventId as string])
      if (
        current !== null &&
        !sameContinuationValue(current, frame.beforeContext)
      )
        return false
      current = frame.afterContext
      lastD1 = d1
    }
    return current === null || sameContinuationValue(current, after)
  }
  let newer: Json | null = null
  for (const older of stack) {
    const play = older.play as Json
    let target: unknown = c.restored
    if (newer !== null) target = newer.beforeContext
    if (
      !gap(
        play.playId as string,
        (play.source as Json).eventId as string,
        older.afterContext,
        target,
      )
    )
      return false
    newer = older
  }
  let target: unknown = c.restored
  if (newer !== null) target = newer.beforeContext
  if (!gap(null, (c.origin as Json).eventId as string, null, target))
    return false
  let count = 0n
  for (const item of used) {
    if (item !== '') count = count + 1n
  }
  let all = 0n
  for (const item of frames.concat(bridges)) {
    if (item !== null) all = all + 1n
  }
  return count === all
}
/** 三headはそのまま保ち、旧v3/startedへ偽装せず共通計算に必要なviewだけを取る。 */
function nonplayView(value: unknown, suppliedPosition: unknown): Json | null {
  if (!nonplayShape(value, read(nonplayShapes, 'np.Source') as Json))
    return null
  const s = value as Json
  const cp = s.checkpoint as Json
  const c = cp.content as Json
  const bridges = controlBridges(c)
  if (bridges === null) return null
  const restored = c.restored as Json
  const stack = s.activeStack as Array<Json>
  const pos = object(suppliedPosition, ['d1', 'd2', 'appliedWatermark'])
  const d3 = unsigned(c.d3)
  let depth = 0n
  let previous: Json | null = null
  for (const frame of stack) {
    depth = depth + 1n
    if (!nonplayHistoryMatches(frame)) return null
    const play = frame.play as Json
    const event = play.source as Json
    const scope = c.scope as Json
    const eventD1 = unsigned(event.d1)
    const physical = unsigned(play.physicalPlayNumber)
    const nextPhysical = unsigned(c.nextPhysicalPlayNumber)
    if (
      event.gameId !== scope.gameId ||
      event.eventKind !== 'play_input' ||
      eventD1 === null ||
      physical === null ||
      nextPhysical === null ||
      d3 === null ||
      (event.generation === scope.generation && eventD1 > d3) ||
      physical >= nextPhysical
    )
      return null
    if (previous !== null) {
      const newer = previous.play as Json
      const newerD1 = unsigned((newer.source as Json).d1)
      const d2 = unsigned(play.d2)
      const newerD2 = unsigned(newer.d2)
      const newerPhysical = unsigned(newer.physicalPlayNumber)
      if (
        newerD1 === null ||
        d2 === null ||
        newerD2 === null ||
        newerPhysical === null
      )
        return null
      if (
        (event.generation === (newer.source as Json).generation &&
          eventD1 >= newerD1) ||
        d2 >= newerD2 ||
        physical >= newerPhysical
      )
        return null
    }
    previous = frame
  }
  const first = stack.slice().shift()
  let headMismatch = c.activeHead !== null
  if (typeof first !== 'undefined')
    headMismatch = !sameContinuationValue(c.activeHead, first.play)
  if (
    d3 === null ||
    unsigned(c.activeDepth) !== depth ||
    headMismatch ||
    !substitutionGaps(c, stack, bridges) ||
    pos === null ||
    unsigned(pos.d1) !== d3 + 1n ||
    unsigned(pos.appliedWatermark) !== d3 ||
    unsigned(pos.d2) === null ||
    unsigned(pos.d2) === 0n
  )
    return null
  const scope = c.scope as Json
  const head = c.d1Head as Json | null
  const projection = c.projectionHead as Json
  if (d3 === 0n) {
    if (head !== null) return null
  } else if (
    head === null ||
    unsigned((head.source as Json).d1) !== d3 ||
    (head.source as Json).gameId !== scope.gameId ||
    (head.source as Json).generation !== scope.generation
  )
    return null
  if (projection.kind === 'started-game') {
    if (projection.eventId !== (c.origin as Json).eventId || depth !== 0n)
      return null
  } else {
    const projected = projection.source as Json
    const projectionD1 = unsigned(projected.d1)
    if (
      projected.gameId !== scope.gameId ||
      projectionD1 === null ||
      (projected.generation === scope.generation && projectionD1 > d3)
    )
      return null
    if (
      head !== null &&
      projected.eventId === (head.source as Json).eventId &&
      !sameContinuationValue(projected, head.source)
    )
      return null
  }
  if (typeof first !== 'undefined' && head !== null) {
    const activeSource = (first.play as Json).source as Json
    if (
      activeSource.eventId === (head.source as Json).eventId &&
      !sameContinuationValue(activeSource, head.source)
    )
      return null
  }
  let releasedEndCondition = false
  let latestControlAction: unknown = null
  for (const bridge of bridges) {
    releasedEndCondition = bridge.action === 'reopen'
    latestControlAction = bridge.action
  }
  if (latestControlAction === 'end') return null
  // 同世代文字列や単純なD2大小は真正連結/全物理末尾の証明ではない。SQLが再照合する。
  return {
    kind: 'nonplay-prefix-source-v1',
    after: restored.current,
    rules: restored.rules,
    lineup: restored.lineup,
    runners: restored.runners,
    participants: restored.participants,
    responsibility: restored.responsibility,
    t2: restored.lastPlayEvaluation,
    // 真正consumed/head一致はSQLが保証し、核は全bridge応答と順序を再検算する。
    releasedEndCondition: releasedEndCondition,
    historyDepth: c.activeDepth,
    playCount: c.activeDepth,
    historyVersion: c.historyVersion,
    position: pos,
    rulesDigest: restored.rulesDigest,
    layoutDigest: restored.layoutDigest,
    rosterDigest: restored.rosterDigest,
    executionArtifactSha256: c.executionArtifactSha256,
    priorArtifactSha256: c.executionArtifactSha256,
    checkpoint: cp.ref,
  }
}

/** 未信頼提案の相関だけを検査する。DB真正資格はsource verifierが別に確認する。 */
export function prepareLineupContinuation(raw: string): Prepared {
  const decoded = JSON.parse(raw)
  const r =
    object(decoded, [
      'version',
      'prefixRef',
      'rules',
      't1',
      'source',
      'playIdentity',
      'nextCheckpoint',
    ]) ??
    object(decoded, [
      'version',
      'prefixRef',
      'rules',
      't1',
      'source',
      'playIdentity',
      'nextCheckpoint',
      'sourcePosition',
    ])
  if (
    r === null ||
    !['3', 'nonplay-continuation-v1'].includes(r.version as string)
  )
    return reject('INVALID_REQUEST')
  const nonplay = r.version === 'nonplay-continuation-v1'
  if (
    (!nonplay && Object.prototype.hasOwnProperty.call(r, 'sourcePosition')) ||
    (nonplay && !Object.prototype.hasOwnProperty.call(r, 'sourcePosition'))
  )
    return reject('INVALID_REQUEST')
  let ref = prefix(r.prefixRef)
  if (nonplay) ref = checkpoint(r.prefixRef)
  const next = checkpoint(r.nextCheckpoint)
  const ordinaryInput = object(r.t1, [
    'eventKind',
    'resultId',
    'pitchEventKind',
    'before',
  ])
  const battedInput = object(r.t1, [
    'eventKind',
    'resultId',
    'pitchEventKind',
    'before',
    'officialScoringPayload',
    'interferenceRuling',
    'runnerAdvanceOverrides',
    'thirdOutObservation',
  ])
  const input = ordinaryInput ?? battedInput
  // 安打結果に観測を補わず、旧4fieldのまま受け入れない。
  if (
    ordinaryInput !== null &&
    typeof ordinaryInput.resultId === 'string' &&
    [
      'batting-result.single',
      'batting-result.double',
      'batting-result.triple',
      'batting-result.home-run',
    ].includes(ordinaryInput.resultId)
  )
    return reject('INVALID_REQUEST')
  let s = object(r.source, [
    'kind',
    'prefixRef',
    'rules',
    'after',
    't2',
    'historyDepth',
    'playCount',
    'lastSource',
    'position',
    'priorArtifactSha256',
    'executionArtifactSha256',
    'rulesDigest',
    'layoutDigest',
    'rosterDigest',
    'lineup',
    'runners',
    'participants',
    'responsibility',
    'provenance',
  ])
  if (nonplay) {
    if (!nonplayShape(r.source, read(nonplayShapes, 'np.Source') as Json))
      return reject('INVALID_REQUEST')
    s = nonplayView(r.source, r.sourcePosition)
    if (s === null) return reject('PREFIX_SOURCE_MISMATCH')
  }
  if (
    ref === null ||
    next === null ||
    input === null ||
    s === null ||
    identity(r.playIdentity) === null
  )
    return reject('INVALID_REQUEST')
  const rules = readContinuationRules(r.rules)
  if (!rules.ok) return reject(rules.code)
  if (!validEndRules(rules.value)) return reject('T2_NOT_EVALUATED')
  const l = lineup(s.lineup, rules.value.dh)
  const before = object(s.after, [
    'stateFields',
    'scoreboard',
    'battingOrderBySide',
  ])
  const pos = object(s.position, ['d1', 'd2', 'appliedWatermark'])
  const resp = responsibility(s.responsibility)
  if (
    l === null ||
    before === null ||
    people(s.participants) === null ||
    pos === null ||
    Object.values(pos).some((v) => unsigned(v) === null) ||
    resp === null ||
    ![
      s.priorArtifactSha256,
      s.executionArtifactSha256,
      s.rulesDigest,
      s.layoutDigest,
      s.rosterDigest,
    ].every(digest)
  )
    return reject('INVALID_REQUEST')
  const fields = before.stateFields as Json
  const cursors = object(before.battingOrderBySide, ['away', 'home'])
  if (
    cursors === null ||
    Object.values(cursors).some((v) => {
      const n = unsigned(v)
      return n === null || n < 1n || n > 9n
    })
  )
    return reject('INVALID_REQUEST')
  let active = cursors.away
  if (read(fields, 'state.half') === 'bottom') active = cursors.home
  let cp = ref.checkpoint as Json
  if (nonplay) cp = ref
  let refMatches = sameContinuationValue(s.prefixRef, ref)
  if (nonplay) refMatches = sameContinuationValue(s.checkpoint, ref)
  const revision = unsigned(cp.revision)
  const applied = unsigned(pos.appliedWatermark)
  if (
    !refMatches ||
    !sameContinuationValue(s.rules, r.rules) ||
    !sameContinuationValue(before, input.before) ||
    !sameContinuationValue(s.participants, participant(before, l)) ||
    read(fields, 'state.battingOrder') !== active ||
    !sameContinuationValue(
      read(fields, 'state.score'),
      (before.scoreboard as Json).inningScores,
    ) ||
    (!nonplay &&
      (s.historyDepth !== ref.length || s.playCount !== ref.length)) ||
    applied === null ||
    unsigned(pos.d1) !== applied + 1n ||
    unsigned(pos.d2) === 0n ||
    (!nonplay && s.rosterDigest !== s.layoutDigest) ||
    revision === null ||
    unsigned(next.revision) !== revision + 1n ||
    next.id === cp.id ||
    !runners(s.runners, before)
  )
    return reject('PREFIX_SOURCE_MISMATCH')
  const provenance = s.provenance as Json
  if (nonplay) {
    if (s.kind !== 'nonplay-prefix-source-v1')
      return reject('PREFIX_SOURCE_MISMATCH')
    if (s.t2 !== null) {
      const prior = s.t2 as Json
      const d = prior.decision as Json
      const f = prior.facts as Json
      if (
        prior.tiebreakStartRequired !== false ||
        (s.releasedEndCondition !== true &&
          (d.endConditionDetected !== false ||
            d.lockFurtherPlayInput !== false ||
            d.promptEndDeclaration !== false ||
            d.automaticallyEndsGame !== false ||
            d.xMark !== 'recorded-score' ||
            !['no-end', 'extra-continue', 'tiebreak-continue'].includes(
              d.outcome as string,
            ))) ||
        f.afterInning !== read(fields, 'state.inning') ||
        f.afterHalf !== read(fields, 'state.half') ||
        f.afterOuts !== read(fields, 'state.outs') ||
        f.priorOpen !== true
      )
        return reject('PREFIX_SOURCE_MISMATCH')
      if (s.releasedEndCondition === true) {
        const inning = unsigned(f.afterInning)
        const score = read(fields, 'state.score') as Json
        const home = unsigned(score.home)
        const away = unsigned(score.away)
        const half = f.afterHalf
        let completedHalf: 'top' | 'bottom' | null = null
        let completedInning: bigint | null = null
        if (f.halfCompleted === true) {
          if (f.beforeHalf !== 'top' && f.beforeHalf !== 'bottom')
            return reject('PREFIX_SOURCE_MISMATCH')
          completedHalf = f.beforeHalf
          completedInning = unsigned(f.beforeInning)
        }
        if (
          inning === null ||
          home === null ||
          away === null ||
          (half !== 'top' && half !== 'bottom')
        )
          return reject('PREFIX_SOURCE_MISMATCH')
        const checked = evaluateEndCondition(
          {
            inning,
            half,
            home,
            away,
            tiebreakActive: read(fields, 'state.tiebreakActive') === true,
            gameEnded: read(fields, 'state.gameEnded') === true,
          },
          rules.value,
          { completedHalf, completedInning },
        )
        if (checked === null || !sameContinuationValue(prior.decision, checked))
          return reject('PREFIX_SOURCE_MISMATCH')
      }
    }
  } else if (s.kind === 'started-initial-v3') {
    const p = object(provenance, ['kind', 'eventId'])
    const origin = ref.origin as Json
    const pa = resp.paStartSource as Json
    if (
      p === null ||
      p.kind !== 'started-game' ||
      p.eventId !== origin.eventId ||
      pa.kind !== 'started-game' ||
      pa.id !== p.eventId ||
      ref.length !== '0' ||
      ref.historyVersion !== '0' ||
      s.t2 !== null ||
      s.lastSource !== null ||
      pos.d1 !== '1' ||
      pos.d2 !== '1' ||
      pos.appliedWatermark !== '0' ||
      cursors.away !== '1' ||
      cursors.home !== '1' ||
      read(fields, 'state.inning') !== '1' ||
      read(fields, 'state.half') !== 'top' ||
      read(fields, 'state.outs') !== '0' ||
      read(fields, 'state.count.strikes') !== '0' ||
      read(fields, 'state.count.balls') !== '0' ||
      read(fields, 'state.runners') !== 'empty' ||
      read(fields, 'state.tiebreakActive') !== false ||
      read(fields, 'state.gameEnded') !== false ||
      !sameContinuationValue(read(fields, 'state.score'), {
        home: '0',
        away: '0',
      }) ||
      !sameContinuationValue(before.scoreboard, {
        inningScores: { home: '0', away: '0' },
        hits: '0',
        errors: '0',
        strikeouts: '0',
        walks: '0',
      })
    )
      return reject('PREFIX_SOURCE_MISMATCH')
  } else if (s.kind === 'evaluated-prefix-v3') {
    const p = object(provenance, [
      'kind',
      'checkpoint',
      'sourceIdentity',
      'historyDepth',
    ])
    const t2 = object(s.t2, [
      'kind',
      'scope',
      'evaluation_point',
      'facts',
      'decision',
      'tiebreakStartRequired',
    ])
    if (
      p === null ||
      p.kind !== 'confirmed-prefix' ||
      !sameContinuationValue(p.checkpoint, cp) ||
      identity(s.lastSource) === null ||
      !sameContinuationValue(p.sourceIdentity, s.lastSource) ||
      p.historyDepth !== s.historyDepth ||
      t2 === null ||
      t2.kind !== 'evaluated-end-condition' ||
      t2.scope !== 'play-prefix-v3' ||
      t2.evaluation_point !== 'post-play' ||
      t2.tiebreakStartRequired !== false
    )
      return reject('PREFIX_SOURCE_MISMATCH')
    const d = object(t2.decision, [
      'outcome',
      'endConditionDetected',
      'lockFurtherPlayInput',
      'promptEndDeclaration',
      'automaticallyEndsGame',
      'xMark',
    ])
    const f = object(t2.facts, [
      'beforeInning',
      'beforeHalf',
      'beforeOuts',
      'afterInning',
      'afterHalf',
      'afterOuts',
      'halfCompleted',
      'outsUnchanged',
      'scoreUnchanged',
      'priorOpen',
    ])
    if (
      d === null ||
      d.endConditionDetected !== false ||
      d.lockFurtherPlayInput !== false ||
      d.promptEndDeclaration !== false ||
      d.automaticallyEndsGame !== false ||
      d.xMark !== 'recorded-score' ||
      !['no-end', 'extra-continue', 'tiebreak-continue'].includes(
        d.outcome as string,
      ) ||
      f === null ||
      f.afterInning !== read(fields, 'state.inning') ||
      f.afterHalf !== read(fields, 'state.half') ||
      f.afterOuts !== read(fields, 'state.outs') ||
      f.priorOpen !== true ||
      typeof f.halfCompleted !== 'boolean' ||
      typeof f.outsUnchanged !== 'boolean' ||
      typeof f.scoreUnchanged !== 'boolean' ||
      unsigned(f.beforeInning) === null ||
      unsigned(f.beforeInning) === 0n ||
      !['top', 'bottom'].includes(f.beforeHalf as string) ||
      !['0', '1', '2'].includes(f.beforeOuts as string)
    )
      return reject('PREFIX_SOURCE_MISMATCH')
  } else return reject('PREFIX_SOURCE_MISMATCH')
  if (s.kind === 'evaluated-prefix-v3' || (nonplay && s.t2 !== null)) {
    const prior = s.t2 as Json
    const facts = prior.facts as Json
    const score = read(fields, 'state.score') as Json
    const observedInning = unsigned(read(fields, 'state.inning'))
    const home = unsigned(score.home)
    const away = unsigned(score.away)
    const observedHalf = read(fields, 'state.half')
    if (
      observedInning === null ||
      home === null ||
      away === null ||
      (observedHalf !== 'top' && observedHalf !== 'bottom')
    )
      return reject('PREFIX_SOURCE_MISMATCH')
    let completed: 'top' | 'bottom' | null = null
    let completedInning: bigint | null = null
    if (facts.halfCompleted === true) {
      if (facts.beforeHalf !== 'top' && facts.beforeHalf !== 'bottom')
        return reject('PREFIX_SOURCE_MISMATCH')
      completed = facts.beforeHalf
      completedInning = unsigned(facts.beforeInning)
    }
    const checked = evaluateEndCondition(
      {
        inning: observedInning,
        half: observedHalf,
        home: home,
        away: away,
        tiebreakActive: read(fields, 'state.tiebreakActive') === true,
        gameEnded: read(fields, 'state.gameEnded') === true,
      },
      rules.value,
      { completedHalf: completed, completedInning: completedInning },
    )
    if (checked === null || !sameContinuationValue(prior.decision, checked))
      return reject('PREFIX_SOURCE_MISMATCH')
  }
  // TB開始を自動実行せず、FR009が未供給の状態から投球しない。
  let expectedTB = false
  const inning = unsigned(read(fields, 'state.inning'))
  if (inning === null) return reject('INVALID_DECIMAL_INTEGER')
  if (
    rules.value.tiebreak !== null &&
    inning >= rules.value.tiebreak.startInning
  )
    expectedTB = true
  if (read(fields, 'state.tiebreakActive') !== expectedTB)
    return reject('T2_NOT_EVALUATED')
  let t1: Json = {
    eventKind: input.eventKind,
    resultId: input.resultId,
    pitchEventKind: input.pitchEventKind,
    before: before,
    history: { stack: [] },
  }
  if (battedInput !== null)
    t1 = Object.assign(t1, {
      officialScoringPayload: battedInput.officialScoringPayload,
      interferenceRuling: battedInput.interferenceRuling,
      runnerAdvanceOverrides: battedInput.runnerAdvanceOverrides,
      thirdOutObservation: battedInput.thirdOutObservation,
    })
  return { ok: true, request: r, battedHit: battedInput !== null, t1: t1 }
}
/** 実一回T1をT2/runner/次sourceへ射影する。入力提案からT1結果をlookupしない。 */
export function finishLineupContinuation(r: Json, raw: string): string {
  const response = JSON.parse(raw) as Json
  if (response.ok !== true) return raw
  const value = response.value as Json
  const input = r.t1 as Json
  const nonplay = r.version === 'nonplay-continuation-v1'
  let source = r.source as Json
  if (nonplay) {
    const view = nonplayView(r.source, r.sourcePosition)
    if (view === null) return failure('PREFIX_SOURCE_MISMATCH')
    source = view
  }
  const before = input.before as Json
  const after = value.after as Json
  const bf = before.stateFields as Json
  const af = after.stateFields as Json
  const rule = readContinuationRules(r.rules)
  if (!rule.ok) return failure('T2_NOT_EVALUATED')
  const inning = unsigned(read(af, 'state.inning'))
  const beforeInning = unsigned(read(bf, 'state.inning'))
  const score = read(af, 'state.score') as Json
  const home = unsigned(score.home)
  const away = unsigned(score.away)
  const half = read(af, 'state.half')
  const beforeHalf = read(bf, 'state.half')
  if (
    inning === null ||
    beforeInning === null ||
    home === null ||
    away === null ||
    (half !== 'top' && half !== 'bottom') ||
    (beforeHalf !== 'top' && beforeHalf !== 'bottom')
  )
    return failure('T2_NOT_EVALUATED')
  let completedHalf: 'top' | 'bottom' | null = null
  let completedInning: bigint | null = null
  if (half !== beforeHalf) {
    completedHalf = beforeHalf
    completedInning = beforeInning
  }
  const result = evaluateEndCondition(
    {
      inning: inning,
      half: half,
      home: home,
      away: away,
      tiebreakActive: read(af, 'state.tiebreakActive') === true,
      gameEnded: read(af, 'state.gameEnded') === true,
    },
    rule.value,
    { completedHalf: completedHalf, completedInning: completedInning },
  )
  if (result === null) return failure('T2_NOT_EVALUATED')
  let tbRequired = false
  if (
    result.outcome === 'tiebreak-continue' &&
    read(af, 'state.tiebreakActive') !== true
  )
    tbRequired = true
  const t2 = {
    kind: 'evaluated-end-condition',
    scope: 'play-prefix-v3',
    evaluation_point: 'post-play',
    facts: {
      beforeInning: read(bf, 'state.inning'),
      beforeHalf: beforeHalf,
      beforeOuts: read(bf, 'state.outs'),
      afterInning: read(af, 'state.inning'),
      afterHalf: half,
      afterOuts: read(af, 'state.outs'),
      halfCompleted: completedHalf !== null,
      outsUnchanged: read(bf, 'state.outs') === read(af, 'state.outs'),
      scoreUnchanged: sameContinuationValue(
        read(bf, 'state.score'),
        read(af, 'state.score'),
      ),
      priorOpen: true,
    },
    decision: result,
    tiebreakStartRequired: tbRequired,
  }
  const entries = (value.historyContext as Array<unknown>).slice()
  const entry = entries.shift()
  if (typeof entry === 'undefined' || entries.some(() => true))
    return failure('T2_NOT_EVALUATED')
  const l = source.lineup as Json
  const nextPeople = participant(after, l)
  if (nextPeople === null) return failure('PREFIX_SOURCE_MISMATCH')
  let responsiblePitcherId = (source.participants as Json).pitcherId as string
  const priorResponsibility = source.responsibility as Json
  if (
    (value.statFlags as Json).四球 === true &&
    priorResponsibility.kind === 'changed-mid-plate-appearance'
  )
    responsiblePitcherId = walkResponsiblePitcher(
      {
        kind: 'changed-mid-plate-appearance',
        previousPitcherId: priorResponsibility.previousPitcherId as string,
        reliefPitcherId: responsiblePitcherId,
        strikesAtChange: priorResponsibility.strikesAtChange as '0' | '1' | '2',
        ballsAtChange: priorResponsibility.ballsAtChange as '0' | '1' | '2' | '3',
      },
      responsiblePitcherId,
    )
  let nextRunners: Array<Json> = []
  if (completedHalf === null) {
    const advances = object(value.runnerDefaultAdvance, [
      'first',
      'second',
      'third',
    ])
    if (advances === null) return failure('PREFIX_SOURCE_MISMATCH')
    for (const runner of source.runners as Array<Json>) {
      const slot = slotForBase(runner.base)
      if (slot === null) return failure('PREFIX_SOURCE_MISMATCH')
      const destination = runnerDestination(read(advances, slot))
      if (destination === 'invalid') return failure('PREFIX_SOURCE_MISMATCH')
      if (destination === null)
        nextRunners = nextRunners.concat([Object.assign({}, runner)])
      else if (destination !== '4')
        nextRunners = nextRunners.concat([
          Object.assign({}, runner, { base: destination }),
        ])
    }
    if (value.plateAppearanceEnded === true) {
      const batter = value.batterDestination as Json
      if (batter.kind === 'reach') {
        if (batter.base !== '1' && batter.base !== '2' && batter.base !== '3')
          return failure('PREFIX_SOURCE_MISMATCH')
        nextRunners = nextRunners.concat([
          {
            runnerId: (source.participants as Json).batterId,
            responsiblePitcherId: responsiblePitcherId,
            base: batter.base,
            status: '継続',
            statusSource: 'auto',
          },
        ])
      }
    }
  }
  if (!runners(nextRunners, after)) return failure('PREFIX_SOURCE_MISMATCH')
  let nextResponsibility = source.responsibility
  if (value.plateAppearanceEnded === true)
    nextResponsibility = {
      kind: 'no-change',
      paStartSource: {
        kind: 'confirmed-play',
        id: (r.playIdentity as Json).eventId,
      },
      previousPitcherId: null,
      strikesAtChange: null,
      ballsAtChange: null,
    }
  const ref = r.prefixRef as Json
  let length = unsigned(ref.length)
  let history = unsigned(ref.historyVersion)
  if (nonplay) {
    length = unsigned(source.historyDepth)
    history = unsigned(source.historyVersion)
  }
  if (length === null || history === null)
    return failure('PREFIX_SOURCE_MISMATCH')
  let nextRef: Json = Object.assign({}, ref, {
    length: formatDecimalInteger(length + 1n),
    historyVersion: formatDecimalInteger(history + 1n),
    checkpoint: r.nextCheckpoint,
  })
  if (nonplay) nextRef = r.nextCheckpoint as Json
  return JSON.stringify({
    ok: true,
    value: {
      t1: {
        countEffect: value.countEffect,
        plateAppearanceEnded: value.plateAppearanceEnded,
        batterDestination: value.batterDestination,
        runnerDefaultAdvance: value.runnerDefaultAdvance,
        outEffect: value.outEffect,
        statFlags: value.statFlags,
        after: after,
      },
      t2: t2,
      newHistoryEntry: entry,
      previousPrefixRef: ref,
      nextPrefixRef: nextRef,
      runners: nextRunners,
      beforeParticipants: source.participants,
      participants: nextPeople,
      lineup: l,
      rosterDigest: source.rosterDigest,
      responsibility: source.responsibility,
      nextResponsibility: nextResponsibility,
      playIdentity: r.playIdentity,
      sourcePosition: source.position,
      executionArtifactSha256: source.executionArtifactSha256,
    },
  })
}
