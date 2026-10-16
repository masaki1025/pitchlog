import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import ts from 'typescript'

/** SQL へ変換する構文、演算、操作をここだけで宣言する。 */
export const SQL_SUBSET = Object.freeze({
  // 型宣言と公開された一つの定義だけを入口とする。
  sourceKinds: Object.freeze([
    ts.SyntaxKind.TypeAliasDeclaration,
    ts.SyntaxKind.VariableStatement,
  ]),
  // 行分類は式、集計は count と sum の式だけを受ける。
  expressionKinds: Object.freeze([
    ts.SyntaxKind.Identifier,
    ts.SyntaxKind.PropertyAccessExpression,
    ts.SyntaxKind.BigIntLiteral,
    ts.SyntaxKind.StringLiteral,
    ts.SyntaxKind.TrueKeyword,
    ts.SyntaxKind.FalseKeyword,
    ts.SyntaxKind.ParenthesizedExpression,
    ts.SyntaxKind.PrefixUnaryExpression,
    ts.SyntaxKind.BinaryExpression,
    ts.SyntaxKind.ConditionalExpression,
  ]),
  operators: Object.freeze({
    [ts.SyntaxKind.PlusToken]: '+',
    [ts.SyntaxKind.MinusToken]: '-',
    [ts.SyntaxKind.AsteriskToken]: '*',
    [ts.SyntaxKind.LessThanToken]: '<',
    [ts.SyntaxKind.LessThanEqualsToken]: '<=',
    [ts.SyntaxKind.GreaterThanToken]: '>',
    [ts.SyntaxKind.GreaterThanEqualsToken]: '>=',
    [ts.SyntaxKind.EqualsEqualsEqualsToken]: '=',
    [ts.SyntaxKind.ExclamationEqualsEqualsToken]: '<>',
    [ts.SyntaxKind.AmpersandAmpersandToken]: 'AND',
    [ts.SyntaxKind.BarBarToken]: 'OR',
  }),
  unaryOperators: Object.freeze([
    ts.SyntaxKind.ExclamationToken,
    ts.SyntaxKind.MinusToken,
  ]),
  functions: Object.freeze([]),
  aggregateKeys: Object.freeze(['count', 'sum']),
  // bigint は 64 bit で桁あふれするため numeric を使う。DB の限界超過は例外で失敗する。
  // 除算と丸めは含めず、将来は 2r ≥ |d| の規則を別途検証する。
  scalarTypes: Object.freeze({
    bigint: 'numeric',
    boolean: 'boolean',
    string: 'text',
  }),
})

const DECIMAL = /^(0|-[1-9][0-9]*|[1-9][0-9]*)$/
const VIRTUAL_FILE = resolve('scripts/domain-sql/__virtual.ts')

export class SqlGenerationError extends Error {
  constructor(ruleId, detail) {
    super(`${ruleId}: ${detail}`)
    this.name = 'SqlGenerationError'
    this.ruleId = ruleId
  }
}

function fail(ruleId, detail) {
  throw new SqlGenerationError(ruleId, detail)
}

/** TS の標準ライブラリを保持し、検査対象だけをメモリ上のソースへ差し替える。 */
function checkedSource(sourceText) {
  const options = {
    target: ts.ScriptTarget.ES2020,
    module: ts.ModuleKind.ESNext,
    strict: true,
    types: [],
    skipLibCheck: true,
  }
  const host = ts.createCompilerHost(options)
  const original = host.getSourceFile.bind(host)
  host.getSourceFile = (
    fileName,
    languageVersion,
    onError,
    shouldCreateNewSourceFile,
  ) =>
    resolve(fileName) === VIRTUAL_FILE
      ? ts.createSourceFile(fileName, sourceText, languageVersion, true)
      : original(fileName, languageVersion, onError, shouldCreateNewSourceFile)
  const program = ts.createProgram([VIRTUAL_FILE], options, host)
  const source = program.getSourceFile(VIRTUAL_FILE)
  if (!source) fail('SQL_TYPE_UNRESOLVED', 'ソースを読み込めない')
  if (program.getSyntacticDiagnostics(source).length > 0) {
    fail('SQL_PARSE_ERROR', 'TypeScript の構文を解析できない')
  }
  return { source, program, checker: program.getTypeChecker() }
}

/** 型の各成分を調べ、三つの SQL 対応型以外を拒否する。 */
function primitiveType(type) {
  if (type.isUnionOrIntersection()) {
    const parts = type.types.map(primitiveType)
    return parts.length > 0 && parts.every((part) => part === parts[0])
      ? parts[0]
      : null
  }
  if (type.flags & ts.TypeFlags.NumberLike) {
    fail('SQL_NUMBER_TYPE', 'number は SQL 変換の境界に入れない')
  }
  if (type.flags & ts.TypeFlags.BigIntLike) return 'bigint'
  if (type.flags & ts.TypeFlags.BooleanLike) return 'boolean'
  if (type.flags & ts.TypeFlags.StringLike) return 'string'
  return null
}

function typeOf(node, checker) {
  const kind = primitiveType(checker.getTypeAtLocation(node))
  if (!kind)
    fail('SQL_TYPE_UNRESOLVED', `式の型を決定できない: ${node.getText()}`)
  return kind
}

function keywordType(node) {
  if (!node) fail('SQL_TYPE_UNRESOLVED', '型注釈がない')
  if (node.kind === ts.SyntaxKind.NumberKeyword) {
    fail('SQL_NUMBER_TYPE', 'number 型を宣言できない')
  }
  if (node.kind === ts.SyntaxKind.BigIntKeyword) return 'bigint'
  if (node.kind === ts.SyntaxKind.BooleanKeyword) return 'boolean'
  if (node.kind === ts.SyntaxKind.StringKeyword) return 'string'
  fail('SQL_TYPE_UNRESOLVED', '許可した基本型以外の型注釈')
}

function rowShape(source) {
  const aliases = source.statements.filter(ts.isTypeAliasDeclaration)
  if (aliases.length !== 1 || aliases[0].name.text !== 'Row') {
    fail('SQL_INVALID_DEFINITION', 'type Row を一つだけ宣言する')
  }
  const alias = aliases[0]
  if (
    alias.typeParameters ||
    alias.modifiers?.length ||
    !ts.isTypeLiteralNode(alias.type) ||
    alias.type.members.length === 0
  ) {
    fail('SQL_UNSUPPORTED_SYNTAX', 'Row は非空の object 型に限る')
  }
  const fields = new Map()
  for (const member of alias.type.members) {
    if (
      !ts.isPropertySignature(member) ||
      !ts.isIdentifier(member.name) ||
      member.modifiers?.length ||
      member.questionToken ||
      fields.has(member.name.text) ||
      ['__proto__', 'constructor', 'prototype'].includes(member.name.text)
    ) {
      fail('SQL_UNSUPPORTED_SYNTAX', 'Row の固定・必須プロパティ以外')
    }
    fields.set(member.name.text, keywordType(member.type))
  }
  return fields
}

function definitionOf(source) {
  if (
    source.referencedFiles.length > 0 ||
    source.typeReferenceDirectives.length > 0 ||
    source.libReferenceDirectives.length > 0 ||
    source.statements.length !== 2 ||
    source.statements.some(
      (node) => !SQL_SUBSET.sourceKinds.includes(node.kind),
    )
  ) {
    fail('SQL_UNSUPPORTED_SYNTAX', '許可したトップレベル宣言以外')
  }
  const statements = source.statements.filter(ts.isVariableStatement)
  const statement = statements[0]
  if (
    statements.length !== 1 ||
    !statement.modifiers?.some(
      (modifier) => modifier.kind === ts.SyntaxKind.ExportKeyword,
    ) ||
    !(statement.declarationList.flags & ts.NodeFlags.Const) ||
    statement.declarationList.declarations.length !== 1
  ) {
    fail('SQL_INVALID_DEFINITION', 'export const definition を一つ宣言する')
  }
  const declaration = statement.declarationList.declarations[0]
  if (
    !ts.isIdentifier(declaration.name) ||
    declaration.name.text !== 'definition' ||
    declaration.type ||
    declaration.exclamationToken
  ) {
    fail('SQL_INVALID_DEFINITION', '公開名は definition に限る')
  }
  return declaration.initializer
}

function validateRows(rows, fields) {
  if (!Array.isArray(rows)) fail('SQL_INVALID_INPUT', 'rows は配列が必要')
  for (const row of rows) {
    if (typeof row !== 'object' || row === null || Array.isArray(row)) {
      fail('SQL_INVALID_INPUT', '行は object が必要')
    }
    if (
      Object.keys(row).length !== fields.size ||
      [...fields.keys()].some((key) => !Object.hasOwn(row, key))
    ) {
      fail('SQL_INVALID_INPUT', '行の列集合が Row と一致しない')
    }
    for (const [key, type] of fields) {
      const value = row[key]
      if (
        (type === 'bigint' &&
          (typeof value !== 'string' || !DECIMAL.test(value))) ||
        (type === 'boolean' && typeof value !== 'boolean') ||
        (type === 'string' && typeof value !== 'string')
      ) {
        fail('SQL_INVALID_INPUT', `行の値が Row と一致しない: ${key}`)
      }
    }
  }
}

function parametersOf(arrow) {
  if (
    !ts.isArrowFunction(arrow) ||
    !ts.isIdentifier(arrow.parameters[0]?.name) ||
    arrow.modifiers?.length ||
    arrow.typeParameters
  ) {
    fail('SQL_UNSUPPORTED_SYNTAX', '式本体のアロー関数が必要')
  }
  const first = arrow.parameters[0]
  if (
    first.name.text !== 'row' ||
    !first.type ||
    !ts.isTypeReferenceNode(first.type) ||
    !ts.isIdentifier(first.type.typeName) ||
    first.type.typeName.text !== 'Row' ||
    first.initializer ||
    first.questionToken ||
    first.dotDotDotToken ||
    first.modifiers?.length
  ) {
    fail('SQL_INVALID_DEFINITION', '先頭引数は row: Row に限る')
  }
  const parameters = new Map()
  for (const parameter of arrow.parameters.slice(1)) {
    if (
      !ts.isIdentifier(parameter.name) ||
      parameter.initializer ||
      parameter.questionToken ||
      parameter.dotDotDotToken ||
      parameter.modifiers?.length ||
      parameters.has(parameter.name.text) ||
      parameter.name.text === 'row'
    ) {
      fail('SQL_UNSUPPORTED_SYNTAX', '固定名と型を持つ引数以外')
    }
    parameters.set(parameter.name.text, keywordType(parameter.type))
  }
  if (ts.isBlock(arrow.body)) fail('SQL_UNSUPPORTED_SYNTAX', '文を含む関数本体')
  return parameters
}

function parameterValue(kind, value, name) {
  if (kind === 'bigint' && typeof value === 'string' && DECIMAL.test(value))
    return value
  if (kind === 'boolean' && typeof value === 'boolean') return value
  if (kind === 'string' && typeof value === 'string') return value
  fail('SQL_INVALID_INPUT', `引数の値が型と一致しない: ${name}`)
}

/** 式を一つずつ SQL へ写し、値は必ずバインド引数へ送る。 */
function expressionSql(node, context) {
  const { checker, fields, parameters, bindings, values, usedBindings } =
    context
  if (ts.isCallExpression(node) || ts.isNewExpression(node)) {
    fail('SQL_UNSUPPORTED_CALL', '呼び出し・再帰・配列操作は変換しない')
  }
  if (!SQL_SUBSET.expressionKinds.includes(node.kind)) {
    if (ts.isNumericLiteral(node)) fail('SQL_NUMBER_TYPE', '数値リテラル')
    fail(
      'SQL_UNSUPPORTED_SYNTAX',
      `変換できない式: ${ts.SyntaxKind[node.kind]}`,
    )
  }
  if (ts.isParenthesizedExpression(node))
    return expressionSql(node.expression, context)
  if (ts.isIdentifier(node)) {
    const kind = parameters.get(node.text)
    if (!kind) fail('SQL_TYPE_UNRESOLVED', `未宣言の引数: ${node.text}`)
    if (!Object.hasOwn(bindings, node.text))
      fail('SQL_INVALID_INPUT', `引数がない: ${node.text}`)
    usedBindings.add(node.text)
    values.push(parameterValue(kind, bindings[node.text], node.text))
    return `%s::${SQL_SUBSET.scalarTypes[kind]}`
  }
  if (ts.isPropertyAccessExpression(node)) {
    if (!ts.isIdentifier(node.expression) || node.expression.text !== 'row') {
      fail('SQL_UNSUPPORTED_SYNTAX', '行の固定列以外へのアクセス')
    }
    const kind = fields.get(node.name.text)
    if (!kind) fail('SQL_TYPE_UNRESOLVED', `Row にない列: ${node.name.text}`)
    const name = node.name.text.replaceAll("'", "''")
    return `(r.doc ->> '${name}')::${SQL_SUBSET.scalarTypes[kind]}`
  }
  if (ts.isBigIntLiteral(node)) {
    const decimal = node.text.endsWith('n') ? node.text.slice(0, -1) : ''
    if (!DECIMAL.test(decimal))
      fail('SQL_UNSUPPORTED_SYNTAX', '十進 BigInt リテラル以外')
    values.push(decimal)
    return '%s::numeric'
  }
  if (ts.isStringLiteral(node)) {
    values.push(node.text)
    return '%s::text'
  }
  if (node.kind === ts.SyntaxKind.TrueKeyword) return 'TRUE'
  if (node.kind === ts.SyntaxKind.FalseKeyword) return 'FALSE'
  if (ts.isPrefixUnaryExpression(node)) {
    if (!SQL_SUBSET.unaryOperators.includes(node.operator)) {
      fail('SQL_UNSUPPORTED_OPERATOR', '許可した単項演算以外')
    }
    if (
      node.operator === ts.SyntaxKind.ExclamationToken &&
      typeOf(node.operand, checker) === 'boolean'
    ) {
      return `(NOT ${expressionSql(node.operand, context)})`
    }
    if (
      node.operator === ts.SyntaxKind.MinusToken &&
      typeOf(node.operand, checker) === 'bigint'
    ) {
      return `(-${expressionSql(node.operand, context)})`
    }
    fail('SQL_UNSUPPORTED_OPERATOR', '許可した単項演算以外')
  }
  if (ts.isBinaryExpression(node)) {
    const operator = SQL_SUBSET.operators[node.operatorToken.kind]
    if (!operator) fail('SQL_UNSUPPORTED_OPERATOR', '許可した二項演算以外')
    const leftSql = expressionSql(node.left, context)
    const rightSql = expressionSql(node.right, context)
    const left = typeOf(node.left, checker)
    const right = typeOf(node.right, checker)
    const arithmetic = ['+', '-', '*'].includes(operator)
    const logical = ['AND', 'OR'].includes(operator)
    const ordered = ['<', '<=', '>', '>='].includes(operator)
    if (
      (arithmetic && (left !== 'bigint' || right !== 'bigint')) ||
      (logical && (left !== 'boolean' || right !== 'boolean')) ||
      (ordered && (left !== 'bigint' || right !== 'bigint')) ||
      (!arithmetic && !logical && !ordered && left !== right)
    ) {
      fail('SQL_UNSUPPORTED_OPERATOR', '演算子と両辺の型が許可集合と一致しない')
    }
    return `(${leftSql} ${operator} ${rightSql})`
  }
  if (ts.isConditionalExpression(node)) {
    if (
      typeOf(node.condition, checker) !== 'boolean' ||
      typeOf(node.whenTrue, checker) !== typeOf(node.whenFalse, checker)
    ) {
      fail('SQL_TYPE_UNRESOLVED', '条件式の型が揃わない')
    }
    return `(CASE WHEN ${expressionSql(node.condition, context)} THEN ${expressionSql(node.whenTrue, context)} ELSE ${expressionSql(node.whenFalse, context)} END)`
  }
  fail('SQL_UNSUPPORTED_SYNTAX', '変換できない式')
}

function compileArrow(arrow, expectedType, shared) {
  const parameters = parametersOf(arrow)
  for (const name of parameters.keys()) shared.declaredBindings.add(name)
  const context = { ...shared, parameters }
  const sql = expressionSql(arrow.body, context)
  const actualType = typeOf(arrow.body, shared.checker)
  if (
    (expectedType && actualType !== expectedType) ||
    (arrow.type && keywordType(arrow.type) !== actualType)
  ) {
    fail('SQL_TYPE_UNRESOLVED', '操作の戻り値が宣言と一致しない')
  }
  return { sql, type: actualType }
}

/** 合成 TS 正本を型付きで検査し、DB 側で実行する単一 SQL とバインド値を返す。 */
export function compileSql(sourceText, mode, rows, bindings = {}) {
  if (!['aggregate', 'classify'].includes(mode))
    fail('SQL_INVALID_DEFINITION', '未知の操作')
  if (
    typeof bindings !== 'object' ||
    bindings === null ||
    Array.isArray(bindings)
  ) {
    fail('SQL_INVALID_INPUT', 'bindings は object が必要')
  }
  const { source, program, checker } = checkedSource(sourceText)
  const fields = rowShape(source)
  const definition = definitionOf(source)
  validateRows(rows, fields)
  const values = []
  const usedBindings = new Set()
  const declaredBindings = new Set()
  const shared = {
    checker,
    fields,
    bindings,
    values,
    usedBindings,
    declaredBindings,
  }
  let sql
  let resultType
  if (mode === 'classify') {
    const classified = compileArrow(definition, null, shared)
    resultType = classified.type
    sql = `SELECT ${classified.sql} AS "value" FROM jsonb_array_elements(%s::jsonb) WITH ORDINALITY AS r(doc, ordinal) ORDER BY r.ordinal`
  } else {
    if (
      !ts.isObjectLiteralExpression(definition) ||
      definition.properties.length !== 2
    ) {
      fail('SQL_INVALID_DEFINITION', '集計は count と sum の二つに限る')
    }
    const operations = new Map()
    for (const property of definition.properties) {
      if (
        !ts.isPropertyAssignment(property) ||
        !ts.isIdentifier(property.name)
      ) {
        fail('SQL_UNSUPPORTED_SYNTAX', '固定名の集計操作以外')
      }
      if (
        !SQL_SUBSET.aggregateKeys.includes(property.name.text) ||
        operations.has(property.name.text)
      ) {
        fail('SQL_INVALID_DEFINITION', '集計操作は count と sum のみ')
      }
      operations.set(property.name.text, property.initializer)
    }
    if (!operations.has('count') || !operations.has('sum')) {
      fail('SQL_INVALID_DEFINITION', 'count と sum が必要')
    }
    const counted = compileArrow(operations.get('count'), 'boolean', shared)
    const summed = compileArrow(operations.get('sum'), 'bigint', shared)
    resultType = 'aggregate'
    sql = `SELECT COUNT(*) FILTER (WHERE ${counted.sql})::numeric AS "count", COALESCE(SUM(${summed.sql}), 0::numeric) AS "sum" FROM jsonb_array_elements(%s::jsonb) AS r(doc)`
  }
  if (program.getSemanticDiagnostics(source).length > 0) {
    fail('SQL_TYPE_UNRESOLVED', 'TypeScript の意味検査に失敗した')
  }
  if (Object.keys(bindings).some((name) => !usedBindings.has(name))) {
    fail('SQL_INVALID_INPUT', '使わない引数がある')
  }
  if ([...declaredBindings].some((name) => !usedBindings.has(name))) {
    fail('SQL_INVALID_DEFINITION', '使わない引数が宣言されている')
  }
  values.push(JSON.stringify(rows))
  return { sql, parameters: values, resultType }
}

/** 試験用 CLI は SQL とパラメータだけを JSON で返す。 */
if (
  process.argv[1] &&
  resolve(process.argv[1]) === fileURLToPath(import.meta.url)
) {
  try {
    const sourceText = readFileSync(resolve(process.argv[2]), 'utf8')
    let input = ''
    for await (const chunk of process.stdin) input += chunk
    const payload = JSON.parse(input)
    process.stdout.write(
      `${JSON.stringify(compileSql(sourceText, process.argv[3], payload.rows, payload.bindings))}\n`,
    )
  } catch (error) {
    process.stderr.write(
      `${error instanceof Error ? error.message : 'SQL 生成に失敗'}\n`,
    )
    process.exitCode = 1
  }
}
