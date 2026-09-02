# PlanDev Actions

**Actions** are server-side TypeScript that runs against a plan on demand — validating a
sequence, calling an external service, generating a file. They're a different PlanDev surface
from mission modeling: a model describes how the spacecraft behaves, an action does something
*with* a plan after a model exists.

See the [Actions docs](https://nasa-ammos.github.io/plandev-docs/sequencing/actions/) for the
platform side.

## The examples

| Directory | What it teaches |
|---|---|
| [`basic-action/`](basic-action/) | The shape of an action — typed parameters and settings, an HTTP call, reading and writing plan files. **Start here.** |
| [`ascii-art-action/`](ascii-art-action/) | Bundling an npm dependency and its data files into one uploadable file. |
| [`fresh-action/`](fresh-action/) | Calling an authenticated internal service. Reference only — the service it targets isn't public. |

## Build, test, lint

This directory is an npm workspace root — install once here, not per example. Node version is
pinned in [`.nvmrc`](.nvmrc).

```bash
cd examples/actions
npm ci
npm run build --workspaces     # each example -> <example>/dist/action.js
npm test --workspaces          # mocked; no PlanDev deployment needed
npm run lint --workspaces      # prettier --check
```

Each example's uploadable artifact is its own **`dist/action.js`**.
