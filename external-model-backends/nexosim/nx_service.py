#!/usr/bin/env python3
"""The NeXosim backend's Python half — a process to spawn, and nothing else.

The MODEL is `nx-model`, a Rust binary built against NeXosim. It speaks `adapter_core.ExecBackend`'s
stdio protocol: `describe` prints the declaration, `simulate` reads a normalized request and writes
profiles and spans, `validate` answers the semantic checks no schema can express. Everything that is
not about cryocoolers — HTTP, `?model=` resolution, defaults, the ValueSchema typechecker, the
identity hash, response validation — is `adapter_core`'s, exactly as it is for the three Python-side
adapters.

That is the whole point of running a Rust model this way, and this file is the evidence: a fourth
adapter, in a fourth language, is a binary and a `serve()` call. Not one line of Rust knows what an
identity hash is.

It did not start out this short. Building it found three gaps in `ExecBackend`, which had shipped
with no real user: it dropped `capabilities` when parsing a declaration, had no `validate` verb, and
had no way for a child to say "your request was wrong" rather than "I failed". All three are fixed
in the host now, so the workarounds that used to live here are gone. Finding them is what a first
real user is for.

Run:  python3 nx_service.py [port]      (stdlib only; needs nx-model on PATH or NX_MODEL_BIN)
"""
import os
import sys

# adapter_core sits one directory up in the repo and NEXT TO this file inside the container image.
# Appending rather than inserting keeps the co-located copy winning when there is one, so the image
# always runs the module it shipped with.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import adapter_core                                                            # noqa: E402

MODEL_KEY = "cryo"
DEFAULT_PORT = 5031

#: Where the Rust binary lives. The image puts it at /opt/adapter/nx-model; a checkout building with
#: `cargo build --release` puts it under target/, which is what the tests use.
MODEL_BIN = os.environ.get(
    "NX_MODEL_BIN",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "target", "release", "nx-model"))

#: Seconds before a run is abandoned. A NeXosim run of a day-long plan is milliseconds, so anything
#: that hits this is wedged rather than slow — and without a timeout a wedged child holds the
#: handler thread that spawned it until the adapter is restarted.
TIMEOUT_SECONDS = 120


def backend(command=None):
    """`validates=True` because `nx-model` implements the third verb. It is opt-in on purpose: a
    child that has never heard of `validate` would exit nonzero and turn every validation into a
    failure, so the host stays quiet unless a model says it can answer."""
    return adapter_core.ExecBackend(
        MODEL_KEY, [command or MODEL_BIN], timeout=TIMEOUT_SECONDS, validates=True)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    only = backend()
    declaration = only.declaration()
    adapter_core.serve(
        {MODEL_KEY: only}, port,
        banner="NeXosim %s model backend on :%d  (activity types: %d, resources: %d, id=%s)"
               % (MODEL_KEY, port, len(declaration.activity_types),
                  len(declaration.resource_types), declaration.identity_hash()))
