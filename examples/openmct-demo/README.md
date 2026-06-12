# openmct-plandev — PlanDev inside OpenMCT (experimental demo)

> ⚠️ **Experimental demo — not a supported or production plugin.** It exists
> to *explore* how PlanDev data could surface in [NASA OpenMCT](https://github.com/nasa/openmct)
> and to make the close-the-U idea tangible. Expect rough edges; structure, naming,
> and behavior will change. Don't depend on it. The "actuals" are **synthesized**
> (predict + noise), not real telemetry, and auth/CORS/perf are demo-grade only.

A small, self-contained experiment that pulls **PlanDev** (Aerie) planning data into
OpenMCT, two ways:

- **Resources as telemetry** — each simulated resource profile becomes an OpenMCT
  telemetry object you can plot (numeric) or table (discrete/state).
- **The plan as an OpenMCT Plan object** — a simulation's activity spans become a
  Plan/Gantt object, so you see **planned activities alongside predicted resources**.

It reads PlanDev's Hasura GraphQL directly through a small, framework-agnostic
client. **No `plandev-ui` or backend changes** are required — everything lives on
the OpenMCT side.

It's a sketch of **Track B / Phase B** of the [PlanDev × OpenMCT integration memo](../../../claude-plans/plandev/plandev-openmct-integration.md)
(`~/code/claude-plans/plandev/plandev-openmct-integration.md`) — the "OpenMCT pulls
from PlanDev" direction — built here to learn from, not to ship. If the approach
proves out, the real version would be extracted and hardened separately.

### What this is / isn't

- **Is:** a throwaway-grade spike to validate the integration shape (object tree,
  telemetry mapping, plan-as-Gantt, predict-vs-actual overlay) against a live backend.
- **Isn't:** supported, secure, performance-tuned, or API-stable. Several behaviors
  are deliberately the simplest thing that works (see [Demo-grade simplifications](#demo-grade-simplifications)).

| Tree (Plans → Sims → Resources) | Ready-made Resource Plot | Activities as a Gantt |
|---|---|---|
| ![tree](docs/tree.png) | ![resource plot](docs/resource-plot.png) | ![gantt](docs/activities-gantt.png) |

## What you get

```
PlanDev                         ← tree root
└── <Plan name>                 ← each PlanDev plan
    └── Sim <id> · <status>      ← each simulation dataset
        ├── Resource Plot (first 15) ← ready-made Display Layout: first 15 numeric resources, each a tall plot frame
        ├── Predict vs Actual        ← close-the-U: Overlay Plots of predict vs synthesized actual
        ├── Activities (simulated)   ← Plan object → Gantt / Time-List / Time-Strip
        ├── <resource A>             ← telemetry (numeric → plot, enum/bool → state table)
        ├── <resource B>
        └── …
```

Each sim ships a **ready-made "Resource Plot"** — a view-only **Display Layout** with
the first 15 numeric resources, each in its own explicitly-sized plot frame (default
240px tall, tunable via `resourcePlotHeightPx`). Open it, set the conductor to the
sim's span, and scroll through tall, readable plots that all stay synced to the time
conductor. (Display Layout is OpenMCT's CSS-free way to give plots an explicit height;
the trade-off is a fixed canvas width — `resourcePlotWidthPx`, default 1000.) To
customize, build your own Overlay/Stacked Plot, Time Strip, or layout under *My Items*.

## Prerequisites

- **Node 18+**
- **A running PlanDev backend** reachable on this machine, with at least one plan
  that has a **completed simulation**. Defaults assume the standard local
  deployment:
  - Hasura GraphQL at `http://localhost:8080/v1/graphql`
  - Gateway at `http://localhost:9000` (with `AUTH_TYPE=none`, the default dev mode)

  If your backend lives elsewhere or uses auth, see [Configuration](#configuration).

## Quick start

```bash
cd examples/openmct-demo
npm install          # pulls openmct + build tooling
npm run build        # bundles the plugin → host/lib/openmct-plandev.js
npm start            # serves the host at http://localhost:8888
```

Open **http://localhost:8888** and:

1. Expand **PlanDev** in the left tree → pick a plan → pick a **`· success`** sim.
2. Click **Resource Plot (first 15)** → an instant dashboard of tall resource plots.
3. Or click an individual numeric resource (e.g. `array.powerProduction`,
   `BetaAngle_MARS`) → it opens as a **plot**; an enum/boolean resource
   (e.g. `adcsState`) → a **state table**.
4. Click **Activities (simulated)** → the sim's activities render as a **Gantt**.

The time conductor opens on the most recent plan's full span. **Zoom in** (drag the
conductor or set a narrower fixed range) to see individual activities in the Gantt —
at full-plan zoom, short activities are sub-pixel. (See `minActivityDurationMs` below
to make them visible at any zoom.)

`npm run dev` builds and starts in one step.

## Configuration

Two layers, both optional:

**Browser-side** — [`host/config.js`](host/config.js) sets `window.PLANDEV_CONFIG`:

| key | default | meaning |
|---|---|---|
| `graphqlUrl` | `/api/graphql` | Hasura endpoint (same-origin proxy path) |
| `loginUrl` | `/api/auth/login` | Gateway login endpoint |
| `username` | `openmct-demo` | login user (any value when `AUTH_TYPE=none`) |
| `role` | `aerie_admin` | Hasura role to assume |
| `namespace` | `plandev` | OpenMCT namespace for PlanDev objects |
| `minActivityDurationMs` | `0` | floor for zero-duration activity spans so they show as bars; e.g. `600000` (10 min) for a denser Gantt at full zoom |
| `resourcePlotHeightPx` | `240` | per-plot frame height in the "Resource Plot" Display Layout — the CSS-free way to set plot height |
| `resourcePlotWidthPx` | `1000` | per-plot frame width in the "Resource Plot" layout (fixed canvas) |

**Server-side** — [`host/server.mjs`](host/server.mjs) proxies the same-origin
`/api/*` paths to PlanDev (this sidesteps CORS — the browser only talks to the
host). Point it at a different backend with env vars:

```bash
PLANDEV_HASURA_URL=http://my-host:8080/v1/graphql \
PLANDEV_GATEWAY_LOGIN_URL=http://my-host:9000/auth/login \
PORT=8888 npm start
```

## How it works

The plugin (`plugin/src/`) registers four things with OpenMCT:

| File | Role |
|---|---|
| [`plandev-api.ts`](plugin/src/plandev-api.ts) | Framework-agnostic typed client over PlanDev's Hasura GraphQL + gateway login. The seed of the shared "AerieApi" (Phase 0 of the memo). |
| [`object-provider.ts`](plugin/src/object-provider.ts) | Resolves any tree node (Root / Plan / Sim / Resource / Plan-object) to an OpenMCT domain object. |
| [`composition-provider.ts`](plugin/src/composition-provider.ts) | Lists each container's children lazily: Root→Plans, Plan→Sims, Sim→Activities+Resources. |
| [`telemetry-provider.ts`](plugin/src/telemetry-provider.ts) | Historical telemetry: fetches a profile, samples it, windows + decimates to the request. |
| [`plan-object.ts`](plugin/src/plan-object.ts) | Builds the OpenMCT Plan body from a sim's activity spans, grouped by activity type. |
| [`sample.ts`](plugin/src/sample.ts) / [`metadata.ts`](plugin/src/metadata.ts) | Port of PlanDev's `sampleProfiles` + `ValueSchema`→OpenMCT metadata mapping. |

Resource values are anchored at the plan start time (matching how `plandev-ui`
samples internal-sim resources) and emitted as `{ utc: epochMs, value }` datums.

## Demo-grade simplifications

Things that are deliberately the simplest-thing-that-works, not production choices:

- **Actuals are synthesized**, not real telemetry — predict + drift/noise ([actuals.ts](plugin/src/actuals.ts)).
- **Historical only** — completed sims; no realtime streaming.
- **No decimation** — we return all points in the requested window. Fine because
  PlanDev profiles are change-point sampled (small); real dense telemetry would need
  min/max decimation, which belongs in a connector, not here.
- **The Plan object uses simulation _spans_** (real durations → accurate Gantt bars)
  rather than raw activity directives. Zero-duration events are point markers unless
  `minActivityDurationMs` is set.
- **Resource time is anchored to the plan start** (matching `plandev-ui`'s internal-sim
  path); sims starting at an offset from plan start aren't handled specially.
- **Displays are view-only** and provider-supplied; auth is gateway-login with a
  demo username; the host proxy is a minimal dev server.

## Close the U (predicts vs actuals)

Each sim has a **Predict vs Actual** folder with an Overlay Plot per resource,
each overlaying the **predicted** profile (from the PlanDev sim) against a
**synthesized "actual"** — the predict perturbed by a slow drift + small wiggle
([actuals.ts](plugin/src/actuals.ts)). The lines diverge, which is the
"close-the-U" signal a planner would replan against.

![predict vs actual](docs/close-the-u.png)

**Why synthesized, and why no separate server?** Real close-the-U needs actuals
that *correspond* to predicts — same channel, comparable time. The OpenMCT
tutorial's reference server emits unrelated random channels at realtime, so it
can't be overlaid meaningfully as-is, and a bespoke mission model matched to its
dictionary would be backwards. Instead we derive actuals from the sim itself, on
the same channels, over the plan's own time span (a **static replay**). For static
replay we implement the tutorial's **historical-provider pattern**
(`request(obj, {start, end}) → datums`) directly in the plugin — no extra server
to run. The actuals perturbation is a pure function of `(timestamp, resource)`, so
the actual line is stable across pans/zooms.

The **live** variant — streaming actuals over a WebSocket, shifted to "now" — is
where the tutorial's realtime server comes in; see [Next steps](#next-steps-from-the-memo).

## Troubleshooting

- **Resources show no data / "nothing appears."** The time conductor must overlap
  the simulation's time range. A resource opened with the conductor outside the
  sim's span plots empty — that's expected, not an error. Set the conductor to the
  sim's range (the demo auto-opens on the latest plan's span; older plans/sims may
  need you to adjust it).
- **A Sim folder with hundreds of resources is slow to fully populate.** The API
  client caps concurrent GraphQL requests (default 6, matching the browser's
  per-origin connection limit) so a large folder loads **progressively** instead of
  flooding the browser (`net::ERR_INSUFFICIENT_RESOURCES`). Profiles are cached, so
  it's a one-time cost per resource.
- **Console warnings from the Plan view in narrow frames** (`<svg> attribute width:
  negative`, `reading 'ticks'`, `xScale is not a function`). These come from
  OpenMCT's own Plan view (`PlanView.vue` computes `clientWidth - 200`), which throws
  when rendered in a container narrower than ~200px. Open the Activities object
  full-size (or widen its frame) and it renders correctly; the warnings are upstream
  and cosmetic.

## Next steps (from the memo)

- **Live close-the-U**: stream actuals over a WebSocket (the OpenMCT tutorial's
  realtime-server pattern), shifting both predict and actual to "now", so the actual
  ticks in and diverges live. Builds on the static `Predict vs Actual` plots above.
- A bundled **demo plan + minimal mission model** so the example is runnable without
  an existing PlanDev plan.
- Extract `plandev-api.ts` into the shared `@plandev/api` package once it stabilizes.
