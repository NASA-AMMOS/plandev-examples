import resolve from "@rollup/plugin-node-resolve";

export default [
  {
    treeshake: true,
    input: "out-tsc/index.js",
    output: {
      dir: "dist",
      format: "cjs",
      // exports: "default"
    },
    plugins: [
      resolve(), // this resolves imports from node_modules
    ],
  },
];
