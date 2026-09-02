# plandev-fresh-action

**What this teaches:** calling an authenticated internal HTTP service from an Action — pulling a
sequence and its command dictionary out of the plan, POSTing them, and handling the response.

This example is modeled on flight-rule checking. The service it calls (FRESH, a JPL-internal
flight-rule evaluator behind a small web wrapper) isn't publicly available, so **read and adapt
this one rather than expecting to run it end to end.**

What's reusable regardless of that service:

- `actionsAPI.readFile` to pull the named sequence from the plan's files
- `actionsAPI.readParcel` / `readCommandDictionary` / `readDictionaryFile` to fetch the command
  dictionary the sequence was written against
- a `POST` with a JSON body, and an explicit `result.ok` check — `fetch` resolves normally on an
  HTTP 500, so without it a failed evaluation would be reported as `SUCCESS`

## Adapting it

Point the `refreshUrl` setting at any service accepting `{ sequence, command_dictionary }` as
JSON, and adjust `RefreshResponse` in [`src/models/refresh.ts`](src/models/refresh.ts) to match
what yours returns.

## Build

```bash
npm install
npm run build      # -> dist/action.js
```

Upload `dist/action.js`
([docs](https://nasa-ammos.github.io/plandev-docs/sequencing/actions/)), then:

1. Upload a command dictionary to PlanDev
   ([docs](https://nasa-ammos.github.io/plandev-docs/command-expansion/upload-command-dictionary/)).
2. Set the `refreshUrl` setting to your service.
3. Run the action with `sequenceName` set to a sequence with valid SeqJSON.

## Tests

No tests yet — `npm test` is a placeholder. See
[`../basic-action/tests/`](../basic-action/tests/) for the pattern to mock `fetch` and the
Actions API.
