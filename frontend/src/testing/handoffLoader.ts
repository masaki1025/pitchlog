import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const HANDOFF_PATH =
  'contracts/state-transition/appendix_e_consumer_handoff_v1.json'
const DESCRIPTOR_PATH =
  'contracts/state-transition/input_axes_descriptor_v1.json'
const DESCRIPTOR_ID = 'pitchlog.input-axes'
const DESCRIPTOR_VERSION = 'input_axes_descriptor_v1'
const DESCRIPTOR_SCHEMA_PATHS = [
  'contracts/state-transition/state_transition_contract_schema_v1.json',
  'contracts/state-transition/game_end_contract_schema_v1.json',
] as const
const DEPENDENCY_OID = 'b8fd5fe73e85ae80b3aa82b28bef7f2911f29b12'
const CONTRACTS = {
  'state-transition': {
    path: 'contracts/state-transition/state_transition_contract_v1.json',
    version: 'state_transition_contract_v1',
    expectedPointer: '/expected',
    caseKeys: [
      'caseId',
      'rowRef',
      'inputCoordinate',
      'historyInput',
      'expected',
      'raw',
      'normalizationRuleId',
      'normalized',
    ],
    contractKeys: [
      'schemaVersion',
      'version',
      'calculation',
      'inputAxesDescriptor',
      'provenance',
      'matrixRows',
      'operationRows',
      'undoRows',
      'mustOperationCoverage',
      'requiredSet',
      'cases',
    ],
  },
  'game-end': {
    path: 'contracts/state-transition/game_end_contract_v1.json',
    version: 'game_end_contract_v1',
    expectedPointer: '/decision',
    caseKeys: [
      'branchId',
      'caseId',
      'decision',
      'inputCoordinate',
      'normalizationRuleId',
      'normalized',
      'raw',
      'rowRef',
      'derivedSourceInput',
    ],
    contractKeys: [
      'schemaVersion',
      'version',
      'calculation',
      'inputAxesDescriptor',
      'provenance',
      'decisionRows',
      'requiredSet',
      'cases',
      'validationErrors',
    ],
  },
} as const
const DEPENDENCIES = {
  // 依存元の commit OID は出自として固定し、SHA-256 は現行の実資産を照合する。
  'backend/domain/history-depth.json': {
    taskId: 'TSK-235',
    commitOid: DEPENDENCY_OID,
    versionKey: 'version',
    digest:
      'sha256:933e41e9a717fe25f52575d7b34ca077904d4592f51173b56832c36963a31e97',
  },
  'backend/domain/check-sets.json': {
    taskId: 'TSK-235',
    commitOid: DEPENDENCY_OID,
    versionKey: 'schemaVersion',
    digest:
      'sha256:c6bf9beeb86325c759f56abb50af060bf62b48323e50f9c1c1cfe5704cc7c18b',
  },
  'backend/src/pitchlog/domaincheck/runners/vector_bridge.py': {
    taskId: 'TSK-455',
    commitOid: 'ee021d87e59f26d3afe4b01c7ea695866797f26f',
    versionKey: null,
    digest:
      'sha256:ba9263cdfb39118e95ec7b9df3ab2656db2ace990206c5bf3967fa0067fbbfff',
  },
  'frontend/src/testing/vectorRunner.ts': {
    taskId: 'TSK-455',
    commitOid: 'f8df3adabb2fe1c26b437149b0ec59c84c7f3d2e',
    versionKey: null,
    digest:
      'sha256:b17eb6c8bc75f1677e038769e2d94b1280ee408fe16a93aa12dcaeb9abef6d06',
  },
} as const
const HANDOFF_KEYS = [
  'handoffVersion',
  'calculationIds',
  'claimBoundary',
  'consumerBindings',
  'artifacts',
  'dependencies',
  'receiverDoD',
  'fr040Declaration',
  'descriptorParity',
  'consumptionVerification',
  'stage2EntryGate',
  'receiverTaskId',
]
const BINDING_KEYS = [
  'calculationId',
  'vectorId',
  'contractPath',
  'version',
  'schemaVersion',
  'caseSchemaRef',
  'caseFieldMapping',
  'normalizationComparison',
  'outputComparison',
  'dPlusOnePolicy',
  'executionPaths',
]
const EXECUTION_PATH_KEYS = [
  'runner',
  'runnerRevision',
  'normalizerId',
  'entrypointId',
  'directTargetId',
  'resolutionStage',
]
const PARITY_KEYS = [
  'descriptorPath',
  'descriptorId',
  'projectionRulesPointer',
  'designPath',
  'designSection',
  'requirement',
  'verificationStage',
]
const DESCRIPTOR_KEYS = [
  'descriptorId',
  'version',
  'digest',
  'digestSpec',
  'stage2ExternalConstraints',
  'inputCoordinateCoverage',
  'freezeBaseline',
  'stateTransitionAxes',
  'gameEndAxes',
  'gameEndCombinationRules',
  'nonCoverageFields',
  'projectionRules',
]
const STAGE2_GATE_KEYS = [
  'topLevelLoad',
  'versionCheck',
  'bindingConstruction',
  'allCasesConsumption',
  'dPlusOnePrerequisite',
]

type RecordValue = Record<string, unknown>
type CalculationId = keyof typeof CONTRACTS

export class HandoffLoadError extends Error {
  readonly code: string

  constructor(code: string, detail: string) {
    super(`${code}: ${detail}`)
    this.name = 'HandoffLoadError'
    this.code = code
  }
}

export type LoadedHandoffCases = Readonly<{
  calculationId: CalculationId
  cases: readonly Readonly<RecordValue>[]
  sourceCases?: readonly Readonly<RecordValue>[]
}>

export type LoadedHandoff = Readonly<{
  byCalculation: Readonly<Record<CalculationId, LoadedHandoffCases>>
  descriptor: Readonly<RecordValue>
}>

function record(value: unknown, label: string): RecordValue {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new HandoffLoadError('HANDOFF_SHAPE', label)
  }
  return value as RecordValue
}

function keys(
  value: unknown,
  expected: readonly string[],
  label: string,
): RecordValue {
  const item = record(value, label)
  const actual = Object.keys(item)
  if (
    actual.length !== expected.length ||
    actual.some((key) => !expected.includes(key))
  ) {
    throw new HandoffLoadError('UNKNOWN_FIELD', label)
  }
  return item
}

function array(value: unknown, label: string): unknown[] {
  if (!Array.isArray(value)) throw new HandoffLoadError('HANDOFF_SHAPE', label)
  return value as unknown[]
}

function same(
  actual: unknown,
  expected: unknown,
  code: string,
  label: string,
): void {
  if (typeof actual !== typeof expected || actual !== expected) {
    throw new HandoffLoadError(code, label)
  }
}

function sameArray(
  actual: unknown,
  expected: readonly string[],
  label: string,
): void {
  if (
    !Array.isArray(actual) ||
    actual.length !== expected.length ||
    actual.some((item, index) => item !== expected[index])
  ) {
    throw new HandoffLoadError('VERSION_MISMATCH', label)
  }
}

function parse(data: Uint8Array, label: string): unknown {
  const source = new TextDecoder('utf-8', { fatal: true }).decode(data)
  // JSON.parse より前に数値 token を検査し、2^53 超の丸めを防ぐ。
  let inString = false
  let escaped = false
  const objects: (Set<string> | null)[] = []
  let stringStart = -1
  for (let index = 0; index < source.length; index += 1) {
    const char = source[index]
    if (inString) {
      if (escaped) escaped = false
      else if (char === '\\') escaped = true
      else if (char === '"') {
        inString = false
        let next = index + 1
        while (/\s/.test(source[next] ?? '')) next += 1
        const objectKeys = objects.at(-1)
        if (source[next] === ':' && objectKeys) {
          let key: string
          try {
            key = JSON.parse(source.slice(stringStart, index + 1)) as string
          } catch {
            throw new HandoffLoadError('HANDOFF_SHAPE', label)
          }
          if (objectKeys.has(key)) {
            throw new HandoffLoadError('UNKNOWN_FIELD', `${label}: ${key}`)
          }
          objectKeys.add(key)
        }
      }
      continue
    }
    if (char === '"') {
      inString = true
      stringStart = index
      continue
    }
    if (char === '{') objects.push(new Set<string>())
    else if (char === '[') objects.push(null)
    else if (char === '}' || char === ']') objects.pop()
    if (char === '-' || (char !== undefined && /[0-9]/.test(char))) {
      const token =
        /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/.exec(
          source.slice(index),
        )?.[0]
      if (!token) throw new HandoffLoadError('HANDOFF_SHAPE', label)
      if (
        token === '-0' ||
        /[.eE]/.test(token) ||
        BigInt(token) > 9007199254740991n ||
        BigInt(token) < -9007199254740991n
      ) {
        throw new HandoffLoadError('UNSAFE_INTEGER', label)
      }
      index += token.length - 1
    }
  }
  try {
    return JSON.parse(source) as unknown
  } catch {
    throw new HandoffLoadError('HANDOFF_SHAPE', label)
  }
}

function mapping(
  binding: RecordValue,
  expectedPointer: string,
): Record<string, string> {
  const config = keys(
    binding.caseFieldMapping,
    ['id', 'input', 'expected', 'tags'],
    'caseFieldMapping',
  )
  const input = keys(config.input, ['raw', 'normalized'], 'input')
  const pairs: Record<string, unknown> = {
    caseId: config.id,
    raw: input.raw,
    normalized: input.normalized,
    expected: config.expected,
  }
  const pointers: Record<string, string> = {}
  for (const [target, pair] of Object.entries(pairs)) {
    const item = keys(pair, ['contractPointer', 'runnerPointer'], target)
    const source = target === 'expected' ? expectedPointer : `/${target}`
    same(item.contractPointer, source, 'MAPPING', target)
    same(item.runnerPointer, `/${target}`, 'MAPPING', target)
    pointers[target] = source.slice(1)
  }
  const tags = keys(
    config.tags,
    ['contractPointer', 'runnerPointer', 'availability'],
    'tags',
  )
  if (
    tags.contractPointer !== null ||
    tags.runnerPointer !== '/tags' ||
    tags.availability !== 'absent'
  ) {
    throw new HandoffLoadError('MAPPING', 'tags')
  }
  return pointers
}

function sha(data: Uint8Array): string {
  return `sha256:${createHash('sha256').update(data).digest('hex')}`
}

export function loadHandoff(
  root: string,
  readAsset: (path: string) => Uint8Array = (path) =>
    readFileSync(resolve(root, path)),
): LoadedHandoff {
  // 読むパスはここで宣言した固定集合だけとし、契約中の path を読み込みに使わない。
  function readBytes(path: string): Uint8Array {
    let raw: Uint8Array
    try {
      raw = readAsset(path)
    } catch {
      throw new HandoffLoadError('HANDOFF_SHAPE', path)
    }
    return raw
  }

  function read(path: string): [Uint8Array, RecordValue] {
    const raw = readBytes(path)
    return [raw, record(parse(raw, path), path)]
  }

  const [, handoff] = read(HANDOFF_PATH)
  keys(handoff, HANDOFF_KEYS, 'handoff')
  keys(handoff.claimBoundary, ['guaranteed', 'notGuaranteed'], 'claimBoundary')
  keys(
    handoff.fr040Declaration,
    ['content', 'basis', 'recordStage', 'recordTarget'],
    'fr040Declaration',
  )
  same(
    handoff.handoffVersion,
    'appendix_e_consumer_handoff_v1',
    'VERSION_MISMATCH',
    'handoffVersion',
  )
  sameArray(handoff.calculationIds, Object.keys(CONTRACTS), 'calculationIds')
  keys(handoff.stage2EntryGate, STAGE2_GATE_KEYS, 'stage2EntryGate')
  const parity = keys(handoff.descriptorParity, PARITY_KEYS, 'descriptorParity')
  same(parity.descriptorPath, DESCRIPTOR_PATH, 'DESCRIPTOR_MISMATCH', 'path')
  same(parity.descriptorId, DESCRIPTOR_ID, 'DESCRIPTOR_MISMATCH', 'id')
  const [descriptorRaw, descriptor] = read(DESCRIPTOR_PATH)
  keys(descriptor, DESCRIPTOR_KEYS, 'descriptor')
  // 既受理の契約schemaの閉じたconst宣言を期待値とし、実descriptorから導出しない。
  let descriptorDigest: string | undefined
  const descriptorFields = ['descriptorId', 'version', 'digest'] as const
  for (const path of DESCRIPTOR_SCHEMA_PATHS) {
    const [, schema] = read(path)
    const definitions = record(schema.$defs, `${path}/$defs`)
    const binding = keys(
      definitions.inputAxesDescriptorBinding,
      ['type', 'required', 'additionalProperties', 'properties'],
      `${path}/inputAxesDescriptorBinding`,
    )
    same(binding.type, 'object', 'DESCRIPTOR_MISMATCH', 'binding type')
    same(
      binding.additionalProperties,
      false,
      'DESCRIPTOR_MISMATCH',
      'binding closure',
    )
    sameArray(binding.required, descriptorFields, 'binding required')
    const properties = keys(
      binding.properties,
      descriptorFields,
      'binding properties',
    )
    const constants: Record<string, string> = {}
    for (const field of descriptorFields) {
      const declaration = keys(properties[field], ['const'], `binding ${field}`)
      if (typeof declaration.const !== 'string') {
        throw new HandoffLoadError('DESCRIPTOR_MISMATCH', `binding ${field}`)
      }
      constants[field] = declaration.const
    }
    same(
      constants.descriptorId,
      DESCRIPTOR_ID,
      'DESCRIPTOR_MISMATCH',
      'binding id',
    )
    same(
      constants.version,
      DESCRIPTOR_VERSION,
      'DESCRIPTOR_MISMATCH',
      'binding version',
    )
    const digest = constants.digest
    if (typeof digest !== 'string' || !/^sha256:[0-9a-f]{64}$/.test(digest)) {
      throw new HandoffLoadError('DESCRIPTOR_MISMATCH', 'binding digest')
    }
    if (descriptorDigest !== undefined) {
      same(digest, descriptorDigest, 'DESCRIPTOR_MISMATCH', 'schema agreement')
    }
    descriptorDigest = digest
  }
  for (const [field, expected] of Object.entries({
    descriptorId: DESCRIPTOR_ID,
    version: DESCRIPTOR_VERSION,
    digest: descriptorDigest,
  })) {
    same(descriptor[field], expected, 'DESCRIPTOR_MISMATCH', field)
  }

  const bindings = array(handoff.consumerBindings, 'consumerBindings')
  const artifacts = array(handoff.artifacts, 'artifacts')
  if (bindings.length !== 2 || artifacts.length !== 3) {
    throw new HandoffLoadError('HANDOFF_SHAPE', 'bindings/artifacts')
  }
  const artifactByPath = new Map<string, RecordValue>()
  for (const value of artifacts) {
    const artifact = keys(value, ['path', 'version', 'digest'], 'artifact')
    const path = artifact.path
    if (typeof path !== 'string' || artifactByPath.has(path)) {
      throw new HandoffLoadError('HANDOFF_SHAPE', 'artifact path')
    }
    artifactByPath.set(path, artifact)
  }
  const knownPaths = [
    DESCRIPTOR_PATH,
    ...Object.values(CONTRACTS).map((item) => item.path),
  ]
  if ([...artifactByPath.keys()].some((path) => !knownPaths.includes(path))) {
    throw new HandoffLoadError('UNKNOWN_FIELD', 'artifact path')
  }

  const loaded = {} as Record<CalculationId, LoadedHandoffCases>
  const rawByPath = new Map<string, Uint8Array>([
    [DESCRIPTOR_PATH, descriptorRaw],
  ])
  for (const value of bindings) {
    const binding = keys(value, BINDING_KEYS, 'consumerBinding')
    const calculationId = binding.calculationId
    if (
      typeof calculationId !== 'string' ||
      !Object.hasOwn(CONTRACTS, calculationId)
    ) {
      throw new HandoffLoadError('UNKNOWN_FIELD', 'calculationId')
    }
    const id = calculationId as CalculationId
    if (loaded[id])
      throw new HandoffLoadError('HANDOFF_SHAPE', 'duplicate binding')
    const executionPaths = array(binding.executionPaths, 'executionPaths')
    if (executionPaths.length !== 2) {
      throw new HandoffLoadError('HANDOFF_SHAPE', 'executionPaths')
    }
    const runners = new Set<string>()
    for (const value of executionPaths) {
      const execution = keys(value, EXECUTION_PATH_KEYS, 'executionPath')
      const runner = execution.runner
      if (typeof runner !== 'string' || runners.has(runner)) {
        throw new HandoffLoadError('HANDOFF_SHAPE', 'executionPath runner')
      }
      runners.add(runner)
    }
    if (!runners.has('pytest') || !runners.has('vitest')) {
      throw new HandoffLoadError('HANDOFF_SHAPE', 'executionPath runner')
    }
    const spec = CONTRACTS[id]
    for (const [field, expected] of Object.entries({
      vectorId: id,
      contractPath: spec.path,
      version: spec.version,
      schemaVersion: 1,
      caseSchemaRef: '#/$defs/normalizedCase',
    })) {
      same(binding[field], expected, 'VERSION_MISMATCH', field)
    }
    const pointers = mapping(binding, spec.expectedPointer)
    const [raw, contract] = read(spec.path)
    rawByPath.set(spec.path, raw)
    keys(contract, spec.contractKeys, spec.path)
    same(contract.calculation, id, 'VERSION_MISMATCH', spec.path)
    same(contract.version, spec.version, 'VERSION_MISMATCH', spec.path)
    same(contract.schemaVersion, 1, 'SCHEMA_VERSION', spec.path)
    const descriptorRef = keys(
      contract.inputAxesDescriptor,
      ['descriptorId', 'version', 'digest'],
      spec.path,
    )
    for (const field of ['descriptorId', 'version', 'digest']) {
      same(
        descriptorRef[field],
        descriptor[field],
        'DESCRIPTOR_MISMATCH',
        `${spec.path}:${field}`,
      )
    }
    const cases = array(contract.cases, `${spec.path}:cases`)
    if (cases.length === 0)
      throw new HandoffLoadError('HANDOFF_SHAPE', `${spec.path}:empty cases`)
    const seen = new Set<string>()
    const mapped: RecordValue[] = []
    const sourceCases: RecordValue[] = []
    for (const value of cases) {
      const candidate = record(value, `${spec.path}:case`)
      const hasPureInput =
        id === 'state-transition' &&
        (Object.hasOwn(candidate, 'inputId') ||
          Object.hasOwn(candidate, 'inputPayload'))
      const expectedKeys = hasPureInput
        ? [
            ...spec.caseKeys.filter((key) => key !== 'historyInput'),
            'inputId',
            'inputPayload',
          ]
        : spec.caseKeys
      const source = keys(candidate, expectedKeys, `${spec.path}:case`)
      if (hasPureInput) {
        if (
          typeof source.inputId !== 'string' ||
          !/^n[0-9]{4}$/.test(source.inputId)
        ) {
          throw new HandoffLoadError('HANDOFF_SHAPE', 'inputId')
        }
        record(source.inputPayload, 'inputPayload')
      }
      sourceCases.push(source)
      const result: RecordValue = {}
      for (const [target, pointer] of Object.entries(pointers))
        result[target] = source[pointer]
      const caseId = result.caseId
      if (typeof caseId !== 'string' || !caseId || seen.has(caseId)) {
        throw new HandoffLoadError('HANDOFF_SHAPE', `${spec.path}:caseId`)
      }
      seen.add(caseId)
      mapped.push(result)
    }
    loaded[id] = { calculationId: id, cases: mapped, sourceCases }
  }
  if (Object.keys(loaded).length !== Object.keys(CONTRACTS).length) {
    throw new HandoffLoadError('HANDOFF_SHAPE', 'missing binding')
  }
  for (const [path, raw] of rawByPath) {
    const artifact = artifactByPath.get(path)
    if (!artifact) throw new HandoffLoadError('HANDOFF_SHAPE', path)
    const version =
      path === DESCRIPTOR_PATH
        ? DESCRIPTOR_VERSION
        : Object.values(CONTRACTS).find((item) => item.path === path)?.version
    same(artifact.version, version, 'VERSION_MISMATCH', path)
    same(artifact.digest, sha(raw), 'ARTIFACT_DIGEST', path)
  }

  const dependencies = array(handoff.dependencies, 'dependencies')
  if (dependencies.length !== Object.keys(DEPENDENCIES).length) {
    throw new HandoffLoadError('DEPENDENCY_MISMATCH', 'dependency count')
  }
  const seenDependencies = new Set<string>()
  for (const value of dependencies) {
    const dep = keys(
      value,
      [
        'taskId',
        'artifactPath',
        'commitOid',
        'version',
        'establishmentCondition',
      ],
      'dependency',
    )
    const path = dep.artifactPath
    if (
      typeof path !== 'string' ||
      !Object.hasOwn(DEPENDENCIES, path) ||
      seenDependencies.has(path)
    ) {
      throw new HandoffLoadError('DEPENDENCY_MISMATCH', 'dependency path')
    }
    seenDependencies.add(path)
    const pinned = DEPENDENCIES[path as keyof typeof DEPENDENCIES]
    same(dep.taskId, pinned.taskId, 'DEPENDENCY_MISMATCH', path)
    same(dep.commitOid, pinned.commitOid, 'DEPENDENCY_MISMATCH', path)
    same(dep.version, 1, 'DEPENDENCY_MISMATCH', path)
    let raw: Uint8Array
    if (pinned.versionKey === null) {
      raw = readBytes(path)
    } else {
      const [bytes, asset] = read(path)
      raw = bytes
      same(asset[pinned.versionKey], 1, 'DEPENDENCY_MISMATCH', path)
    }
    same(sha(raw), pinned.digest, 'DEPENDENCY_MISMATCH', path)
  }
  return { byCalculation: loaded, descriptor }
}
