# aerie-fresh-action

This is an example action that performs flight rule checking on a sequence by making requests to an external FRESH service.

[FRESH](https://github.jpl.nasa.gov/397/mm-fresh) is a JPL internal (closed source) flight rule evaluation tool. If you are a JPL user, see the [FRESH docs and setup instructions](https://github.jpl.nasa.gov/397/mm-fresh/tree/develop/docs) for details (links accessible inside JPL network only). FRESH alone does not provide a web interface, so this action also depends on [Refresh](https://github.jpl.nasa.gov/Aerie/refresh), which provides a web server wrapper for FRESH.

External users won't be able to run FRESH, but this repo can still serve as a reference for building actions that make HTTP requests to remote services.


## Usage

1. Install dependencies for the `fresh-action` with `npm install`.
2. Build the action by running `npm run build`. This generates a bundled file at `dist/action.js`, which you can [upload to Aerie](https://nasa-ammos.github.io/aerie-docs/sequencing/actions/).
3. Fresh requires a valid command dictionary to be [uploaded to Aerie](https://nasa-ammos.github.io/aerie-docs/command-expansion/upload-command-dictionary/) before it can be invoked.
4. Next is setting up a webserver than can execute fresh, this will require you getting a copy of the `mm-fresh` python dependency from [Cody Hansen](mailto:cody.m.hansen@jpl.nasa.gov).
5. After writing a sequence and generating valid SeqJSON Fresh is ready to be run, run the action that was created after `dist/action.js` was uploaded and provide the sequence name.
