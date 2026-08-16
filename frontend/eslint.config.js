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
    ignores: ['dist/**'],
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
  },
  // Prettier と競合する整形規則だけを最後に無効化する。
  eslintConfigPrettier,
]
