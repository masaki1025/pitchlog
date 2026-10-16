import ts from 'typescript'

const FORBIDDEN_TOKENS = new Map([
  [ts.SyntaxKind.ImportKeyword, 'import'],
  [ts.SyntaxKind.ExportKeyword, 'export'],
  [ts.SyntaxKind.RequireKeyword, 'require'],
])

/** JS の字句を走査し、文字列・コメント外の動的読み込みとモジュール構文を拒否する。 */
export function inspectArtifactTokens(sourceText) {
  const source = ts.createSourceFile(
    'pitchlog-domain.js',
    sourceText,
    ts.ScriptTarget.ES2020,
    true,
    ts.ScriptKind.JS,
  )
  const diagnostics = source.parseDiagnostics
  if (!Array.isArray(diagnostics)) {
    return [{ token: 'PARSE_ERROR', position: 0 }]
  }
  if (diagnostics.length > 0) {
    return diagnostics.map((diagnostic) => ({
      token: 'PARSE_ERROR',
      position: diagnostic.start ?? 0,
    }))
  }

  const scanner = ts.createScanner(
    ts.ScriptTarget.ES2020,
    false,
    ts.LanguageVariant.Standard,
    sourceText,
  )
  const violations = []
  const templates = []
  let kind = scanner.scan()
  while (kind !== ts.SyntaxKind.EndOfFileToken) {
    if (kind === ts.SyntaxKind.TemplateHead) {
      templates.push({ braceDepth: 0 })
    } else if (kind === ts.SyntaxKind.OpenBraceToken && templates.length > 0) {
      templates.at(-1).braceDepth += 1
    } else if (kind === ts.SyntaxKind.CloseBraceToken && templates.length > 0) {
      const current = templates.at(-1)
      if (current.braceDepth > 0) {
        current.braceDepth -= 1
      } else {
        kind = scanner.reScanTemplateToken(false)
        if (kind === ts.SyntaxKind.TemplateTail) templates.pop()
      }
    }
    const identifier =
      kind === ts.SyntaxKind.Identifier ? scanner.getTokenValue() : null
    const forbidden =
      FORBIDDEN_TOKENS.get(kind) ??
      (identifier === 'require' ||
      identifier === 'import' ||
      identifier === 'export'
        ? identifier
        : null)
    if (forbidden) {
      violations.push({ token: forbidden, position: scanner.getTokenPos() })
    }
    if (
      kind === ts.SyntaxKind.Unknown ||
      (scanner.getTokenFlags() & ts.TokenFlags.Unterminated) !== 0
    ) {
      violations.push({
        token: 'UNKNOWN_TOKEN',
        position: scanner.getTokenPos(),
      })
    }
    kind = scanner.scan()
  }
  return violations
}
