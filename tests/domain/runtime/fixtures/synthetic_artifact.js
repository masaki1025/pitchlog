(function () {
  "use strict";

  globalThis.PitchlogSynthetic = Object.freeze({
    run(requestJson) {
      try {
        const request = JSON.parse(requestJson);
        if (request.operation === "echo") {
          return JSON.stringify({ value: BigInt(request.value).toString() });
        }
        if (request.operation === "arithmetic") {
          const left = BigInt(request.left);
          const right = BigInt(request.right);
          let value;
          switch (request.operator) {
            case "add":
              value = left + right;
              break;
            case "subtract":
              value = left - right;
              break;
            case "multiply":
              value = left * right;
              break;
            case "divide":
              // BigInt の除算は 0 方向へ切り捨てる。
              if (right === 0n) throw new Error("zero_divisor");
              value = left / right;
              break;
            default:
              throw new Error("unknown_operator");
          }
          return JSON.stringify({ value: value.toString() });
        }
        if (request.operation === "sort") {
          const rows = request.rows.slice();
          rows.sort((left, right) =>
            left.key < right.key ? -1 : left.key > right.key ? 1 : 0,
          );
          return JSON.stringify({ rows });
        }
        if (request.operation === "error") {
          throw new Error("synthetic_error");
        }
        throw new Error("unknown_operation");
      } catch (error) {
        return JSON.stringify({ error: error.message });
      }
    },
  });
})();
