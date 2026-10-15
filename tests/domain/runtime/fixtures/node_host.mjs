import { readFileSync } from "node:fs";
import { createInterface } from "node:readline";
import vm from "node:vm";

const source = readFileSync(process.argv[2], "utf8");
const context = vm.createContext(Object.create(null), {
  codeGeneration: { strings: false, wasm: false },
});
vm.runInContext(source, context, { timeout: 1000 });

for await (const line of createInterface({ input: process.stdin })) {
  context.requestJson = line;
  const response = vm.runInContext("PitchlogSynthetic.run(requestJson)", context, {
    timeout: 1000,
  });
  process.stdout.write(`${response}\n`);
}
