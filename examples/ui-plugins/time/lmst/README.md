# Perseverance LMST Time Plugin Example

This is a demonstration of a more complex time plugin for the PlanDev UI. This time plugin implements Perseverance LMST
time as the primary time for the PlanDev UI as well as additional time formats in SCLK and UTC. This plugin is built 
using Typescript and bundled using Rollup.js to output a `time-plugin.js` file along with some other associated files
that the plugin will dynamically fetch at runtime. Mars time conversions are performed using [TimeCraftJS](https://github.com/NASA-AMMOS/timecraftjs) 
which provides an interface to a version of NAIF CSPICE that is compiled to Javascript using Emscripten. This plugin and
the provided SPICE kernels are specific to the Perseverance rover so it is recommended that users make a copy of this
plugin and customize it for their own needs.

## Build

From this directory:

```bash
npm install
npm run build
```

The generated `build/` directory contains:

- `time-plugin.js`
- the JavaScript modules used by TimeCraftJS
- the required SPICE kernels under `build/kernels/`

## Install in PlanDev UI

PlanDev loads the time plugin from `/resources/time-plugin.js`. Copy the complete build output into the UI’s static resources directory:

```bash
plandev_ui_dir=/path/to/plandev-ui

mkdir -p "$plandev_ui_dir/static/resources"
cp -R build/. "$plandev_ui_dir/static/resources/"
```

Enable the plugin in the PlanDev UI environment:

```text
PUBLIC_TIME_PLUGIN_ENABLED=true
```

Then rebuild the PlanDev UI and restart or redeploy it.

The deployed files must be available at these paths:

```text
/resources/time-plugin.js
/resources/asm_full-*.js
/resources/asm_lite-*.js
/resources/kernels/m2020_lmst_ops210303_v1.tsc
/resources/kernels/m2020.tls
/resources/kernels/m2020.tsc
```

## Verify

When you open a plan with this plugin installed, you should see:

- LMST as the primary timeline time
- SCLK and UTC appear as additional time formats

If initialization fails, check the browser console and Network panel for missing files under `/resources/`.