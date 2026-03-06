import resolve from "@rollup/plugin-node-resolve";
import commonjs from "@rollup/plugin-commonjs";

export default [
  {
    treeshake: true,
    input: "out-tsc/index.js",
    output: {
      file: "dist/action.js",
      format: "cjs",
      inlineDynamicImports: true, // force inlining
      sourcemap: false,
    },
    plugins: [
      resolve({ preferBuiltins: true }), // allows node_modules resolution
      commonjs({
        transformMixedEsModules: true, // enables deeper cjs -> esm conversion
        requireReturnsDefault: "auto", // fixes issues with cjs default exports
      }),
    ],
  },
];
