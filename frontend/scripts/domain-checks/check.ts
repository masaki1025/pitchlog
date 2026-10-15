import { readFileSync, readdirSync } from 'node:fs'
import { join, resolve, sep } from 'node:path'
import ts from 'typescript'
import {
  ALLOWED_BINARY_OPERATORS,
  ALLOWED_SYNTAX,
  HOST_FUNCTIONS,
  SAFE_INTRINSICS,
} from './policy'

export type RuleId =
  | 'PARSE_ERROR'
  | 'UNKNOWN_SYNTAX'
  | 'UNSUPPORTED_OPERATOR'
  | 'VAR_DECLARATION'
  | 'EVAL'
  | 'FUNCTION_CONSTRUCTOR'
  | 'DYNAMIC_IMPORT'
  | 'REQUIRE'
  | 'WITH'
  | 'GLOBAL_OBJECT'
  | 'DATE'
  | 'MATH_RANDOM'
  | 'INTL'
  | 'PROXY'
  | 'REFLECT'
  | 'REGEXP'
  | 'UNDECLARED_HOST_FUNCTION'
  | 'UNDECLARED_GLOBAL'
  | 'NON_STATIC_IMPORT'

export interface Violation {
  ruleId: RuleId
  fileName: string
  line: number
  column: number
  detail: string
}

/** 各規則の拒否理由。診断にも同じ文言を載せる。 */
export const RULE_REASONS: Readonly<Record<RuleId, string>> = {
  PARSE_ERROR: '構文解析が完了せず、判定できないため',
  UNKNOWN_SYNTAX: '宣言した変換可能な構文に含まれないため',
  UNSUPPORTED_OPERATOR: '演算子の意味を変換可能な集合で宣言していないため',
  VAR_DECLARATION: 'var は関数スコープへ巻き上がり局所束縛を曖昧にするため',
  EVAL: '実行時に新しいコードを生成できるため',
  FUNCTION_CONSTRUCTOR: '関数コンストラクタ経由でコードを生成できるため',
  DYNAMIC_IMPORT: '実行時に依存先を増やせるため',
  REQUIRE: '実行時に依存先を増やせるため',
  WITH: '識別子の解決先が実行時のオブジェクトに依存するため',
  GLOBAL_OBJECT: '未宣言のホスト機能へ到達できるため',
  DATE: '時刻と環境に依存するため',
  MATH_RANDOM: '乱数に依存するため',
  INTL: 'ロケールとエンジンの実装に依存するため',
  PROXY: '通常のプロパティ操作の意味を変更できるため',
  REFLECT: '動的なプロパティ操作を許してしまうため',
  REGEXP: '正規表現の実装差を境界に持ち込むため',
  UNDECLARED_HOST_FUNCTION: 'ホストが提供する関数として宣言されていないため',
  UNDECLARED_GLOBAL: '宣言済みの局所名または標準名ではないため',
  NON_STATIC_IMPORT: '閉じた領域内の静的な相対依存ではないため',
}

interface Scope {
  parent?: Scope
  names: Set<string>
}

const BANNED_IDENTIFIERS = new Map<string, RuleId>([
  ['eval', 'EVAL'],
  ['Function', 'FUNCTION_CONSTRUCTOR'],
  ['require', 'REQUIRE'],
  ['Date', 'DATE'],
  ['Intl', 'INTL'],
  ['Proxy', 'PROXY'],
  ['Reflect', 'REFLECT'],
  ['RegExp', 'REGEXP'],
])

const GLOBAL_OBJECTS = new Set(['globalThis', 'window', 'self', 'global'])

/** 束縛名を局所スコープへ追加する。 */
function addBinding(name: ts.BindingName, scope: Scope): void {
  if (ts.isIdentifier(name)) {
    scope.names.add(name.text)
    return
  }
  for (const element of name.elements) {
    if (!ts.isOmittedExpression(element)) addBinding(element.name, scope)
  }
}

/** 同じブロックにある宣言を、前方の関数参照も含めて収集する。 */
function collectStatements(
  statements: ts.NodeArray<ts.Statement>,
  scope: Scope,
): void {
  for (const statement of statements) {
    if (
      ts.isFunctionDeclaration(statement) ||
      ts.isTypeAliasDeclaration(statement)
    ) {
      if (statement.name) scope.names.add(statement.name.text)
    } else if (ts.isVariableStatement(statement)) {
      for (const declaration of statement.declarationList.declarations) {
        addBinding(declaration.name, scope)
      }
    } else if (ts.isImportDeclaration(statement) && statement.importClause) {
      if (statement.importClause.name)
        scope.names.add(statement.importClause.name.text)
      const bindings = statement.importClause.namedBindings
      if (bindings && ts.isNamedImports(bindings)) {
        for (const specifier of bindings.elements)
          scope.names.add(specifier.name.text)
      }
    }
  }
}

/** 識別子が宣言名や固定プロパティ名なら参照として扱わない。 */
function isReference(node: ts.Identifier): boolean {
  const parent = node.parent
  if (
    (ts.isPropertyAccessExpression(parent) && parent.name === node) ||
    (ts.isPropertyAssignment(parent) && parent.name === node) ||
    (ts.isPropertySignature(parent) && parent.name === node) ||
    (ts.isFunctionDeclaration(parent) && parent.name === node) ||
    (ts.isVariableDeclaration(parent) && parent.name === node) ||
    (ts.isParameter(parent) && parent.name === node) ||
    (ts.isTypeAliasDeclaration(parent) && parent.name === node) ||
    ts.isImportSpecifier(parent) ||
    ts.isExportSpecifier(parent) ||
    (ts.isImportClause(parent) && parent.name === node)
  ) {
    return false
  }
  return true
}

/** 公開口への直接代入に含まれる globalThis だけを許す。 */
function isEntryAssignment(node: ts.Identifier, fileName: string): boolean {
  const normalized = fileName.replaceAll('\\', '/')
  if (!normalized.endsWith('/src/domain/entry.ts')) return false
  if (!ts.isAsExpression(node.parent) || node.parent.expression !== node)
    return false
  let cast: ts.Node = node.parent
  while (ts.isParenthesizedExpression(cast.parent)) cast = cast.parent
  const access = cast.parent
  if (
    !ts.isPropertyAccessExpression(access) ||
    access.expression !== cast ||
    access.name.text !== 'PitchlogDomain'
  ) {
    return false
  }
  const assignment = access.parent
  return (
    ts.isBinaryExpression(assignment) &&
    assignment.left === access &&
    assignment.operatorToken.kind === ts.SyntaxKind.EqualsToken &&
    ts.isIdentifier(assignment.right) &&
    assignment.right.text === 'domainOperations'
  )
}

/** 参照元スコープから局所束縛を解決する。 */
function isBound(name: string, scope: Scope): boolean {
  let current: Scope | undefined = scope
  while (current) {
    if (current.names.has(name)) return true
    current = current.parent
  }
  return false
}

/** 規則に反する構文を最初に判定し、未知構文との重複を避ける。 */
function explicitRule(
  node: ts.Node,
  fileName: string,
  scope: Scope,
): RuleId | null {
  if (ts.isWithStatement(node)) return 'WITH'
  if (ts.isRegularExpressionLiteral(node)) return 'REGEXP'
  if (ts.isCallExpression(node)) {
    if (node.expression.kind === ts.SyntaxKind.ImportKeyword)
      return 'DYNAMIC_IMPORT'
    if (
      ts.isIdentifier(node.expression) &&
      node.expression.text === 'require'
    ) {
      return 'REQUIRE'
    }
  }
  if (ts.isNewExpression(node) && ts.isIdentifier(node.expression)) {
    const banned = BANNED_IDENTIFIERS.get(node.expression.text)
    if (banned) return banned
  }
  if (ts.isPropertyAccessExpression(node)) {
    if (node.name.text === 'constructor' || node.name.text === '__proto__') {
      return 'FUNCTION_CONSTRUCTOR'
    }
    if (
      ts.isIdentifier(node.expression) &&
      node.expression.text === 'Math' &&
      node.name.text === 'random'
    ) {
      return 'MATH_RANDOM'
    }
  }
  if (ts.isElementAccessExpression(node)) {
    if (
      ts.isIdentifier(node.expression) &&
      node.expression.text === 'Math' &&
      ts.isStringLiteral(node.argumentExpression) &&
      node.argumentExpression.text === 'random'
    ) {
      return 'MATH_RANDOM'
    }
    if (
      ts.isStringLiteral(node.argumentExpression) &&
      (node.argumentExpression.text === 'constructor' ||
        node.argumentExpression.text === '__proto__')
    ) {
      return 'FUNCTION_CONSTRUCTOR'
    }
  }
  if (ts.isIdentifier(node) && isReference(node)) {
    if (GLOBAL_OBJECTS.has(node.text)) {
      return node.text === 'globalThis' && isEntryAssignment(node, fileName)
        ? null
        : 'GLOBAL_OBJECT'
    }
    const banned = BANNED_IDENTIFIERS.get(node.text)
    if (banned) return banned
    const isStandardType =
      node.text === 'Record' &&
      ts.isTypeReferenceNode(node.parent) &&
      node.parent.typeName === node
    if (
      !isBound(node.text, scope) &&
      !SAFE_INTRINSICS.has(node.text) &&
      !isStandardType
    ) {
      if (ts.isCallExpression(node.parent) && node.parent.expression === node) {
        return HOST_FUNCTIONS.has(node.text) ? null : 'UNDECLARED_HOST_FUNCTION'
      }
      return 'UNDECLARED_GLOBAL'
    }
  }
  if (ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) {
    const path = node.moduleSpecifier
    if (path && (!ts.isStringLiteral(path) || !path.text.startsWith('./'))) {
      return 'NON_STATIC_IMPORT'
    }
  }
  if (ts.isVariableDeclarationList(node)) {
    const isConst = (node.flags & ts.NodeFlags.Const) !== 0
    const isLet = (node.flags & ts.NodeFlags.Let) !== 0
    if (!isConst && !isLet) return 'VAR_DECLARATION'
  }
  if (
    ts.isBinaryExpression(node) &&
    !ALLOWED_BINARY_OPERATORS.has(node.operatorToken.kind)
  ) {
    return 'UNSUPPORTED_OPERATOR'
  }
  if (
    ts.isPrefixUnaryExpression(node) &&
    node.operator !== ts.SyntaxKind.ExclamationToken &&
    node.operator !== ts.SyntaxKind.MinusToken
  ) {
    return 'UNSUPPORTED_OPERATOR'
  }
  return null
}

/** TS ソースを構文だけで検査する。解析不能と未宣言構文は必ず違反にする。 */
export function inspectSource(
  sourceText: string,
  fileName: string,
): Violation[] {
  const source = ts.createSourceFile(
    fileName,
    sourceText,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TS,
  )
  const violations: Violation[] = []

  function report(ruleId: RuleId, node: ts.Node, detail: string): void {
    const location = source.getLineAndCharacterOfPosition(node.getStart(source))
    violations.push({
      ruleId,
      fileName,
      line: location.line + 1,
      column: location.character + 1,
      detail: `${RULE_REASONS[ruleId]}: ${detail}`,
    })
  }

  // createSourceFile が持つ構文診断が読めない版も、合格にはしない。
  const parseDiagnostics = (
    source as ts.SourceFile & { parseDiagnostics?: readonly ts.Diagnostic[] }
  ).parseDiagnostics
  if (!parseDiagnostics) {
    return [
      {
        ruleId: 'PARSE_ERROR',
        fileName,
        line: 1,
        column: 1,
        detail: `${RULE_REASONS.PARSE_ERROR}: 構文診断を取得できません`,
      },
    ]
  }
  for (const diagnostic of parseDiagnostics) {
    const start = diagnostic.start ?? 0
    const location = source.getLineAndCharacterOfPosition(start)
    violations.push({
      ruleId: 'PARSE_ERROR',
      fileName,
      line: location.line + 1,
      column: location.character + 1,
      detail: `${RULE_REASONS.PARSE_ERROR}: ${ts.flattenDiagnosticMessageText(diagnostic.messageText, '\n')}`,
    })
  }
  if (violations.length > 0) return violations

  function visit(node: ts.Node, parentScope: Scope): void {
    let scope = parentScope
    if (ts.isSourceFile(node) || ts.isBlock(node)) {
      scope = { parent: parentScope, names: new Set() }
      collectStatements(node.statements, scope)
    } else if (ts.isFunctionDeclaration(node) || ts.isArrowFunction(node)) {
      scope = { parent: parentScope, names: new Set() }
      if (ts.isFunctionDeclaration(node) && node.name)
        scope.names.add(node.name.text)
      for (const parameter of node.parameters) addBinding(parameter.name, scope)
    } else if (ts.isCatchClause(node)) {
      scope = { parent: parentScope, names: new Set() }
      if (node.variableDeclaration)
        addBinding(node.variableDeclaration.name, scope)
    } else if (ts.isForOfStatement(node)) {
      scope = { parent: parentScope, names: new Set() }
      if (ts.isVariableDeclarationList(node.initializer)) {
        for (const declaration of node.initializer.declarations) {
          addBinding(declaration.name, scope)
        }
      }
    }

    const explicit = explicitRule(node, fileName, scope)
    if (explicit) {
      report(explicit, node, node.getText(source))
      return
    }
    if (!ALLOWED_SYNTAX.has(node.kind)) {
      report('UNKNOWN_SYNTAX', node, ts.SyntaxKind[node.kind])
      return
    }
    ts.forEachChild(node, (child) => visit(child, scope))
  }

  visit(source, { names: new Set() })
  return violations
}

/** src/domain の TS 正本だけを、パス順を固定して検査する。 */
export function inspectDomainDirectory(directory: string): Violation[] {
  const violations: Violation[] = []
  const root = resolve(directory)

  function inspectDirectory(current: string): void {
    for (const entry of readdirSync(current, { withFileTypes: true }).sort(
      (a, b) => a.name.localeCompare(b.name),
    )) {
      const path = join(current, entry.name)
      if (entry.isDirectory()) inspectDirectory(path)
      else if (
        entry.isFile() &&
        entry.name.endsWith('.ts') &&
        !entry.name.endsWith('.spec.ts')
      ) {
        violations.push(...inspectSource(readFileSync(path, 'utf8'), path))
      }
    }
  }

  if (!root.endsWith(`${sep}src${sep}domain`)) {
    throw new Error('src/domain のディレクトリを指定してください')
  }
  inspectDirectory(root)
  return violations
}
