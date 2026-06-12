/**
 * Bundles the openmct-plandev plugin (TypeScript) into a single browser global
 * that the OpenMCT host page loads via a <script> tag — the same no-bundler
 * pattern nasa/openmct-tutorial uses for its plugins.
 *
 * @type {import('rollup').RollupOptions}
 */
import commonjs from '@rollup/plugin-commonjs';
import { nodeResolve } from '@rollup/plugin-node-resolve';
import typescript from '@rollup/plugin-typescript';

export default {
  input: './plugin/src/index.ts',
  output: {
    file: './host/lib/openmct-plandev.js',
    format: 'iife',
    name: 'openmctPlandev',
    exports: 'default',
  },
  plugins: [
    nodeResolve({ browser: true }),
    commonjs(),
    typescript({ tsconfig: './tsconfig.json' }),
  ],
};
