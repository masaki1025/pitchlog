globalThis.PitchlogDomain = Object.freeze({
  probe(requestJson) {
    const request = JSON.parse(requestJson)
    if (request.mode === 'loop') {
      while (true) {}
    }
    if (request.mode === 'memory') {
      const chunks = []
      while (true) chunks.push(new Array(50000).fill('x'))
    }
    if (request.mode === 'never') return new Promise(() => {})
    if (request.mode === 'eval') return eval('"unexpected"')
    if (request.mode === 'newFunction') return new Function('return "unexpected"')()
    if (request.mode === 'constructor') {
      return Function.prototype.constructor('return "unexpected"')()
    }
    if (request.mode === 'import') return import('node:fs')
    if (request.mode === 'globals') {
      return JSON.stringify({
        require: typeof require,
        process: typeof process,
        fs: typeof fs,
        console: typeof console,
      })
    }
    return JSON.stringify({ ok: true, value: request.value })
  },
})
