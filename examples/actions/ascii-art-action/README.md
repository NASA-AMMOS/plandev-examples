# plandev-ascii-art-action

**What this teaches:** bundling a third-party npm dependency and its data files into a single
uploadable action.

The action itself is frivolous — it reads a file from the plan, renders the text as
[figlet](https://www.npmjs.com/package/figlet) ASCII art, and optionally writes the result
back. The packaging is the point.

## The bundling problem

An action is uploaded as **one self-contained JavaScript file**. There's no `node_modules` at
runtime, so anything a dependency loads lazily won't be there. figlet loads fonts on demand.

The fix, in [`src/index.ts`](src/index.ts): import each font explicitly so the bundler inlines
it, then register it.

```ts
// @ts-ignore  (these font modules ship no type declarations)
import Roman from "figlet/importable-fonts/Roman.js";
figlet.parseFont("roman", Roman);
```

[`rollup.config.js`](rollup.config.js) does the rest — `inlineDynamicImports` forces one file,
and the `commonjs` plugin converts figlet's CJS sources.

## Parameters and settings

|           | Name        | Type    | Meaning                                               |
| --------- | ----------- | ------- | ----------------------------------------------------- |
| Parameter | `inputFile` | string  | File in the plan to read text from (required)         |
| Parameter | `font`      | string  | `roman`, `caligraphy`, or `colossal`. Default `roman` |
| Setting   | `writeFile` | boolean | Write the art back as `figlet-<timestamp>`            |

## Build & try it

```bash
npm install
npm run build      # -> dist/action.js
npm test
```

Upload `dist/action.js`, add a file with a short string to your plan, and run the action with
`inputFile` set to it. The art appears in the run logs.
