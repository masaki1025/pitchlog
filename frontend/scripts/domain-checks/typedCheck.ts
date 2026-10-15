import { readdirSync } from 'node:fs'
import { dirname, join, resolve, sep } from 'node:path'
import ts from 'typescript'

export type TypedRuleId =
  | 'NUMBER_TYPE'
  | 'STRING_TO_NUMBER'
  | 'MATH_ROUNDING'
  | 'UNRESOLVED_ARITHMETIC'
  | 'TYPE_CHECK_FAILED'

export interface TypedViolation {
  ruleId: TypedRuleId
  fileName: string
  line: number
  column: number
  detail: string
}

/** 暗黙に数値化する演算子。加算は文字列連結にもなるため含めない。 */
const COERCING_BINARY_OPERATORS = new Set<ts.SyntaxKind>([
  ts.SyntaxKind.MinusToken,
  ts.SyntaxKind.AsteriskToken,
  ts.SyntaxKind.SlashToken,
  ts.SyntaxKind.PercentToken,
])

/** BigInt を含む算術で any・unknown を判定不能のまま通さない。 */
const ARITHMETIC_OPERATORS = new Set<ts.SyntaxKind>([
  ts.SyntaxKind.PlusToken,
  ...COERCING_BINARY_OPERATORS,
])

const ROUNDING_METHODS = new Set(['round', 'floor', 'ceil', 'trunc'])

/** union・intersection の各成分をたどって、指定した型フラグを調べる。 */
function hasTypeFlag(type: ts.Type, flag: ts.TypeFlags): boolean {
  if ((type.flags & flag) !== 0) return true
  if (type.isUnionOrIntersection()) {
    return type.types.some((part) => hasTypeFlag(part, flag))
  }
  return false
}

/** Math の丸めメソッド名を、直接・リテラル添字の両方で取り出す。 */
function roundingMethod(expression: ts.Expression): string | null {
  if (
    ts.isPropertyAccessExpression(expression) &&
    ts.isIdentifier(expression.expression) &&
    expression.expression.text === 'Math' &&
    ROUNDING_METHODS.has(expression.name.text)
  ) {
    return expression.name.text
  }
  if (
    ts.isElementAccessExpression(expression) &&
    ts.isIdentifier(expression.expression) &&
    expression.expression.text === 'Math' &&
    ts.isStringLiteral(expression.argumentExpression) &&
    ROUNDING_METHODS.has(expression.argumentExpression.text)
  ) {
    return expression.argumentExpression.text
  }
  return null
}

/** 実際の tsconfig と同じ compilerOptions を取得する。 */
function compilerOptions(configPath: string): {
  options?: ts.CompilerOptions
  diagnostics: readonly ts.Diagnostic[]
} {
  const config = ts.readConfigFile(configPath, ts.sys.readFile)
  if (config.error) return { diagnostics: [config.error] }
  const parsed = ts.parseJsonConfigFileContent(
    config.config,
    ts.sys,
    dirname(configPath),
    undefined,
    configPath,
  )
  return { options: parsed.options, diagnostics: parsed.errors }
}

/** 型チェッカーで TS ファイルを検査する。対象外の spec・lib は走査しない。 */
export function inspectTypedFiles(
  fileNames: readonly string[],
  configPath: string,
): TypedViolation[] {
  const normalized = fileNames.map((fileName) => resolve(fileName))
  const { options, diagnostics: configDiagnostics } = compilerOptions(
    resolve(configPath),
  )
  const violations: TypedViolation[] = []

  function reportDiagnostic(diagnostic: ts.Diagnostic, fallback: string): void {
    const source = diagnostic.file
    const fileName = source?.fileName ?? fallback
    const position = source?.getLineAndCharacterOfPosition(
      diagnostic.start ?? 0,
    )
    violations.push({
      ruleId: 'TYPE_CHECK_FAILED',
      fileName,
      line: (position?.line ?? 0) + 1,
      column: (position?.character ?? 0) + 1,
      detail: ts.flattenDiagnosticMessageText(diagnostic.messageText, '\n'),
    })
  }

  for (const diagnostic of configDiagnostics) {
    reportDiagnostic(diagnostic, configPath)
  }
  if (!options || violations.length > 0) return violations

  const program = ts.createProgram({ rootNames: normalized, options })
  const checker = program.getTypeChecker()

  for (const fileName of normalized) {
    const source = program.getSourceFile(fileName)
    if (!source) {
      violations.push({
        ruleId: 'TYPE_CHECK_FAILED',
        fileName,
        line: 1,
        column: 1,
        detail: 'ソースファイルを型チェッカーへ読み込めません',
      })
      continue
    }

    function report(ruleId: TypedRuleId, node: ts.Node, detail: string): void {
      const location = source!.getLineAndCharacterOfPosition(
        node.getStart(source),
      )
      violations.push({
        ruleId,
        fileName,
        line: location.line + 1,
        column: location.character + 1,
        detail,
      })
    }

    function visit(node: ts.Node): void {
      let conversion = false
      let rounding = false
      if (ts.isCallExpression(node)) {
        rounding = roundingMethod(node.expression) !== null
      }
      if (
        ts.isPropertyAccessExpression(node) ||
        ts.isElementAccessExpression(node)
      ) {
        if (roundingMethod(node)) {
          report('MATH_ROUNDING', node, 'Math の丸め関数への参照を禁止する')
        }
      }
      if (ts.isBinaryExpression(node)) {
        const left = checker.getTypeAtLocation(node.left)
        const right = checker.getTypeAtLocation(node.right)
        if (
          COERCING_BINARY_OPERATORS.has(node.operatorToken.kind) &&
          (hasTypeFlag(left, ts.TypeFlags.StringLike) ||
            hasTypeFlag(right, ts.TypeFlags.StringLike))
        ) {
          report(
            'STRING_TO_NUMBER',
            node,
            '算術演算が文字列を number に変換する',
          )
          conversion = true
        }
        if (
          ARITHMETIC_OPERATORS.has(node.operatorToken.kind) &&
          (hasTypeFlag(left, ts.TypeFlags.Any | ts.TypeFlags.Unknown) ||
            hasTypeFlag(right, ts.TypeFlags.Any | ts.TypeFlags.Unknown))
        ) {
          report('UNRESOLVED_ARITHMETIC', node, '算術の型を判定できない')
        }
      }

      let type: ts.Type | undefined
      if (ts.isVariableDeclaration(node) || ts.isParameter(node)) {
        type = checker.getTypeAtLocation(node.name)
      } else if (ts.isFunctionDeclaration(node) || ts.isArrowFunction(node)) {
        const signature = checker.getSignatureFromDeclaration(node)
        type = signature && checker.getReturnTypeOfSignature(signature)
      } else if (ts.isExpression(node) || ts.isTypeNode(node)) {
        type = checker.getTypeAtLocation(node)
      }
      if (
        type &&
        !conversion &&
        !rounding &&
        hasTypeFlag(type, ts.TypeFlags.NumberLike)
      ) {
        report('NUMBER_TYPE', node, '式・宣言・戻り値・型に number が含まれる')
      }
      ts.forEachChild(node, visit)
    }

    visit(source)
    for (const diagnostic of program.getSyntacticDiagnostics(source)) {
      reportDiagnostic(diagnostic, fileName)
    }
    for (const diagnostic of program.getSemanticDiagnostics(source)) {
      reportDiagnostic(diagnostic, fileName)
    }
  }

  return violations
}

/** src/domain の TS 正本だけを型付きで検査する。 */
export function inspectTypedDomainDirectory(
  directory: string,
  configPath: string,
): TypedViolation[] {
  const root = resolve(directory)
  if (!root.endsWith(`${sep}src${sep}domain`)) {
    return [
      {
        ruleId: 'TYPE_CHECK_FAILED',
        fileName: root,
        line: 1,
        column: 1,
        detail: 'src/domain のディレクトリを指定してください',
      },
    ]
  }
  const files: string[] = []
  function collect(current: string): void {
    for (const entry of readdirSync(current, { withFileTypes: true }).sort(
      (left, right) => left.name.localeCompare(right.name),
    )) {
      const path = join(current, entry.name)
      if (entry.isDirectory()) collect(path)
      else if (
        entry.isFile() &&
        entry.name.endsWith('.ts') &&
        !entry.name.endsWith('.spec.ts')
      ) {
        files.push(path)
      }
    }
  }
  collect(root)
  return inspectTypedFiles(files, configPath)
}
