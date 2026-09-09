# plandev-basic-action

**What this teaches:** the shape of a PlanDev Action. Start here.

An action exports three things, all in [`src/index.ts`](src/index.ts):

- **`parameterDefinitions`** — values supplied per run (`urlPath`, `sleepMs`)
- **`settingDefinitions`** — values configured once at upload (`externalUrl`)
- **`main(parameters, settings, actionsAPI)`** — the entry point; its return value is the run's result

The `satisfies` clauses let TypeScript derive the parameter and setting types, so
`parameters.urlPath` is known to be a `string` without a second declaration to keep in sync.

This example also calls an external URL, then reads and writes plan files via `actionsAPI`.

> **Note:** `fetch` only rejects on network failure — an HTTP 500 resolves normally, so
> `result.ok` is checked explicitly and throws. Throwing is what marks a run as failed; the
> optional file read is caught and warned about instead, because that failure is not fatal.

## Build

```bash
npm install
npm run build      # -> dist/action.js
```

Upload `dist/action.js` to PlanDev
([docs](https://nasa-ammos.github.io/plandev-docs/sequencing/actions/)).
`npm run stringify` emits the bundle as a JSON string, for pasting into an API call instead.

## Try it

1. Upload `dist/action.js`, setting `externalUrl` to `https://api.github.com`.
2. Run it with `urlPath` = `repos/NASA-AMMOS/plandev`, `sleepMs` = `0`.
3. The JSON response is written back to the plan as `action-template-output`.

## Tests

```bash
npm test
```

[`tests/main.test.ts`](tests/main.test.ts) mocks `fetch` and the Actions API — no deployment or
network needed.
