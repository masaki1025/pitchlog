/** 自動生成。単一遷移だけを計算し、認可/全game集計を行わない。 */
export const SOURCE_MODEL_HASH =
  'sha256:db0c52f2df92ddd76a9681a940e1bae83f29fb7ff7f9e988b23a76cd5b52b40d'
if (
  (globalThis as { __PITCHLOG_GENERATED_WRAPPER__?: boolean })
    .__PITCHLOG_GENERATED_WRAPPER__ !== true
)
  throw new Error('登録wrapperが必要です')
// generated=sha256:db0c52f2df92ddd76a9681a940e1bae83f29fb7ff7f9e988b23a76cd5b52b40d
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

function _p(owner: unknown, path: string): unknown {
  for (const part of path.split('.')) {
    if (owner === null) return null
    if (
      typeof owner !== 'object' ||
      Array.isArray(owner) ||
      !Object.hasOwn(owner, part)
    )
      throw new Error('閉入力のfield不足')
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
export function eventFacts(event: unknown) {
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
  _check(_p(event, 'source.source_event_id'), 'string', false, null, null, null)
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
  _check(_p(event, 'completeness.participants'), 'string', false, null, null, [
    'complete',
    'unavailable',
  ])
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
    metrics[name] = _zero()
  const selected = _p(event, 'source.lifecycle') === 'effective'
  if (selected) {
    {
      if (!(_p(event, 'completeness.participants') === 'complete'))
        metrics['pitch_count'] = _missing()
      else {
        let quantity = 0n
        const credits: Credit[] = []
        let missing = false
        if (
          _p(event, 'event_kind') === 'pitch' &&
          _p(event, 'stat_flags.投球数')
        ) {
          const amount = _n(1n)
          const player = _p(event, 'participants.actual_pitcher_id')
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
    {
      if (!(
        _p(event, 'completeness.pa') === 'complete' &&
        _p(event, 'completeness.participants') === 'complete'
      ))
        metrics['pa'] = _missing()
      else {
        let quantity = 0n
        const credits: Credit[] = []
        let missing = false
        if (_p(event, 'pa.ended_here') && _p(event, 'stat_flags.打席')) {
          const amount = _n(1n)
          const player = _p(event, 'participants.credited_batter_id')
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
    {
      if (!(
        _p(event, 'completeness.pa') === 'complete' &&
        _p(event, 'completeness.participants') === 'complete'
      ))
        metrics['ab'] = _missing()
      else {
        let quantity = 0n
        const credits: Credit[] = []
        let missing = false
        if (_p(event, 'pa.ended_here') && _p(event, 'stat_flags.打数')) {
          const amount = _n(1n)
          const player = _p(event, 'participants.credited_batter_id')
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
    {
      if (!(
        _p(event, 'completeness.pa') === 'complete' &&
        _p(event, 'completeness.participants') === 'complete'
      ))
        metrics['h'] = _missing()
      else {
        let quantity = 0n
        const credits: Credit[] = []
        let missing = false
        if (_p(event, 'pa.ended_here') && _p(event, 'stat_flags.安打')) {
          const amount = _n(1n)
          const player = _p(event, 'participants.credited_batter_id')
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
    {
      if (!(
        _p(event, 'completeness.pa') === 'complete' &&
        _p(event, 'completeness.participants') === 'complete'
      ))
        metrics['hr'] = _missing()
      else {
        let quantity = 0n
        const credits: Credit[] = []
        let missing = false
        if (_p(event, 'pa.ended_here') && _p(event, 'stat_flags.本塁打')) {
          const amount = _n(1n)
          const player = _p(event, 'participants.credited_batter_id')
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
    {
      if (!(
        _p(event, 'completeness.pa') === 'complete' &&
        _p(event, 'completeness.participants') === 'complete'
      ))
        metrics['bb'] = _missing()
      else {
        let quantity = 0n
        const credits: Credit[] = []
        let missing = false
        if (_p(event, 'pa.ended_here') && _p(event, 'stat_flags.四球')) {
          const amount = _n(1n)
          const player = _p(event, 'participants.credited_batter_id')
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
    {
      if (!(
        _p(event, 'completeness.pa') === 'complete' &&
        _p(event, 'completeness.participants') === 'complete'
      ))
        metrics['hbp'] = _missing()
      else {
        let quantity = 0n
        const credits: Credit[] = []
        let missing = false
        if (_p(event, 'pa.ended_here') && _p(event, 'stat_flags.死球')) {
          const amount = _n(1n)
          const player = _p(event, 'participants.credited_batter_id')
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
    {
      if (!(
        _p(event, 'completeness.pa') === 'complete' &&
        _p(event, 'completeness.participants') === 'complete'
      ))
        metrics['k'] = _missing()
      else {
        let quantity = 0n
        const credits: Credit[] = []
        let missing = false
        if (_p(event, 'pa.ended_here') && _p(event, 'stat_flags.三振')) {
          const amount = _n(1n)
          const player = _p(event, 'participants.credited_batter_id')
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
    {
      if (!(
        _p(event, 'completeness.pa') === 'complete' &&
        _p(event, 'completeness.participants') === 'complete'
      ))
        metrics['sh'] = _missing()
      else {
        let quantity = 0n
        const credits: Credit[] = []
        let missing = false
        if (_p(event, 'pa.ended_here') && _p(event, 'stat_flags.犠打')) {
          const amount = _n(1n)
          const player = _p(event, 'participants.credited_batter_id')
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
    {
      if (!(
        _p(event, 'completeness.pa') === 'complete' &&
        _p(event, 'completeness.participants') === 'complete'
      ))
        metrics['sf'] = _missing()
      else {
        let quantity = 0n
        const credits: Credit[] = []
        let missing = false
        if (_p(event, 'pa.ended_here') && _p(event, 'stat_flags.犠飛')) {
          const amount = _n(1n)
          const player = _p(event, 'participants.credited_batter_id')
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
    {
      if (!(
        _p(event, 'completeness.pa') === 'complete' &&
        _p(event, 'completeness.participants') === 'complete'
      ))
        metrics['catcher_interference_reached'] = _missing()
      else {
        let quantity = 0n
        const credits: Credit[] = []
        let missing = false
        if (
          _p(event, 'pa.ended_here') &&
          _p(event, 'stat_flags.打撃妨害出塁')
        ) {
          const amount = _n(1n)
          const player = _p(event, 'participants.credited_batter_id')
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
    {
      if (!(
        _p(event, 'completeness.pa') === 'complete' &&
        _p(event, 'completeness.participants') === 'complete'
      ))
        metrics['runner_interference_reached'] = _missing()
      else {
        let quantity = 0n
        const credits: Credit[] = []
        let missing = false
        if (
          _p(event, 'pa.ended_here') &&
          _p(event, 'stat_flags.走塁妨害出塁')
        ) {
          const amount = _n(1n)
          const player = _p(event, 'participants.credited_batter_id')
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
    {
      if (!(
        _p(event, 'completeness.pa') === 'complete' &&
        _p(event, 'completeness.participants') === 'complete'
      ))
        metrics['doubles'] = _missing()
      else {
        let quantity = 0n
        const credits: Credit[] = []
        let missing = false
        if (
          _p(event, 'pa.ended_here') &&
          _p(event, 'stat_flags.安打') &&
          _p(event, 'pa.hit_kind') === 'double'
        ) {
          const amount = _n(1n)
          const player = _p(event, 'participants.credited_batter_id')
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
    {
      if (!(
        _p(event, 'completeness.pa') === 'complete' &&
        _p(event, 'completeness.participants') === 'complete'
      ))
        metrics['triples'] = _missing()
      else {
        let quantity = 0n
        const credits: Credit[] = []
        let missing = false
        if (
          _p(event, 'pa.ended_here') &&
          _p(event, 'stat_flags.安打') &&
          _p(event, 'pa.hit_kind') === 'triple'
        ) {
          const amount = _n(1n)
          const player = _p(event, 'participants.credited_batter_id')
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
    {
      if (!(
        _p(event, 'completeness.pa') === 'complete' &&
        _p(event, 'completeness.participants') === 'complete'
      ))
        metrics['total_bases'] = _missing()
      else {
        let quantity = 0n
        const credits: Credit[] = []
        let missing = false
        if (_p(event, 'pa.ended_here') && _p(event, 'stat_flags.塁打')) {
          const amount = _n(
            _lookup(
              { none: 0n, single: 1n, double: 2n, triple: 3n, home_run: 4n },
              _p(event, 'pa.hit_kind'),
            ),
          )
          const player = _p(event, 'participants.credited_batter_id')
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
    {
      if (!(_p(event, 'completeness.runs_rbi') === 'complete'))
        metrics['runs'] = _missing()
      else {
        let quantity = 0n
        const credits: Credit[] = []
        let missing = false
        const collection = _p(event, 'runner_scores')
        if (collection === null) missing = true
        else {
          if (!Array.isArray(collection)) throw new Error('collection型違い')
          for (const item of collection) {
            if (_p(event, 'stat_flags.得点') && _p(item, 'valid_run')) {
              const amount = _n(1n)
              const player = _p(item, 'runner_id')
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
    {
      if (!(_p(event, 'completeness.runs_rbi') === 'complete'))
        metrics['rbi'] = _missing()
      else {
        let quantity = 0n
        const credits: Credit[] = []
        let missing = false
        const collection = _p(event, 'runner_scores')
        if (collection === null) missing = true
        else {
          if (!Array.isArray(collection)) throw new Error('collection型違い')
          for (const item of collection) {
            if (
              _p(event, 'stat_flags.打点') &&
              _p(item, 'valid_run') &&
              _p(item, 'rbi_credited')
            ) {
              const amount = _n(1n)
              const player = _p(item, 'rbi_batter_id')
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
    {
      if (!(_p(event, 'completeness.steals') === 'complete'))
        metrics['stolen_bases'] = _missing()
      else {
        let quantity = 0n
        const credits: Credit[] = []
        let missing = false
        const collection = _p(event, 'steal_attempts')
        if (collection === null) missing = true
        else {
          if (!Array.isArray(collection)) throw new Error('collection型違い')
          for (const item of collection) {
            if (_p(item, 'attempted') && _p(item, 'successful')) {
              const amount = _n(1n)
              const player = _p(item, 'runner_id')
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
    {
      if (!(
        _p(event, 'completeness.outs') === 'complete' &&
        _p(event, 'completeness.participants') === 'complete'
      ))
        metrics['pitching_outs'] = _missing()
      else {
        let quantity = 0n
        const credits: Credit[] = []
        let missing = false
        if (_p(event, 'stat_flags.投球回算入アウト')) {
          const amount = _n(_n(_p(event, 'out_effect.effective_count')))
          const player = _p(event, 'participants.outs_pitcher_id')
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
    {
      if (!(_p(event, 'completeness.participants') === 'complete'))
        metrics['pitcher_k'] = _missing()
      else {
        let quantity = 0n
        const credits: Credit[] = []
        let missing = false
        if (_p(event, 'stat_flags.奪三振')) {
          const amount = _n(1n)
          const player = _p(event, 'participants.strikeout_pitcher_id')
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
    {
      if (!(_p(event, 'completeness.participants') === 'complete'))
        metrics['pitcher_bb'] = _missing()
      else {
        let quantity = 0n
        const credits: Credit[] = []
        let missing = false
        if (_p(event, 'stat_flags.与四球')) {
          const amount = _n(1n)
          const player = _p(event, 'participants.walk_pitcher_id')
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
    {
      if (!(_p(event, 'completeness.participants') === 'complete'))
        metrics['pitcher_hbp'] = _missing()
      else {
        let quantity = 0n
        const credits: Credit[] = []
        let missing = false
        if (_p(event, 'stat_flags.与死球')) {
          const amount = _n(1n)
          const player = _p(event, 'participants.hbp_pitcher_id')
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
    {
      if (!(_p(event, 'completeness.participants') === 'complete'))
        metrics['hits_allowed'] = _missing()
      else {
        let quantity = 0n
        const credits: Credit[] = []
        let missing = false
        if (_p(event, 'stat_flags.被安打')) {
          const amount = _n(1n)
          const player = _p(event, 'participants.hit_pitcher_id')
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
    {
      if (!(_p(event, 'completeness.participants') === 'complete'))
        metrics['home_runs_allowed'] = _missing()
      else {
        let quantity = 0n
        const credits: Credit[] = []
        let missing = false
        if (_p(event, 'stat_flags.被本塁打')) {
          const amount = _n(1n)
          const player = _p(event, 'participants.home_run_pitcher_id')
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
    {
      if (!(_p(event, 'completeness.participants') === 'complete'))
        metrics['fielding_errors'] = _missing()
      else {
        let quantity = 0n
        const credits: Credit[] = []
        let missing = false
        if (_p(event, 'stat_flags.失策')) {
          const amount = _n(1n)
          const player = _p(event, 'participants.error_fielder_id')
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
    {
      if (!(_p(event, 'completeness.runs_rbi') === 'complete'))
        metrics['runs_allowed'] = _missing()
      else {
        let quantity = 0n
        const credits: Credit[] = []
        let missing = false
        const collection = _p(event, 'runner_scores')
        if (collection === null) missing = true
        else {
          if (!Array.isArray(collection)) throw new Error('collection型違い')
          for (const item of collection) {
            if (_p(event, 'stat_flags.失点') && _p(item, 'valid_run')) {
              const amount = _n(1n)
              const player = _p(item, 'responsible_pitcher_id')
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
  }
  let paRow: Record<string, unknown> | null = null
  if (
    selected &&
    _p(event, 'pa.ended_here') &&
    _p(event, 'completeness.pa') === 'complete'
  ) {
    paRow = {
      pa_id: _p(event, 'pa.pa_id'),
      batter_id: _p(event, 'participants.credited_batter_id'),
      ordinal_for_batter: _p(event, 'pa.ordinal_for_batter'),
      inning: _p(event, 'before.inning'),
      half: _p(event, 'before.half'),
      result_display: _p(event, 'pa.result_display'),
      counts_as_ab: _p(event, 'stat_flags.打数'),
      hit_kind: _p(event, 'pa.hit_kind'),
      reached_by: _p(event, 'pa.reached_by'),
    }
    paRow['rbi'] = metrics['rbi']!.value
    paRow['rbi_state'] = metrics['rbi']!.state
  }
  return {
    metrics,
    pa_row: paRow,
    source_event_id: _p(event, 'source.source_event_id'),
    selected,
    pending: {
      named_category: {
        state: 'decision_pending',
        decision_id: 'D02',
        value: null,
      },
      appearances: {
        state: 'decision_pending',
        decision_id: 'D03',
        value: null,
      },
      batters_faced: {
        state: 'decision_pending',
        decision_id: 'D04',
        value: null,
      },
      ops: { state: 'decision_pending', decision_id: 'D05', value: null },
    } as const,
  }
}
