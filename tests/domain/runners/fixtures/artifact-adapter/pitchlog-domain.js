// 正規化と加算だけを行う試験専用の単一 artifact。
(() => {
  function normalize(requestJson) {
    const rows = JSON.parse(requestJson)
    return JSON.stringify(
      rows.map((row) => ({ value: BigInt(row.legacyValue).toString() })),
    )
  }

  function calculate(requestJson) {
    const request = JSON.parse(requestJson)
    if (typeof request.caseId !== 'string') throw new Error('caseId')
    return JSON.stringify(
      request.normalized.map((row) => ({
        value: (BigInt(row.value) + 1n).toString(),
      })),
    )
  }

  globalThis.PitchlogDomain = Object.freeze({ normalize, calculate })
})()
