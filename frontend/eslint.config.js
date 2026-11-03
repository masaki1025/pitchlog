import eslintConfigPrettier from 'eslint-config-prettier/flat'
import pluginVue from 'eslint-plugin-vue'
import tseslint from 'typescript-eslint'

// /check（.claude/skills/check/SKILL.md）と CI は、素の `pnpm exec eslint .` を実行する。
// warning のままでは exit 0 となり、検査として機能しない。
// `--max-warnings` は CLI 専用オプションで flat config には書けないため、設定側で severity を error に引き上げる。
// flat/recommended の各 config の rules を走査し、配列なら 2 要素目以降のオプションを保ったまま
// severity だけを error に置き換える。将来 eslint-plugin-vue が規則を追加した場合も一律に効き、
// プラグイン更新時に新規則で赤くなることがあるが、それは意図した挙動である。
const vueRecommended = pluginVue.configs['flat/recommended'].map((config) => ({
  ...config,
  rules: Object.fromEntries(
    Object.entries(config.rules ?? {}).map(([name, setting]) => [
      name,
      Array.isArray(setting) ? ['error', ...setting.slice(1)] : 'error',
    ]),
  ),
}))

export default [
  {
    ignores: ['dist/**', 'scripts/domain-checks/fixtures/**'],
  },
  ...vueRecommended,
  ...tseslint.configs.recommended.map((config) => ({
    ...config,
    files: ['**/*.ts'],
  })),
  {
    files: ['**/*.vue'],
    languageOptions: {
      parserOptions: {
        parser: tseslint.parser,
      },
    },
    rules: {
      'vue/multi-word-component-names': [
        'error',
        { ignores: ['Button', 'Sheet', 'Toast'] },
      ],
    },
  },
  {
    files: ['**/*.ts', '**/*.vue'],
    plugins: {
      '@typescript-eslint': tseslint.plugin,
    },
    rules: {
      'no-eval': 'error',
      'no-implied-eval': 'error',
      'no-new-func': 'error',
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              group: [
                '**/lib/generated/*',
                '!**/lib/generated/wrappers',
                '!**/lib/generated/wrappers/**',
                '**/lib/generated/artifacts/**',
              ],
              message:
                '生成物は generated/wrappers 配下の生成ラッパーを経由してください。',
            },
          ],
        },
      ],
      'no-restricted-syntax': [
        'error',
        {
          selector: 'ImportExpression',
          message: '動的 import は入口を静的に閉じられないため禁止です。',
        },
      ],
      '@typescript-eslint/no-require-imports': 'error',
    },
  },
  {
    files: ['src/**/*.{ts,tsx,vue}'],
    // ステップ 9 の読み込み口だけが公開口を参照する。
    ignores: ['src/domain/**', 'src/lib/generated/wrappers/domainArtifact.ts'],
    rules: {
      'no-restricted-globals': [
        'error',
        {
          name: 'PitchlogDomain',
          message:
            'ドメイン公開口は src/lib/generated/wrappers/domainArtifact.ts を経由してください。',
        },
      ],
      'no-restricted-properties': [
        'error',
        {
          property: 'PitchlogDomain',
          message:
            'ドメイン公開口は src/lib/generated/wrappers/domainArtifact.ts を経由してください。',
        },
      ],
    },
  },
  // Prettier と競合する整形規則だけを最後に無効化する。
  eslintConfigPrettier,
  {
    // 第 1 期の U-F8 は、利用者の確定操作から永続追記・送信へ進ませない
    // (docs/features/uf8-game-recording/design.md 6-2)。到達の禁止を試験の
    // 文字列照合に頼ると、表記違い・動的 import・再 export で迂回できるため、
    // 機構(lint)で落とす。解除は封鎖を外す PR で同時に行う。
    files: ['src/screens/GameScreen.vue'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              group: [
                '**/GameScreenPitchCommit*',
                '**/GameScreenPitchAcceptance*',
                '**/GameScreenAckApplication*',
                '**/client.syncEvents*',
                '**/api/client',
                '**/lib/sync/durableQueue*',
                '**/lib/sync/singleWriter*',
                '**/lib/sync/clientDiscipline*',
              ],
              message:
                '第 1 期は確定の経路へ到達させない(uf8-game-recording/design.md 6-2)。',
            },
            {
              // flat config の後勝ちは規則ごとオプションを置換するため、
              // 一般ブロックの禁止をここへ書き戻さないとこのファイルだけ消える。
              group: [
                '**/lib/generated/*',
                '!**/lib/generated/wrappers',
                '!**/lib/generated/wrappers/**',
                '**/lib/generated/artifacts/**',
              ],
              message:
                '生成物は generated/wrappers 配下の生成ラッパーを経由してください。',
            },
          ],
        },
      ],
      // import を塞いでも、素の fetch / indexedDB で到達できてしまう。
      // 2 周目 P0 の反例がまさにこれだったので、グローバルも落とす。
      'no-restricted-globals': [
        'error',
        {
          name: 'fetch',
          message:
            '第 1 期は確定の経路へ到達させない(uf8-game-recording/design.md 6-2)。',
        },
        {
          name: 'XMLHttpRequest',
          message:
            '第 1 期は確定の経路へ到達させない(uf8-game-recording/design.md 6-2)。',
        },
        {
          name: 'indexedDB',
          message:
            '第 1 期は確定の経路へ到達させない(uf8-game-recording/design.md 6-2)。',
        },
        {
          name: 'caches',
          message:
            '第 1 期は確定の経路へ到達させない(uf8-game-recording/design.md 6-2)。',
        },
        {
          name: 'PitchlogDomain',
          message:
            'ドメイン計算は generated/wrappers の公開口から呼び出してください。',
        },
      ],
    },
  },
]
