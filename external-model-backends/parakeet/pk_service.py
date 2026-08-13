#!/usr/bin/env python3
"""The Parakeet backend's Python half — a process to spawn, and nothing else.

The MODEL is a Kotlin program built against Parakeet, a simulation engine whose tasks are
coroutines rather than threads. It speaks `adapter_core.ExecBackend`'s stdio protocol: `describe`
prints the declaration, `simulate` reads a normalized request and writes profiles and spans.

Fifth backend, third language through `ExecBackend`, and the shortest adapter yet — which is the
only claim this file makes. HTTP, `?model=` resolution, defaults, the ValueSchema typechecker, the
identity hash, response validation and the sample-to-segment conversion are all `adapter_core`'s.

Why Parakeet is here at all: it is a candidate REPLACEMENT for merlin's own engine, not a foreign
simulator someone needs to plan with. Its distinguishing property is rigorous save/restore, which
is exactly what makes scheduling against an external model affordable — a scheduler that can
restore a checkpoint does not pay a full re-simulation per placement. Running it through this
contract is the cheapest way to try it against real plans without touching merlin at all.

Run:  python3 pk_service.py [port]   (stdlib only; needs the model on PARAKEET_MODEL_BIN)
"""
import os
import sys

# adapter_core sits one directory up in the repo and NEXT TO this file inside the container image.
# Appending rather than inserting keeps the co-located copy winning when there is one, so the image
# always runs the module it shipped with.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import adapter_core                                                            # noqa: E402

MODEL_KEY = "recorder"
DEFAULT_PORT = 5041

#: The Kotlin program. The image installs a start script; a checkout building with
#: `gradle installDist` puts one under build/install/, which is what the tests use.
MODEL_BIN = os.environ.get(
    "PARAKEET_MODEL_BIN",
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "build", "install", "parakeet-adapter", "bin", "parakeet-adapter"))

#: Seconds before a run is abandoned. Generous because a JVM starts per request -- the child is
#: spawned, runs, and exits, so cold start is paid every time. Anything that reaches this is wedged
#: rather than slow, and without it a wedged child holds the handler thread until a restart.
TIMEOUT_SECONDS = 180


def backend(command=None):
    """No subclass and no protocol code.

    `validates=False`: the model implements `describe` and `simulate` only. The host's generic
    typecheck is all it gets, which is correct -- there is no semantic check about a recorder that
    a ValueSchema cannot already express, and claiming otherwise would have every validation
    shell out to a JVM for nothing.
    """
    return adapter_core.ExecBackend(
        MODEL_KEY, [command or MODEL_BIN], timeout=TIMEOUT_SECONDS)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    only = backend()
    declaration = only.declaration()
    adapter_core.serve(
        {MODEL_KEY: only}, port,
        banner="Parakeet %s model backend on :%d  (activity types: %d, resources: %d, id=%s)"
               % (MODEL_KEY, port, len(declaration.activity_types),
                  len(declaration.resource_types), declaration.identity_hash()))
