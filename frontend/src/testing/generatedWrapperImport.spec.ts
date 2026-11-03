// @vitest-environment node
import { ESLint } from 'eslint'
import { expect, it } from 'vitest'

it('正規wrapper経由を許可し生成物への直接到達は拒否する', async () => {
  const eslint = new ESLint()
  for (const [path, forbidden] of [
    ['../lib/generated/wrappers/domainArtifact', false],
    ['../lib/generated/artifacts/domainArtifact', true],
    ['../lib/generated/directArtifact', true],
  ] as const) {
    const [result] = await eslint.lintText(
      `import { value } from '${path}'\nvoid value\n`,
      { filePath: 'src/screens/GameScreenFirstBallProvider.ts' },
    )
    expect(
      result!.messages.some(
        (message) => message.ruleId === 'no-restricted-imports',
      ),
      path,
    ).toBe(forbidden)
  }
})
