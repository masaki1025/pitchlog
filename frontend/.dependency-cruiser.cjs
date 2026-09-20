/** @type {import('dependency-cruiser').IConfiguration} */
module.exports = {
  forbidden: [
    {
      name: 'no-direct-generated-artifact-import',
      comment:
        '生成物は generated/wrappers 配下の生成ラッパーを経由して利用する。',
      severity: 'error',
      from: {
        path: '(^|/)src/',
        pathNot: '(^|/)src/lib/generated/',
      },
      to: {
        path: '(^|/)src/lib/generated/',
        pathNot: '(^|/)src/lib/generated/wrappers/',
      },
    },
    {
      name: 'no-dynamic-dependency',
      comment: 'ADR-003 D-11 ③ 動的機構の禁止行に従い動的依存を拒否する。',
      severity: 'error',
      from: { path: '(^|/)src/' },
      to: { dynamic: true },
    },
    {
      name: 'no-exotic-dependency',
      comment:
        'ADR-003 D-11 ③ 動的機構の禁止行に従い特殊な読み込みを拒否する。',
      severity: 'error',
      from: { path: '(^|/)src/' },
      to: { exoticallyRequired: true },
    },
    {
      name: 'no-unknown-dependency',
      comment: 'unknown・undetermined dependency を判定不能のまま通さない。',
      severity: 'error',
      from: { path: '(^|/)src/' },
      to: {
        dependencyTypes: ['unknown', 'undetermined', 'npm-unknown'],
      },
    },
    {
      name: 'no-unresolvable-dependency',
      comment: '解決不能な依存を合格にしない。',
      severity: 'error',
      from: { path: '(^|/)src/' },
      to: { couldNotResolve: true },
    },
  ],
  options: {
    doNotFollow: {
      dependencyTypes: [
        'npm',
        'npm-dev',
        'npm-optional',
        'npm-peer',
        'npm-bundled',
      ],
    },
    exclude: '\\.spec\\.ts$',
    tsConfig: { fileName: 'tsconfig.app.json' },
    enhancedResolveOptions: {
      extensions: ['.ts', '.tsx', '.js', '.jsx', '.vue', '.json'],
    },
  },
}
