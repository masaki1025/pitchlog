/** 自動生成。単一遷移だけを計算し、認可/全game集計を行わない。 */
export const SOURCE_MODEL_HASH =
  'sha256:60ab45878fdfc868efc15ddb0f9b84d6ab0f3583519c48a2202e3d9c3abac59d'
if (
  (globalThis as { __PITCHLOG_GENERATED_WRAPPER__?: boolean })
    .__PITCHLOG_GENERATED_WRAPPER__ !== true
)
  throw new Error('登録wrapperが必要です')
// generated=sha256:60ab45878fdfc868efc15ddb0f9b84d6ab0f3583519c48a2202e3d9c3abac59d
export function parseCount(value: unknown): bigint {
  if (typeof value === 'bigint' && value >= 0n) return value
  if (typeof value === 'number' && Number.isSafeInteger(value) && value >= 0)
    return BigInt(value)
  if (typeof value === 'string' && /^(0|[1-9][0-9]*)$/.test(value))
    return BigInt(value)
  throw new Error('正準非負整数が必要です')
}
export function formatCount(value: unknown): string | null {
  if (value === null) return null
  if (typeof value === 'bigint' && value >= 0n) return value.toString()
  if (typeof value === 'string' && /^(0|[1-9][0-9]*)$/.test(value)) return value
  throw new Error('正準非負整数が必要です')
}

class MissingProjectionField extends Error {}
function _p(owner: unknown, path: string): unknown {
  for (const part of path.split('.')) {
    if (owner === null) return null
    if (typeof owner !== 'object' || Array.isArray(owner))
      throw new Error('閉入力の親型違い')
    if (!Object.hasOwn(owner, part))
      throw new MissingProjectionField('閉入力のfield不足')
    owner = (owner as Record<string, unknown>)[part]
  }
  return owner
}
function _n(value: unknown): bigint {
  return parseCount(value)
}

function _check(
  value: unknown,
  kind: string,
  nullable: boolean,
  minimum: string | null = null,
  maximum: string | null = null,
  allowed: readonly unknown[] | null = null,
): void {
  if (value === null && nullable) return
  if (allowed !== null && !allowed.includes(value)) throw new Error('未知enum')
  if (kind === 'integer') {
    if (
      typeof value === 'string' &&
      maximum !== null &&
      value.length > maximum.length
    )
      throw new Error('既有限field上限')
    const n = _n(value)
    if (minimum !== null && n < _n(minimum)) throw new Error('整数下限')
    if (maximum !== null && n > _n(maximum)) throw new Error('整数上限')
    return
  }
  if (kind === 'boolean' && typeof value === 'boolean') return
  if (kind === 'string' && typeof value === 'string') return
  throw new Error('閉入力の型違い')
}
function _checked_ref(
  owner: unknown,
  path: string,
  kind: string,
  nullable: boolean,
  minimum: string | null,
  maximum: string | null,
  allowed: readonly unknown[] | null,
): unknown {
  const value = _p(owner, path)
  _check(value, kind, nullable, minimum, maximum, allowed)
  return value
}
function _lookup(
  values: Readonly<Record<string, bigint>>,
  value: unknown,
): bigint {
  if (typeof value !== 'string' || !Object.hasOwn(values, value))
    throw new Error('未知enum')
  return values[value]!
}
type Credit = { player_id: string; quantity: string }
type Metric = {
  state: 'available' | 'source_unavailable'
  value: string | null
  display: string | null
  reason: string | null
  credits: Credit[]
}
function _appendCredit(
  credits: Credit[],
  player: string,
  amount: bigint,
): void {
  for (const credit of credits) {
    if (credit.player_id === player) {
      credit.quantity = addCounts(credit.quantity, amount)
      return
    }
  }
  credits.push({ player_id: player, quantity: formatCount(amount)! })
}
function _zero(): Metric {
  return {
    state: 'available',
    value: '0',
    display: '0',
    reason: null,
    credits: [],
  }
}
function _missing(
  reason: 'MISSING_OBSERVATION' | 'MISSING_ATTRIBUTION' = 'MISSING_OBSERVATION',
): Metric {
  return {
    state: 'source_unavailable',
    value: null,
    display: null,
    reason,
    credits: [],
  }
}
export function addCounts(left: unknown, right: unknown): string {
  return formatCount(_n(left) + _n(right))!
}
export function eventFacts(
  event: unknown,
  requestedMetrics?: readonly string[],
) {
  const knownMetrics = [
    'pitch_count',
    'pa',
    'ab',
    'h',
    'hr',
    'bb',
    'hbp',
    'k',
    'sh',
    'sf',
    'catcher_interference_reached',
    'runner_interference_reached',
    'doubles',
    'triples',
    'total_bases',
    'runs',
    'rbi',
    'stolen_bases',
    'pitching_outs',
    'pitcher_k',
    'pitcher_bb',
    'pitcher_hbp',
    'hits_allowed',
    'home_runs_allowed',
    'fielding_errors',
    'runs_allowed',
  ]
  if (
    requestedMetrics !== undefined &&
    (!Array.isArray(requestedMetrics) ||
      requestedMetrics.length > 26 ||
      requestedMetrics.some(
        (x) => typeof x !== 'string' || !knownMetrics.includes(x),
      ) ||
      new Set(requestedMetrics).size !== requestedMetrics.length)
  )
    throw new Error('primitive射影の有限型違い')
  {
    const record = _p(event, 'stat_flags')
    if (record === null || typeof record !== 'object' || Array.isArray(record))
      throw new Error('閉record型違い')
    let seen = 0
    for (const key in record) {
      if (!Object.hasOwn(record, key)) continue
      if (
        ++seen > 23 ||
        ![
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
        ].includes(key)
      )
        throw new Error('未知field')
    }
    if (seen !== 23) throw new Error('不足field')
  }
  if (requestedMetrics === undefined) {
    _check(_p(event, 'event_kind'), 'string', false, null, null, [
      'pitch',
      'non_pitch',
      'control',
    ])
    _check(_p(event, 'source.lifecycle'), 'string', false, null, null, [
      'effective',
      'replaced',
      'retired',
      'tombstone',
      'audit_control',
    ])
    _check(
      _p(event, 'source.source_event_id'),
      'string',
      false,
      null,
      null,
      null,
    )
    _check(_p(event, 'pa.ended_here'), 'boolean', false, null, null, null)
    _check(_p(event, 'pa.pa_id'), 'string', true, null, null, null)
    _check(_p(event, 'pa.ordinal_for_batter'), 'string', true, null, null, null)
    _check(_p(event, 'pa.hit_kind'), 'string', false, null, null, [
      'none',
      'single',
      'double',
      'triple',
      'home_run',
    ])
    _check(_p(event, 'pa.result_display'), 'string', true, null, null, null)
    _check(_p(event, 'pa.reached_by'), 'string', false, null, null, null)
    _check(_p(event, 'before.inning'), 'string', false, null, null, null)
    _check(_p(event, 'before.half'), 'string', false, null, null, null)
    _check(
      _p(event, 'out_effect.effective_count'),
      'integer',
      true,
      '0',
      '3',
      null,
    )
    _check(
      _p(event, 'stat_flags.投球回算入アウト'),
      'boolean',
      false,
      null,
      null,
      null,
    )
    _check(_p(event, 'stat_flags.投球数'), 'boolean', false, null, null, null)
    _check(_p(event, 'stat_flags.奪三振'), 'boolean', false, null, null, null)
    _check(_p(event, 'stat_flags.与四球'), 'boolean', false, null, null, null)
    _check(_p(event, 'stat_flags.与死球'), 'boolean', false, null, null, null)
    _check(_p(event, 'stat_flags.被安打'), 'boolean', false, null, null, null)
    _check(_p(event, 'stat_flags.被本塁打'), 'boolean', false, null, null, null)
    _check(_p(event, 'stat_flags.失点'), 'boolean', false, null, null, null)
    _check(_p(event, 'stat_flags.失策'), 'boolean', false, null, null, null)
    _check(_p(event, 'stat_flags.打席'), 'boolean', false, null, null, null)
    _check(_p(event, 'stat_flags.打数'), 'boolean', false, null, null, null)
    _check(_p(event, 'stat_flags.安打'), 'boolean', false, null, null, null)
    _check(_p(event, 'stat_flags.本塁打'), 'boolean', false, null, null, null)
    _check(_p(event, 'stat_flags.塁打'), 'boolean', false, null, null, null)
    _check(_p(event, 'stat_flags.犠打'), 'boolean', false, null, null, null)
    _check(_p(event, 'stat_flags.犠飛'), 'boolean', false, null, null, null)
    _check(_p(event, 'stat_flags.四球'), 'boolean', false, null, null, null)
    _check(_p(event, 'stat_flags.死球'), 'boolean', false, null, null, null)
    _check(_p(event, 'stat_flags.三振'), 'boolean', false, null, null, null)
    _check(
      _p(event, 'stat_flags.打撃妨害出塁'),
      'boolean',
      false,
      null,
      null,
      null,
    )
    _check(
      _p(event, 'stat_flags.走塁妨害出塁'),
      'boolean',
      false,
      null,
      null,
      null,
    )
    _check(_p(event, 'stat_flags.得点'), 'boolean', false, null, null, null)
    _check(_p(event, 'stat_flags.打点'), 'boolean', false, null, null, null)
    _check(_p(event, 'completeness.pa'), 'string', false, null, null, [
      'complete',
      'unavailable',
    ])
    _check(
      _p(event, 'completeness.participants'),
      'string',
      false,
      null,
      null,
      ['complete', 'unavailable'],
    )
    _check(_p(event, 'completeness.outs'), 'string', false, null, null, [
      'complete',
      'unavailable',
    ])
    _check(_p(event, 'completeness.runs_rbi'), 'string', false, null, null, [
      'complete',
      'unavailable',
    ])
    _check(_p(event, 'completeness.steals'), 'string', false, null, null, [
      'complete',
      'unavailable',
    ])
    _check(
      _p(event, 'participants.actual_pitcher_id'),
      'string',
      false,
      null,
      null,
      null,
    )
    _check(
      _p(event, 'participants.actual_batter_id'),
      'string',
      false,
      null,
      null,
      null,
    )
    _check(
      _p(event, 'participants.credited_batter_id'),
      'string',
      true,
      null,
      null,
      null,
    )
    _check(
      _p(event, 'participants.strikeout_pitcher_id'),
      'string',
      true,
      null,
      null,
      null,
    )
    _check(
      _p(event, 'participants.walk_pitcher_id'),
      'string',
      true,
      null,
      null,
      null,
    )
    _check(
      _p(event, 'participants.hbp_pitcher_id'),
      'string',
      true,
      null,
      null,
      null,
    )
    _check(
      _p(event, 'participants.hit_pitcher_id'),
      'string',
      true,
      null,
      null,
      null,
    )
    _check(
      _p(event, 'participants.home_run_pitcher_id'),
      'string',
      true,
      null,
      null,
      null,
    )
    _check(
      _p(event, 'participants.outs_pitcher_id'),
      'string',
      true,
      null,
      null,
      null,
    )
    _check(
      _p(event, 'participants.error_fielder_id'),
      'string',
      true,
      null,
      null,
      null,
    )
    {
      const collection = _p(event, 'runner_scores')
      if (collection !== null) {
        if (!Array.isArray(collection) || collection.length > 4)
          throw new Error('有限collection上限')
        for (const item of collection) {
          _check(_p(item, 'runner_id'), 'string', false)
          _check(_p(item, 'responsible_pitcher_id'), 'string', false)
          _check(_p(item, 'valid_run'), 'boolean', false)
          _check(_p(item, 'rbi_credited'), 'boolean', false)
          _check(_p(item, 'rbi_batter_id'), 'string', true)
          _check(_p(item, 'rbi_branch'), 'string', true)
        }
      }
    }
    {
      const collection = _p(event, 'steal_attempts')
      if (collection !== null) {
        if (!Array.isArray(collection) || collection.length > 3)
          throw new Error('有限collection上限')
        for (const item of collection) {
          _check(_p(item, 'runner_id'), 'string', false)
          _check(_p(item, 'attempted'), 'boolean', false)
          _check(_p(item, 'successful'), 'boolean', false)
        }
      }
    }
  }
  const metrics: Record<string, Metric> = {}
  for (const name of [
    'pitch_count',
    'pa',
    'ab',
    'h',
    'hr',
    'bb',
    'hbp',
    'k',
    'sh',
    'sf',
    'catcher_interference_reached',
    'runner_interference_reached',
    'doubles',
    'triples',
    'total_bases',
    'runs',
    'rbi',
    'stolen_bases',
    'pitching_outs',
    'pitcher_k',
    'pitcher_bb',
    'pitcher_hbp',
    'hits_allowed',
    'home_runs_allowed',
    'fielding_errors',
    'runs_allowed',
  ])
    if (requestedMetrics === undefined || requestedMetrics.includes(name))
      metrics[name] = _zero()
  const selected =
    _checked_ref(event, 'source.lifecycle', 'string', false, null, null, [
      'effective',
      'replaced',
      'retired',
      'tombstone',
      'audit_control',
    ]) === 'effective'
  if (selected) {
    try {
      if (
        requestedMetrics === undefined ||
        requestedMetrics.includes('pitch_count')
      ) {
        if (
          !(
            _checked_ref(
              event,
              'completeness.participants',
              'string',
              false,
              null,
              null,
              ['complete', 'unavailable'],
            ) === 'complete'
          )
        )
          metrics['pitch_count'] = _missing()
        else {
          let quantity = 0n
          const credits: Credit[] = []
          let missing = false
          if (
            _checked_ref(event, 'event_kind', 'string', false, null, null, [
              'pitch',
              'non_pitch',
              'control',
            ]) === 'pitch' &&
            _checked_ref(
              event,
              'stat_flags.投球数',
              'boolean',
              false,
              null,
              null,
              null,
            )
          ) {
            const amount = _n(1n)
            const player = _checked_ref(
              event,
              'participants.actual_pitcher_id',
              'string',
              false,
              null,
              null,
              null,
            )
            if (amount > 0n && typeof player !== 'string') missing = true
            else if (amount > 0n && typeof player === 'string') {
              quantity += amount
              _appendCredit(credits, player, amount)
            }
          }
          metrics['pitch_count'] = missing
            ? _missing('MISSING_ATTRIBUTION')
            : {
                state: 'available',
                value: formatCount(quantity),
                display: formatCount(quantity),
                reason: null,
                credits,
              }
        }
      }
    } catch (error) {
      if (
        requestedMetrics === undefined ||
        !(error instanceof MissingProjectionField)
      )
        throw error
      metrics['pitch_count'] = _missing()
    }
    try {
      if (requestedMetrics === undefined || requestedMetrics.includes('pa')) {
        if (!(
          _checked_ref(event, 'completeness.pa', 'string', false, null, null, [
            'complete',
            'unavailable',
          ]) === 'complete' &&
          _checked_ref(
            event,
            'completeness.participants',
            'string',
            false,
            null,
            null,
            ['complete', 'unavailable'],
          ) === 'complete'
        ))
          metrics['pa'] = _missing()
        else {
          let quantity = 0n
          const credits: Credit[] = []
          let missing = false
          if (
            _checked_ref(
              event,
              'pa.ended_here',
              'boolean',
              false,
              null,
              null,
              null,
            ) &&
            _checked_ref(
              event,
              'stat_flags.打席',
              'boolean',
              false,
              null,
              null,
              null,
            )
          ) {
            const amount = _n(1n)
            const player = _checked_ref(
              event,
              'participants.credited_batter_id',
              'string',
              true,
              null,
              null,
              null,
            )
            if (amount > 0n && typeof player !== 'string') missing = true
            else if (amount > 0n && typeof player === 'string') {
              quantity += amount
              _appendCredit(credits, player, amount)
            }
          }
          metrics['pa'] = missing
            ? _missing('MISSING_ATTRIBUTION')
            : {
                state: 'available',
                value: formatCount(quantity),
                display: formatCount(quantity),
                reason: null,
                credits,
              }
        }
      }
    } catch (error) {
      if (
        requestedMetrics === undefined ||
        !(error instanceof MissingProjectionField)
      )
        throw error
      metrics['pa'] = _missing()
    }
    try {
      if (requestedMetrics === undefined || requestedMetrics.includes('ab')) {
        if (!(
          _checked_ref(event, 'completeness.pa', 'string', false, null, null, [
            'complete',
            'unavailable',
          ]) === 'complete' &&
          _checked_ref(
            event,
            'completeness.participants',
            'string',
            false,
            null,
            null,
            ['complete', 'unavailable'],
          ) === 'complete'
        ))
          metrics['ab'] = _missing()
        else {
          let quantity = 0n
          const credits: Credit[] = []
          let missing = false
          if (
            _checked_ref(
              event,
              'pa.ended_here',
              'boolean',
              false,
              null,
              null,
              null,
            ) &&
            _checked_ref(
              event,
              'stat_flags.打数',
              'boolean',
              false,
              null,
              null,
              null,
            )
          ) {
            const amount = _n(1n)
            const player = _checked_ref(
              event,
              'participants.credited_batter_id',
              'string',
              true,
              null,
              null,
              null,
            )
            if (amount > 0n && typeof player !== 'string') missing = true
            else if (amount > 0n && typeof player === 'string') {
              quantity += amount
              _appendCredit(credits, player, amount)
            }
          }
          metrics['ab'] = missing
            ? _missing('MISSING_ATTRIBUTION')
            : {
                state: 'available',
                value: formatCount(quantity),
                display: formatCount(quantity),
                reason: null,
                credits,
              }
        }
      }
    } catch (error) {
      if (
        requestedMetrics === undefined ||
        !(error instanceof MissingProjectionField)
      )
        throw error
      metrics['ab'] = _missing()
    }
    try {
      if (requestedMetrics === undefined || requestedMetrics.includes('h')) {
        if (!(
          _checked_ref(event, 'completeness.pa', 'string', false, null, null, [
            'complete',
            'unavailable',
          ]) === 'complete' &&
          _checked_ref(
            event,
            'completeness.participants',
            'string',
            false,
            null,
            null,
            ['complete', 'unavailable'],
          ) === 'complete'
        ))
          metrics['h'] = _missing()
        else {
          let quantity = 0n
          const credits: Credit[] = []
          let missing = false
          if (
            _checked_ref(
              event,
              'pa.ended_here',
              'boolean',
              false,
              null,
              null,
              null,
            ) &&
            _checked_ref(
              event,
              'stat_flags.安打',
              'boolean',
              false,
              null,
              null,
              null,
            )
          ) {
            const amount = _n(1n)
            const player = _checked_ref(
              event,
              'participants.credited_batter_id',
              'string',
              true,
              null,
              null,
              null,
            )
            if (amount > 0n && typeof player !== 'string') missing = true
            else if (amount > 0n && typeof player === 'string') {
              quantity += amount
              _appendCredit(credits, player, amount)
            }
          }
          metrics['h'] = missing
            ? _missing('MISSING_ATTRIBUTION')
            : {
                state: 'available',
                value: formatCount(quantity),
                display: formatCount(quantity),
                reason: null,
                credits,
              }
        }
      }
    } catch (error) {
      if (
        requestedMetrics === undefined ||
        !(error instanceof MissingProjectionField)
      )
        throw error
      metrics['h'] = _missing()
    }
    try {
      if (requestedMetrics === undefined || requestedMetrics.includes('hr')) {
        if (!(
          _checked_ref(event, 'completeness.pa', 'string', false, null, null, [
            'complete',
            'unavailable',
          ]) === 'complete' &&
          _checked_ref(
            event,
            'completeness.participants',
            'string',
            false,
            null,
            null,
            ['complete', 'unavailable'],
          ) === 'complete'
        ))
          metrics['hr'] = _missing()
        else {
          let quantity = 0n
          const credits: Credit[] = []
          let missing = false
          if (
            _checked_ref(
              event,
              'pa.ended_here',
              'boolean',
              false,
              null,
              null,
              null,
            ) &&
            _checked_ref(
              event,
              'stat_flags.本塁打',
              'boolean',
              false,
              null,
              null,
              null,
            )
          ) {
            const amount = _n(1n)
            const player = _checked_ref(
              event,
              'participants.credited_batter_id',
              'string',
              true,
              null,
              null,
              null,
            )
            if (amount > 0n && typeof player !== 'string') missing = true
            else if (amount > 0n && typeof player === 'string') {
              quantity += amount
              _appendCredit(credits, player, amount)
            }
          }
          metrics['hr'] = missing
            ? _missing('MISSING_ATTRIBUTION')
            : {
                state: 'available',
                value: formatCount(quantity),
                display: formatCount(quantity),
                reason: null,
                credits,
              }
        }
      }
    } catch (error) {
      if (
        requestedMetrics === undefined ||
        !(error instanceof MissingProjectionField)
      )
        throw error
      metrics['hr'] = _missing()
    }
    try {
      if (requestedMetrics === undefined || requestedMetrics.includes('bb')) {
        if (!(
          _checked_ref(event, 'completeness.pa', 'string', false, null, null, [
            'complete',
            'unavailable',
          ]) === 'complete' &&
          _checked_ref(
            event,
            'completeness.participants',
            'string',
            false,
            null,
            null,
            ['complete', 'unavailable'],
          ) === 'complete'
        ))
          metrics['bb'] = _missing()
        else {
          let quantity = 0n
          const credits: Credit[] = []
          let missing = false
          if (
            _checked_ref(
              event,
              'pa.ended_here',
              'boolean',
              false,
              null,
              null,
              null,
            ) &&
            _checked_ref(
              event,
              'stat_flags.四球',
              'boolean',
              false,
              null,
              null,
              null,
            )
          ) {
            const amount = _n(1n)
            const player = _checked_ref(
              event,
              'participants.credited_batter_id',
              'string',
              true,
              null,
              null,
              null,
            )
            if (amount > 0n && typeof player !== 'string') missing = true
            else if (amount > 0n && typeof player === 'string') {
              quantity += amount
              _appendCredit(credits, player, amount)
            }
          }
          metrics['bb'] = missing
            ? _missing('MISSING_ATTRIBUTION')
            : {
                state: 'available',
                value: formatCount(quantity),
                display: formatCount(quantity),
                reason: null,
                credits,
              }
        }
      }
    } catch (error) {
      if (
        requestedMetrics === undefined ||
        !(error instanceof MissingProjectionField)
      )
        throw error
      metrics['bb'] = _missing()
    }
    try {
      if (requestedMetrics === undefined || requestedMetrics.includes('hbp')) {
        if (!(
          _checked_ref(event, 'completeness.pa', 'string', false, null, null, [
            'complete',
            'unavailable',
          ]) === 'complete' &&
          _checked_ref(
            event,
            'completeness.participants',
            'string',
            false,
            null,
            null,
            ['complete', 'unavailable'],
          ) === 'complete'
        ))
          metrics['hbp'] = _missing()
        else {
          let quantity = 0n
          const credits: Credit[] = []
          let missing = false
          if (
            _checked_ref(
              event,
              'pa.ended_here',
              'boolean',
              false,
              null,
              null,
              null,
            ) &&
            _checked_ref(
              event,
              'stat_flags.死球',
              'boolean',
              false,
              null,
              null,
              null,
            )
          ) {
            const amount = _n(1n)
            const player = _checked_ref(
              event,
              'participants.credited_batter_id',
              'string',
              true,
              null,
              null,
              null,
            )
            if (amount > 0n && typeof player !== 'string') missing = true
            else if (amount > 0n && typeof player === 'string') {
              quantity += amount
              _appendCredit(credits, player, amount)
            }
          }
          metrics['hbp'] = missing
            ? _missing('MISSING_ATTRIBUTION')
            : {
                state: 'available',
                value: formatCount(quantity),
                display: formatCount(quantity),
                reason: null,
                credits,
              }
        }
      }
    } catch (error) {
      if (
        requestedMetrics === undefined ||
        !(error instanceof MissingProjectionField)
      )
        throw error
      metrics['hbp'] = _missing()
    }
    try {
      if (requestedMetrics === undefined || requestedMetrics.includes('k')) {
        if (!(
          _checked_ref(event, 'completeness.pa', 'string', false, null, null, [
            'complete',
            'unavailable',
          ]) === 'complete' &&
          _checked_ref(
            event,
            'completeness.participants',
            'string',
            false,
            null,
            null,
            ['complete', 'unavailable'],
          ) === 'complete'
        ))
          metrics['k'] = _missing()
        else {
          let quantity = 0n
          const credits: Credit[] = []
          let missing = false
          if (
            _checked_ref(
              event,
              'pa.ended_here',
              'boolean',
              false,
              null,
              null,
              null,
            ) &&
            _checked_ref(
              event,
              'stat_flags.三振',
              'boolean',
              false,
              null,
              null,
              null,
            )
          ) {
            const amount = _n(1n)
            const player = _checked_ref(
              event,
              'participants.credited_batter_id',
              'string',
              true,
              null,
              null,
              null,
            )
            if (amount > 0n && typeof player !== 'string') missing = true
            else if (amount > 0n && typeof player === 'string') {
              quantity += amount
              _appendCredit(credits, player, amount)
            }
          }
          metrics['k'] = missing
            ? _missing('MISSING_ATTRIBUTION')
            : {
                state: 'available',
                value: formatCount(quantity),
                display: formatCount(quantity),
                reason: null,
                credits,
              }
        }
      }
    } catch (error) {
      if (
        requestedMetrics === undefined ||
        !(error instanceof MissingProjectionField)
      )
        throw error
      metrics['k'] = _missing()
    }
    try {
      if (requestedMetrics === undefined || requestedMetrics.includes('sh')) {
        if (!(
          _checked_ref(event, 'completeness.pa', 'string', false, null, null, [
            'complete',
            'unavailable',
          ]) === 'complete' &&
          _checked_ref(
            event,
            'completeness.participants',
            'string',
            false,
            null,
            null,
            ['complete', 'unavailable'],
          ) === 'complete'
        ))
          metrics['sh'] = _missing()
        else {
          let quantity = 0n
          const credits: Credit[] = []
          let missing = false
          if (
            _checked_ref(
              event,
              'pa.ended_here',
              'boolean',
              false,
              null,
              null,
              null,
            ) &&
            _checked_ref(
              event,
              'stat_flags.犠打',
              'boolean',
              false,
              null,
              null,
              null,
            )
          ) {
            const amount = _n(1n)
            const player = _checked_ref(
              event,
              'participants.credited_batter_id',
              'string',
              true,
              null,
              null,
              null,
            )
            if (amount > 0n && typeof player !== 'string') missing = true
            else if (amount > 0n && typeof player === 'string') {
              quantity += amount
              _appendCredit(credits, player, amount)
            }
          }
          metrics['sh'] = missing
            ? _missing('MISSING_ATTRIBUTION')
            : {
                state: 'available',
                value: formatCount(quantity),
                display: formatCount(quantity),
                reason: null,
                credits,
              }
        }
      }
    } catch (error) {
      if (
        requestedMetrics === undefined ||
        !(error instanceof MissingProjectionField)
      )
        throw error
      metrics['sh'] = _missing()
    }
    try {
      if (requestedMetrics === undefined || requestedMetrics.includes('sf')) {
        if (!(
          _checked_ref(event, 'completeness.pa', 'string', false, null, null, [
            'complete',
            'unavailable',
          ]) === 'complete' &&
          _checked_ref(
            event,
            'completeness.participants',
            'string',
            false,
            null,
            null,
            ['complete', 'unavailable'],
          ) === 'complete'
        ))
          metrics['sf'] = _missing()
        else {
          let quantity = 0n
          const credits: Credit[] = []
          let missing = false
          if (
            _checked_ref(
              event,
              'pa.ended_here',
              'boolean',
              false,
              null,
              null,
              null,
            ) &&
            _checked_ref(
              event,
              'stat_flags.犠飛',
              'boolean',
              false,
              null,
              null,
              null,
            )
          ) {
            const amount = _n(1n)
            const player = _checked_ref(
              event,
              'participants.credited_batter_id',
              'string',
              true,
              null,
              null,
              null,
            )
            if (amount > 0n && typeof player !== 'string') missing = true
            else if (amount > 0n && typeof player === 'string') {
              quantity += amount
              _appendCredit(credits, player, amount)
            }
          }
          metrics['sf'] = missing
            ? _missing('MISSING_ATTRIBUTION')
            : {
                state: 'available',
                value: formatCount(quantity),
                display: formatCount(quantity),
                reason: null,
                credits,
              }
        }
      }
    } catch (error) {
      if (
        requestedMetrics === undefined ||
        !(error instanceof MissingProjectionField)
      )
        throw error
      metrics['sf'] = _missing()
    }
    try {
      if (
        requestedMetrics === undefined ||
        requestedMetrics.includes('catcher_interference_reached')
      ) {
        if (!(
          _checked_ref(event, 'completeness.pa', 'string', false, null, null, [
            'complete',
            'unavailable',
          ]) === 'complete' &&
          _checked_ref(
            event,
            'completeness.participants',
            'string',
            false,
            null,
            null,
            ['complete', 'unavailable'],
          ) === 'complete'
        ))
          metrics['catcher_interference_reached'] = _missing()
        else {
          let quantity = 0n
          const credits: Credit[] = []
          let missing = false
          if (
            _checked_ref(
              event,
              'pa.ended_here',
              'boolean',
              false,
              null,
              null,
              null,
            ) &&
            _checked_ref(
              event,
              'stat_flags.打撃妨害出塁',
              'boolean',
              false,
              null,
              null,
              null,
            )
          ) {
            const amount = _n(1n)
            const player = _checked_ref(
              event,
              'participants.credited_batter_id',
              'string',
              true,
              null,
              null,
              null,
            )
            if (amount > 0n && typeof player !== 'string') missing = true
            else if (amount > 0n && typeof player === 'string') {
              quantity += amount
              _appendCredit(credits, player, amount)
            }
          }
          metrics['catcher_interference_reached'] = missing
            ? _missing('MISSING_ATTRIBUTION')
            : {
                state: 'available',
                value: formatCount(quantity),
                display: formatCount(quantity),
                reason: null,
                credits,
              }
        }
      }
    } catch (error) {
      if (
        requestedMetrics === undefined ||
        !(error instanceof MissingProjectionField)
      )
        throw error
      metrics['catcher_interference_reached'] = _missing()
    }
    try {
      if (
        requestedMetrics === undefined ||
        requestedMetrics.includes('runner_interference_reached')
      ) {
        if (!(
          _checked_ref(event, 'completeness.pa', 'string', false, null, null, [
            'complete',
            'unavailable',
          ]) === 'complete' &&
          _checked_ref(
            event,
            'completeness.participants',
            'string',
            false,
            null,
            null,
            ['complete', 'unavailable'],
          ) === 'complete'
        ))
          metrics['runner_interference_reached'] = _missing()
        else {
          let quantity = 0n
          const credits: Credit[] = []
          let missing = false
          if (
            _checked_ref(
              event,
              'pa.ended_here',
              'boolean',
              false,
              null,
              null,
              null,
            ) &&
            _checked_ref(
              event,
              'stat_flags.走塁妨害出塁',
              'boolean',
              false,
              null,
              null,
              null,
            )
          ) {
            const amount = _n(1n)
            const player = _checked_ref(
              event,
              'participants.credited_batter_id',
              'string',
              true,
              null,
              null,
              null,
            )
            if (amount > 0n && typeof player !== 'string') missing = true
            else if (amount > 0n && typeof player === 'string') {
              quantity += amount
              _appendCredit(credits, player, amount)
            }
          }
          metrics['runner_interference_reached'] = missing
            ? _missing('MISSING_ATTRIBUTION')
            : {
                state: 'available',
                value: formatCount(quantity),
                display: formatCount(quantity),
                reason: null,
                credits,
              }
        }
      }
    } catch (error) {
      if (
        requestedMetrics === undefined ||
        !(error instanceof MissingProjectionField)
      )
        throw error
      metrics['runner_interference_reached'] = _missing()
    }
    try {
      if (
        requestedMetrics === undefined ||
        requestedMetrics.includes('doubles')
      ) {
        if (!(
          _checked_ref(event, 'completeness.pa', 'string', false, null, null, [
            'complete',
            'unavailable',
          ]) === 'complete' &&
          _checked_ref(
            event,
            'completeness.participants',
            'string',
            false,
            null,
            null,
            ['complete', 'unavailable'],
          ) === 'complete'
        ))
          metrics['doubles'] = _missing()
        else {
          let quantity = 0n
          const credits: Credit[] = []
          let missing = false
          if (
            _checked_ref(
              event,
              'pa.ended_here',
              'boolean',
              false,
              null,
              null,
              null,
            ) &&
            _checked_ref(
              event,
              'stat_flags.安打',
              'boolean',
              false,
              null,
              null,
              null,
            ) &&
            _checked_ref(event, 'pa.hit_kind', 'string', false, null, null, [
              'none',
              'single',
              'double',
              'triple',
              'home_run',
            ]) === 'double'
          ) {
            const amount = _n(1n)
            const player = _checked_ref(
              event,
              'participants.credited_batter_id',
              'string',
              true,
              null,
              null,
              null,
            )
            if (amount > 0n && typeof player !== 'string') missing = true
            else if (amount > 0n && typeof player === 'string') {
              quantity += amount
              _appendCredit(credits, player, amount)
            }
          }
          metrics['doubles'] = missing
            ? _missing('MISSING_ATTRIBUTION')
            : {
                state: 'available',
                value: formatCount(quantity),
                display: formatCount(quantity),
                reason: null,
                credits,
              }
        }
      }
    } catch (error) {
      if (
        requestedMetrics === undefined ||
        !(error instanceof MissingProjectionField)
      )
        throw error
      metrics['doubles'] = _missing()
    }
    try {
      if (
        requestedMetrics === undefined ||
        requestedMetrics.includes('triples')
      ) {
        if (!(
          _checked_ref(event, 'completeness.pa', 'string', false, null, null, [
            'complete',
            'unavailable',
          ]) === 'complete' &&
          _checked_ref(
            event,
            'completeness.participants',
            'string',
            false,
            null,
            null,
            ['complete', 'unavailable'],
          ) === 'complete'
        ))
          metrics['triples'] = _missing()
        else {
          let quantity = 0n
          const credits: Credit[] = []
          let missing = false
          if (
            _checked_ref(
              event,
              'pa.ended_here',
              'boolean',
              false,
              null,
              null,
              null,
            ) &&
            _checked_ref(
              event,
              'stat_flags.安打',
              'boolean',
              false,
              null,
              null,
              null,
            ) &&
            _checked_ref(event, 'pa.hit_kind', 'string', false, null, null, [
              'none',
              'single',
              'double',
              'triple',
              'home_run',
            ]) === 'triple'
          ) {
            const amount = _n(1n)
            const player = _checked_ref(
              event,
              'participants.credited_batter_id',
              'string',
              true,
              null,
              null,
              null,
            )
            if (amount > 0n && typeof player !== 'string') missing = true
            else if (amount > 0n && typeof player === 'string') {
              quantity += amount
              _appendCredit(credits, player, amount)
            }
          }
          metrics['triples'] = missing
            ? _missing('MISSING_ATTRIBUTION')
            : {
                state: 'available',
                value: formatCount(quantity),
                display: formatCount(quantity),
                reason: null,
                credits,
              }
        }
      }
    } catch (error) {
      if (
        requestedMetrics === undefined ||
        !(error instanceof MissingProjectionField)
      )
        throw error
      metrics['triples'] = _missing()
    }
    try {
      if (
        requestedMetrics === undefined ||
        requestedMetrics.includes('total_bases')
      ) {
        if (!(
          _checked_ref(event, 'completeness.pa', 'string', false, null, null, [
            'complete',
            'unavailable',
          ]) === 'complete' &&
          _checked_ref(
            event,
            'completeness.participants',
            'string',
            false,
            null,
            null,
            ['complete', 'unavailable'],
          ) === 'complete'
        ))
          metrics['total_bases'] = _missing()
        else {
          let quantity = 0n
          const credits: Credit[] = []
          let missing = false
          if (
            _checked_ref(
              event,
              'pa.ended_here',
              'boolean',
              false,
              null,
              null,
              null,
            ) &&
            _checked_ref(
              event,
              'stat_flags.塁打',
              'boolean',
              false,
              null,
              null,
              null,
            )
          ) {
            const amount = _n(
              _lookup(
                { none: 0n, single: 1n, double: 2n, triple: 3n, home_run: 4n },
                _checked_ref(
                  event,
                  'pa.hit_kind',
                  'string',
                  false,
                  null,
                  null,
                  ['none', 'single', 'double', 'triple', 'home_run'],
                ),
              ),
            )
            const player = _checked_ref(
              event,
              'participants.credited_batter_id',
              'string',
              true,
              null,
              null,
              null,
            )
            if (amount > 0n && typeof player !== 'string') missing = true
            else if (amount > 0n && typeof player === 'string') {
              quantity += amount
              _appendCredit(credits, player, amount)
            }
          }
          metrics['total_bases'] = missing
            ? _missing('MISSING_ATTRIBUTION')
            : {
                state: 'available',
                value: formatCount(quantity),
                display: formatCount(quantity),
                reason: null,
                credits,
              }
        }
      }
    } catch (error) {
      if (
        requestedMetrics === undefined ||
        !(error instanceof MissingProjectionField)
      )
        throw error
      metrics['total_bases'] = _missing()
    }
    try {
      if (requestedMetrics === undefined || requestedMetrics.includes('runs')) {
        if (
          !(
            _checked_ref(
              event,
              'completeness.runs_rbi',
              'string',
              false,
              null,
              null,
              ['complete', 'unavailable'],
            ) === 'complete'
          )
        )
          metrics['runs'] = _missing()
        else {
          let quantity = 0n
          const credits: Credit[] = []
          let missing = false
          const collection = _p(event, 'runner_scores')
          if (collection === null) missing = true
          else {
            if (!Array.isArray(collection) || collection.length > 4)
              throw new Error('collection型違い')
            for (const item of collection) {
              if (
                _checked_ref(
                  event,
                  'stat_flags.得点',
                  'boolean',
                  false,
                  null,
                  null,
                  null,
                ) &&
                _checked_ref(
                  item,
                  'valid_run',
                  'boolean',
                  false,
                  null,
                  null,
                  null,
                )
              ) {
                const amount = _n(1n)
                const player = _checked_ref(
                  item,
                  'runner_id',
                  'string',
                  false,
                  null,
                  null,
                  null,
                )
                if (amount > 0n && typeof player !== 'string') missing = true
                else if (amount > 0n && typeof player === 'string') {
                  quantity += amount
                  _appendCredit(credits, player, amount)
                }
              }
            }
          }
          metrics['runs'] = missing
            ? _missing('MISSING_ATTRIBUTION')
            : {
                state: 'available',
                value: formatCount(quantity),
                display: formatCount(quantity),
                reason: null,
                credits,
              }
        }
      }
    } catch (error) {
      if (
        requestedMetrics === undefined ||
        !(error instanceof MissingProjectionField)
      )
        throw error
      metrics['runs'] = _missing()
    }
    try {
      if (requestedMetrics === undefined || requestedMetrics.includes('rbi')) {
        if (
          !(
            _checked_ref(
              event,
              'completeness.runs_rbi',
              'string',
              false,
              null,
              null,
              ['complete', 'unavailable'],
            ) === 'complete'
          )
        )
          metrics['rbi'] = _missing()
        else {
          let quantity = 0n
          const credits: Credit[] = []
          let missing = false
          const collection = _p(event, 'runner_scores')
          if (collection === null) missing = true
          else {
            if (!Array.isArray(collection) || collection.length > 4)
              throw new Error('collection型違い')
            for (const item of collection) {
              if (
                _checked_ref(
                  event,
                  'stat_flags.打点',
                  'boolean',
                  false,
                  null,
                  null,
                  null,
                ) &&
                _checked_ref(
                  item,
                  'valid_run',
                  'boolean',
                  false,
                  null,
                  null,
                  null,
                ) &&
                _checked_ref(
                  item,
                  'rbi_credited',
                  'boolean',
                  false,
                  null,
                  null,
                  null,
                )
              ) {
                const amount = _n(1n)
                const player = _checked_ref(
                  item,
                  'rbi_batter_id',
                  'string',
                  true,
                  null,
                  null,
                  null,
                )
                if (amount > 0n && typeof player !== 'string') missing = true
                else if (amount > 0n && typeof player === 'string') {
                  quantity += amount
                  _appendCredit(credits, player, amount)
                }
              }
            }
          }
          metrics['rbi'] = missing
            ? _missing('MISSING_ATTRIBUTION')
            : {
                state: 'available',
                value: formatCount(quantity),
                display: formatCount(quantity),
                reason: null,
                credits,
              }
        }
      }
    } catch (error) {
      if (
        requestedMetrics === undefined ||
        !(error instanceof MissingProjectionField)
      )
        throw error
      metrics['rbi'] = _missing()
    }
    try {
      if (
        requestedMetrics === undefined ||
        requestedMetrics.includes('stolen_bases')
      ) {
        if (
          !(
            _checked_ref(
              event,
              'completeness.steals',
              'string',
              false,
              null,
              null,
              ['complete', 'unavailable'],
            ) === 'complete'
          )
        )
          metrics['stolen_bases'] = _missing()
        else {
          let quantity = 0n
          const credits: Credit[] = []
          let missing = false
          const collection = _p(event, 'steal_attempts')
          if (collection === null) missing = true
          else {
            if (!Array.isArray(collection) || collection.length > 3)
              throw new Error('collection型違い')
            for (const item of collection) {
              if (
                _checked_ref(
                  item,
                  'attempted',
                  'boolean',
                  false,
                  null,
                  null,
                  null,
                ) &&
                _checked_ref(
                  item,
                  'successful',
                  'boolean',
                  false,
                  null,
                  null,
                  null,
                )
              ) {
                const amount = _n(1n)
                const player = _checked_ref(
                  item,
                  'runner_id',
                  'string',
                  false,
                  null,
                  null,
                  null,
                )
                if (amount > 0n && typeof player !== 'string') missing = true
                else if (amount > 0n && typeof player === 'string') {
                  quantity += amount
                  _appendCredit(credits, player, amount)
                }
              }
            }
          }
          metrics['stolen_bases'] = missing
            ? _missing('MISSING_ATTRIBUTION')
            : {
                state: 'available',
                value: formatCount(quantity),
                display: formatCount(quantity),
                reason: null,
                credits,
              }
        }
      }
    } catch (error) {
      if (
        requestedMetrics === undefined ||
        !(error instanceof MissingProjectionField)
      )
        throw error
      metrics['stolen_bases'] = _missing()
    }
    try {
      if (
        requestedMetrics === undefined ||
        requestedMetrics.includes('pitching_outs')
      ) {
        if (!(
          _checked_ref(
            event,
            'completeness.outs',
            'string',
            false,
            null,
            null,
            ['complete', 'unavailable'],
          ) === 'complete' &&
          _checked_ref(
            event,
            'completeness.participants',
            'string',
            false,
            null,
            null,
            ['complete', 'unavailable'],
          ) === 'complete'
        ))
          metrics['pitching_outs'] = _missing()
        else {
          let quantity = 0n
          const credits: Credit[] = []
          let missing = false
          if (
            _checked_ref(
              event,
              'stat_flags.投球回算入アウト',
              'boolean',
              false,
              null,
              null,
              null,
            )
          ) {
            const amount = _n(
              _n(
                _checked_ref(
                  event,
                  'out_effect.effective_count',
                  'integer',
                  true,
                  '0',
                  '3',
                  null,
                ),
              ),
            )
            const player = _checked_ref(
              event,
              'participants.outs_pitcher_id',
              'string',
              true,
              null,
              null,
              null,
            )
            if (amount > 0n && typeof player !== 'string') missing = true
            else if (amount > 0n && typeof player === 'string') {
              quantity += amount
              _appendCredit(credits, player, amount)
            }
          }
          metrics['pitching_outs'] = missing
            ? _missing('MISSING_ATTRIBUTION')
            : {
                state: 'available',
                value: formatCount(quantity),
                display: formatCount(quantity),
                reason: null,
                credits,
              }
        }
      }
    } catch (error) {
      if (
        requestedMetrics === undefined ||
        !(error instanceof MissingProjectionField)
      )
        throw error
      metrics['pitching_outs'] = _missing()
    }
    try {
      if (
        requestedMetrics === undefined ||
        requestedMetrics.includes('pitcher_k')
      ) {
        if (
          !(
            _checked_ref(
              event,
              'completeness.participants',
              'string',
              false,
              null,
              null,
              ['complete', 'unavailable'],
            ) === 'complete'
          )
        )
          metrics['pitcher_k'] = _missing()
        else {
          let quantity = 0n
          const credits: Credit[] = []
          let missing = false
          if (
            _checked_ref(
              event,
              'stat_flags.奪三振',
              'boolean',
              false,
              null,
              null,
              null,
            )
          ) {
            const amount = _n(1n)
            const player = _checked_ref(
              event,
              'participants.strikeout_pitcher_id',
              'string',
              true,
              null,
              null,
              null,
            )
            if (amount > 0n && typeof player !== 'string') missing = true
            else if (amount > 0n && typeof player === 'string') {
              quantity += amount
              _appendCredit(credits, player, amount)
            }
          }
          metrics['pitcher_k'] = missing
            ? _missing('MISSING_ATTRIBUTION')
            : {
                state: 'available',
                value: formatCount(quantity),
                display: formatCount(quantity),
                reason: null,
                credits,
              }
        }
      }
    } catch (error) {
      if (
        requestedMetrics === undefined ||
        !(error instanceof MissingProjectionField)
      )
        throw error
      metrics['pitcher_k'] = _missing()
    }
    try {
      if (
        requestedMetrics === undefined ||
        requestedMetrics.includes('pitcher_bb')
      ) {
        if (
          !(
            _checked_ref(
              event,
              'completeness.participants',
              'string',
              false,
              null,
              null,
              ['complete', 'unavailable'],
            ) === 'complete'
          )
        )
          metrics['pitcher_bb'] = _missing()
        else {
          let quantity = 0n
          const credits: Credit[] = []
          let missing = false
          if (
            _checked_ref(
              event,
              'stat_flags.与四球',
              'boolean',
              false,
              null,
              null,
              null,
            )
          ) {
            const amount = _n(1n)
            const player = _checked_ref(
              event,
              'participants.walk_pitcher_id',
              'string',
              true,
              null,
              null,
              null,
            )
            if (amount > 0n && typeof player !== 'string') missing = true
            else if (amount > 0n && typeof player === 'string') {
              quantity += amount
              _appendCredit(credits, player, amount)
            }
          }
          metrics['pitcher_bb'] = missing
            ? _missing('MISSING_ATTRIBUTION')
            : {
                state: 'available',
                value: formatCount(quantity),
                display: formatCount(quantity),
                reason: null,
                credits,
              }
        }
      }
    } catch (error) {
      if (
        requestedMetrics === undefined ||
        !(error instanceof MissingProjectionField)
      )
        throw error
      metrics['pitcher_bb'] = _missing()
    }
    try {
      if (
        requestedMetrics === undefined ||
        requestedMetrics.includes('pitcher_hbp')
      ) {
        if (
          !(
            _checked_ref(
              event,
              'completeness.participants',
              'string',
              false,
              null,
              null,
              ['complete', 'unavailable'],
            ) === 'complete'
          )
        )
          metrics['pitcher_hbp'] = _missing()
        else {
          let quantity = 0n
          const credits: Credit[] = []
          let missing = false
          if (
            _checked_ref(
              event,
              'stat_flags.与死球',
              'boolean',
              false,
              null,
              null,
              null,
            )
          ) {
            const amount = _n(1n)
            const player = _checked_ref(
              event,
              'participants.hbp_pitcher_id',
              'string',
              true,
              null,
              null,
              null,
            )
            if (amount > 0n && typeof player !== 'string') missing = true
            else if (amount > 0n && typeof player === 'string') {
              quantity += amount
              _appendCredit(credits, player, amount)
            }
          }
          metrics['pitcher_hbp'] = missing
            ? _missing('MISSING_ATTRIBUTION')
            : {
                state: 'available',
                value: formatCount(quantity),
                display: formatCount(quantity),
                reason: null,
                credits,
              }
        }
      }
    } catch (error) {
      if (
        requestedMetrics === undefined ||
        !(error instanceof MissingProjectionField)
      )
        throw error
      metrics['pitcher_hbp'] = _missing()
    }
    try {
      if (
        requestedMetrics === undefined ||
        requestedMetrics.includes('hits_allowed')
      ) {
        if (
          !(
            _checked_ref(
              event,
              'completeness.participants',
              'string',
              false,
              null,
              null,
              ['complete', 'unavailable'],
            ) === 'complete'
          )
        )
          metrics['hits_allowed'] = _missing()
        else {
          let quantity = 0n
          const credits: Credit[] = []
          let missing = false
          if (
            _checked_ref(
              event,
              'stat_flags.被安打',
              'boolean',
              false,
              null,
              null,
              null,
            )
          ) {
            const amount = _n(1n)
            const player = _checked_ref(
              event,
              'participants.hit_pitcher_id',
              'string',
              true,
              null,
              null,
              null,
            )
            if (amount > 0n && typeof player !== 'string') missing = true
            else if (amount > 0n && typeof player === 'string') {
              quantity += amount
              _appendCredit(credits, player, amount)
            }
          }
          metrics['hits_allowed'] = missing
            ? _missing('MISSING_ATTRIBUTION')
            : {
                state: 'available',
                value: formatCount(quantity),
                display: formatCount(quantity),
                reason: null,
                credits,
              }
        }
      }
    } catch (error) {
      if (
        requestedMetrics === undefined ||
        !(error instanceof MissingProjectionField)
      )
        throw error
      metrics['hits_allowed'] = _missing()
    }
    try {
      if (
        requestedMetrics === undefined ||
        requestedMetrics.includes('home_runs_allowed')
      ) {
        if (
          !(
            _checked_ref(
              event,
              'completeness.participants',
              'string',
              false,
              null,
              null,
              ['complete', 'unavailable'],
            ) === 'complete'
          )
        )
          metrics['home_runs_allowed'] = _missing()
        else {
          let quantity = 0n
          const credits: Credit[] = []
          let missing = false
          if (
            _checked_ref(
              event,
              'stat_flags.被本塁打',
              'boolean',
              false,
              null,
              null,
              null,
            )
          ) {
            const amount = _n(1n)
            const player = _checked_ref(
              event,
              'participants.home_run_pitcher_id',
              'string',
              true,
              null,
              null,
              null,
            )
            if (amount > 0n && typeof player !== 'string') missing = true
            else if (amount > 0n && typeof player === 'string') {
              quantity += amount
              _appendCredit(credits, player, amount)
            }
          }
          metrics['home_runs_allowed'] = missing
            ? _missing('MISSING_ATTRIBUTION')
            : {
                state: 'available',
                value: formatCount(quantity),
                display: formatCount(quantity),
                reason: null,
                credits,
              }
        }
      }
    } catch (error) {
      if (
        requestedMetrics === undefined ||
        !(error instanceof MissingProjectionField)
      )
        throw error
      metrics['home_runs_allowed'] = _missing()
    }
    try {
      if (
        requestedMetrics === undefined ||
        requestedMetrics.includes('fielding_errors')
      ) {
        if (
          !(
            _checked_ref(
              event,
              'completeness.participants',
              'string',
              false,
              null,
              null,
              ['complete', 'unavailable'],
            ) === 'complete'
          )
        )
          metrics['fielding_errors'] = _missing()
        else {
          let quantity = 0n
          const credits: Credit[] = []
          let missing = false
          if (
            _checked_ref(
              event,
              'stat_flags.失策',
              'boolean',
              false,
              null,
              null,
              null,
            )
          ) {
            const amount = _n(1n)
            const player = _checked_ref(
              event,
              'participants.error_fielder_id',
              'string',
              true,
              null,
              null,
              null,
            )
            if (amount > 0n && typeof player !== 'string') missing = true
            else if (amount > 0n && typeof player === 'string') {
              quantity += amount
              _appendCredit(credits, player, amount)
            }
          }
          metrics['fielding_errors'] = missing
            ? _missing('MISSING_ATTRIBUTION')
            : {
                state: 'available',
                value: formatCount(quantity),
                display: formatCount(quantity),
                reason: null,
                credits,
              }
        }
      }
    } catch (error) {
      if (
        requestedMetrics === undefined ||
        !(error instanceof MissingProjectionField)
      )
        throw error
      metrics['fielding_errors'] = _missing()
    }
    try {
      if (
        requestedMetrics === undefined ||
        requestedMetrics.includes('runs_allowed')
      ) {
        if (
          !(
            _checked_ref(
              event,
              'completeness.runs_rbi',
              'string',
              false,
              null,
              null,
              ['complete', 'unavailable'],
            ) === 'complete'
          )
        )
          metrics['runs_allowed'] = _missing()
        else {
          let quantity = 0n
          const credits: Credit[] = []
          let missing = false
          const collection = _p(event, 'runner_scores')
          if (collection === null) missing = true
          else {
            if (!Array.isArray(collection) || collection.length > 4)
              throw new Error('collection型違い')
            for (const item of collection) {
              if (
                _checked_ref(
                  event,
                  'stat_flags.失点',
                  'boolean',
                  false,
                  null,
                  null,
                  null,
                ) &&
                _checked_ref(
                  item,
                  'valid_run',
                  'boolean',
                  false,
                  null,
                  null,
                  null,
                )
              ) {
                const amount = _n(1n)
                const player = _checked_ref(
                  item,
                  'responsible_pitcher_id',
                  'string',
                  false,
                  null,
                  null,
                  null,
                )
                if (amount > 0n && typeof player !== 'string') missing = true
                else if (amount > 0n && typeof player === 'string') {
                  quantity += amount
                  _appendCredit(credits, player, amount)
                }
              }
            }
          }
          metrics['runs_allowed'] = missing
            ? _missing('MISSING_ATTRIBUTION')
            : {
                state: 'available',
                value: formatCount(quantity),
                display: formatCount(quantity),
                reason: null,
                credits,
              }
        }
      }
    } catch (error) {
      if (
        requestedMetrics === undefined ||
        !(error instanceof MissingProjectionField)
      )
        throw error
      metrics['runs_allowed'] = _missing()
    }
  }
  let paRow: Record<string, unknown> | null = null
  if (
    requestedMetrics === undefined &&
    selected &&
    _checked_ref(event, 'pa.ended_here', 'boolean', false, null, null, null) &&
    _checked_ref(event, 'completeness.pa', 'string', false, null, null, [
      'complete',
      'unavailable',
    ]) === 'complete'
  ) {
    paRow = {
      pa_id: _checked_ref(event, 'pa.pa_id', 'string', true, null, null, null),
      batter_id: _checked_ref(
        event,
        'participants.credited_batter_id',
        'string',
        true,
        null,
        null,
        null,
      ),
      ordinal_for_batter: _checked_ref(
        event,
        'pa.ordinal_for_batter',
        'string',
        true,
        null,
        null,
        null,
      ),
      inning: _checked_ref(
        event,
        'before.inning',
        'string',
        false,
        null,
        null,
        null,
      ),
      half: _checked_ref(
        event,
        'before.half',
        'string',
        false,
        null,
        null,
        null,
      ),
      result_display: _checked_ref(
        event,
        'pa.result_display',
        'string',
        true,
        null,
        null,
        null,
      ),
      counts_as_ab: _checked_ref(
        event,
        'stat_flags.打数',
        'boolean',
        false,
        null,
        null,
        null,
      ),
      hit_kind: _checked_ref(
        event,
        'pa.hit_kind',
        'string',
        false,
        null,
        null,
        ['none', 'single', 'double', 'triple', 'home_run'],
      ),
      reached_by: _checked_ref(
        event,
        'pa.reached_by',
        'string',
        false,
        null,
        null,
        null,
      ),
    }
    paRow['rbi'] = metrics['rbi']!.value
    paRow['rbi_state'] = metrics['rbi']!.state
  }
  return {
    metrics,
    pa_row: paRow,
    source_event_id: _p(event, 'source.source_event_id'),
    selected,
    decisions: {
      D02: {
        decision_id: 'D02',
        decision_state: 'adopted',
        choice: 'A',
        implementation_state: 'available',
      },
      D03: {
        decision_id: 'D03',
        decision_state: 'adopted',
        choice: 'A',
        implementation_state: 'pending',
        source_state: 'not_evaluated',
        value: null,
      },
      D04: {
        decision_id: 'D04',
        decision_state: 'adopted',
        choice: 'A',
        implementation_state: 'pending',
        source_state: 'not_evaluated',
        value: null,
      },
      D05: {
        decision_id: 'D05',
        decision_state: 'adopted',
        choice: 'A',
        implementation_state: 'available',
      },
    } as const,
  }
}
type RateMetric =
  | string
  | null
  | {
      state: string
      value: string | null
      display: string | null
      reason: string | null
    }
type RatioPair = readonly [bigint, bigint] | null
type RatioDisplay = {
  scale: number
  rounding: string
  leadingZero: boolean
  zeroDivisionGlyph: string
  denominators: readonly { component: string; prefix: string; suffix: string }[]
}
function _rateInputs(
  metrics: unknown,
  names: readonly string[],
): Record<string, bigint | null> {
  if (typeof metrics !== 'object' || metrics === null || Array.isArray(metrics))
    throw new Error('派生率の閉型が必要です')
  const source = metrics as Record<string, unknown>
  if (
    Object.keys(source).length !== names.length ||
    Object.keys(source).some((k) => !names.includes(k))
  )
    throw new Error('派生率の十分統計は閉26項目が必要です')
  const values: Record<string, bigint | null> = {}
  for (const key of names) {
    let row = source[key]
    if (typeof row === 'object' && row !== null && !Array.isArray(row)) {
      const metric = row as Record<string, unknown>
      if (
        Object.keys(metric).length !== 4 ||
        Object.keys(metric).some(
          (k) => !['state', 'value', 'display', 'reason'].includes(k),
        )
      )
        throw new Error('十分統計の閉型が不正です')
      if (metric.state === 'source_unavailable') {
        if (
          metric.value !== null ||
          metric.display !== null ||
          ![
            'MISSING_OBSERVATION',
            'MISSING_ATTRIBUTION',
            'UNSUPPORTED_SOURCE_VARIANT',
          ].includes(metric.reason as string)
        )
          throw new Error('不足観測の型が不正です')
        values[key] = null
        continue
      }
      if (
        metric.state !== 'available' ||
        metric.value === null ||
        metric.reason !== null ||
        metric.display !== metric.value
      )
        throw new Error('十分統計の状態が不正です')
      row = metric.value
    }
    if (row === null) values[key] = null
    else if (typeof row === 'string' && /^(0|[1-9][0-9]*)(?![\s\S])/.test(row))
      values[key] = BigInt(row)
    else throw new Error('十分統計は正準整数文字列です')
  }
  return values
}
function _rateAdd(...values: Array<bigint | null | undefined>): bigint | null {
  let result = 0n
  for (const value of values) {
    if (value === null || value === undefined) return null
    result += value
  }
  return result
}
function _ratio(
  n: bigint | null | undefined,
  d: bigint | null | undefined,
): RatioPair {
  return n === null || n === undefined || d === null || d === undefined
    ? null
    : [n, d]
}
function _ratioAdd(...values: RatioPair[]): RatioPair {
  let n = 0n,
    d = 1n
  for (const value of values) {
    if (value === null || value[1] === 0n) return null
    n = n * value[1] + value[0] * d
    d *= value[1]
  }
  return [n, d]
}
function _rateReason(
  metrics: Record<string, RateMetric>,
  dependencies: readonly string[],
): string {
  for (const key of dependencies) {
    const row = metrics[key]
    if (
      typeof row === 'object' &&
      row !== null &&
      row.state === 'source_unavailable'
    )
      return row.reason!
  }
  return 'MISSING_OBSERVATION'
}
function _rateResult(
  value: RatioPair,
  components: Record<string, RatioPair>,
  display: RatioDisplay,
  reason = 'MISSING_OBSERVATION',
) {
  const expected = display.denominators.map((x) => x.component)
  if (
    Object.keys(components).length !== expected.length ||
    Object.keys(components).some((k) => !expected.includes(k))
  )
    throw new Error('比componentの閉集合が不正です')
  for (const pair of [value, ...Object.values(components)])
    if (
      pair !== null &&
      (!Array.isArray(pair) ||
        pair.length !== 2 ||
        pair.some((x) => typeof x !== 'bigint' || x < 0n))
    )
      throw new Error('比の整数型が不正です')
  if (Object.values(components).some((pair) => pair === null) && value !== null)
    throw new Error('不足観測に比を補完できません')
  if (Object.values(components).some((pair) => pair === null))
    return {
      state: 'source_unavailable',
      value_state: 'not_evaluated',
      exact_ratio: null,
      components: null,
      formatted_value: null,
      display: null,
      reason,
    }
  const raw: Record<string, { numerator: string; denominator: string }> = {}
  for (const [key, pair] of Object.entries(components)) {
    if (pair === null) throw new Error('比が不足しています')
    raw[key] = {
      numerator: pair[0].toString(),
      denominator: pair[1].toString(),
    }
  }
  let exact: { numerator: string; denominator: string } | null = null,
    formatted: string,
    state: string
  if (
    Object.values(components).some((pair) => pair !== null && pair[1] === 0n)
  ) {
    formatted = display.zeroDivisionGlyph
    state = 'undefined_zero_denominator'
  } else {
    if (value === null) throw new Error('定義済み比の値が不足しています')
    let [n, d] = value,
      a = n,
      b = d
    if (d === 0n) throw new Error('定義済み比の分母は正です')
    while (b !== 0n) {
      const r = a % b
      a = b
      b = r
    }
    n /= a
    d /= a
    exact = { numerator: n.toString(), denominator: d.toString() }
    const power = 10n ** BigInt(display.scale),
      q = (n * power) / d,
      r = (n * power) % d
    const rounded = q + (2n * r >= d ? 1n : 0n)
    formatted =
      (rounded / power).toString() +
      '.' +
      (rounded % power).toString().padStart(display.scale, '0')
    state = 'defined'
  }
  const labels = display.denominators.map(
    (label) => label.prefix + raw[label.component]!.denominator + label.suffix,
  )
  return {
    state: 'available',
    value_state: state,
    exact_ratio: exact,
    components: raw,
    formatted_value: formatted,
    display: formatted + '(' + labels.join('・') + ')',
    reason: null,
  }
}

const GAME_TYPE_SCOPES: Record<string, readonly string[]> = {
  official: ['game_official', 'game_semi_official'],
  practice: ['game_open', 'game_intrasquad', 'game_other'],
  all: [
    'game_official',
    'game_semi_official',
    'game_open',
    'game_intrasquad',
    'game_other',
  ],
}
export function selectGameTypeKeys(
  namedCategory: unknown = 'all',
  rawKeys?: unknown,
): string[] {
  if (
    typeof namedCategory !== 'string' ||
    !Object.hasOwn(GAME_TYPE_SCOPES, namedCategory)
  )
    throw new Error('未知のnamed categoryです')
  const keys = GAME_TYPE_SCOPES[namedCategory]!
  if (
    rawKeys !== undefined &&
    (!Array.isArray(rawKeys) ||
      rawKeys.length !== keys.length ||
      rawKeys.some((x, i) => typeof x !== 'string' || x !== keys[i]))
  )
    throw new Error('named/raw集合が不一致です')
  return [...keys]
}
export function decisionMetadata() {
  return {
    D02: {
      decision_id: 'D02',
      decision_state: 'adopted',
      choice: 'A',
      implementation_state: 'available',
    },
    D03: {
      decision_id: 'D03',
      decision_state: 'adopted',
      choice: 'A',
      implementation_state: 'pending',
      source_state: 'not_evaluated',
      value: null,
    },
    D04: {
      decision_id: 'D04',
      decision_state: 'adopted',
      choice: 'A',
      implementation_state: 'pending',
      source_state: 'not_evaluated',
      value: null,
    },
    D05: {
      decision_id: 'D05',
      decision_state: 'adopted',
      choice: 'A',
      implementation_state: 'available',
    },
  } as const
}
export function deriveRates(metrics: Record<string, RateMetric>) {
  const values = _rateInputs(metrics, [
    'pitch_count',
    'pa',
    'ab',
    'h',
    'hr',
    'bb',
    'hbp',
    'k',
    'sh',
    'sf',
    'catcher_interference_reached',
    'runner_interference_reached',
    'doubles',
    'triples',
    'total_bases',
    'runs',
    'rbi',
    'stolen_bases',
    'pitching_outs',
    'pitcher_k',
    'pitcher_bb',
    'pitcher_hbp',
    'hits_allowed',
    'home_runs_allowed',
    'fielding_errors',
    'runs_allowed',
  ])
  const results: Record<string, ReturnType<typeof _rateResult>> = {}
  const parts0: Record<string, RatioPair> = {
    obp: _ratio(
      _rateAdd(values['h'], values['bb'], values['hbp']),
      _rateAdd(values['ab'], values['bb'], values['hbp'], values['sf']),
    ),
    slg: _ratio(values['total_bases'], values['ab']),
  }
  results['ops'] = _rateResult(
    _ratioAdd(parts0['obp']!, parts0['slg']!),
    parts0,
    {
      scale: 3,
      rounding: 'half-up',
      leadingZero: true,
      zeroDivisionGlyph: '−',
      denominators: [
        { component: 'obp', prefix: '出塁率分母', suffix: '打席' },
        { component: 'slg', prefix: '長打率分母', suffix: '打数' },
      ],
    },
    _rateReason(metrics, ['h', 'bb', 'hbp', 'ab', 'sf', 'total_bases']),
  )
  return results
}
