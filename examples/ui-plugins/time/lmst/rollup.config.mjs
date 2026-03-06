// rollup.config.js
/**
 * @type {import('rollup').RollupOptions}
 */
import typescript from "@rollup/plugin-typescript";
import { nodeResolve } from '@rollup/plugin-node-resolve';

export default {
  input: "./time-plugin.ts",
  output: {
    dir: "./build",
    format: "esm",
  },
  plugins: [nodeResolve(), typescript({tsconfig: "../../../tsconfig.json"})],
};
