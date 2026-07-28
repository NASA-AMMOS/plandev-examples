# NeXosim external-model backend for PlanDev — container image.
#
# Build context is external-model-backends/, not nexosim/, so adapter_core.py — shared with the
# Python, Blackbird and Basilisk adapters — is reachable:
#   docker build -f nexosim/Dockerfile -t plandev/nexosim-adapter .
#
# The second stage is the honest part of this image. `ExecBackend` means the PYTHON host spawns the
# RUST model, so the runtime needs both, and a Rust model does NOT buy a `FROM scratch` image. The
# binary alone is a couple of megabytes and would run on scratch; the Python interpreter it is
# spawned by is the other fifty. That is still the smallest of the four adapters by a wide margin,
# and it is not 1 MB — see README.md, "What the image actually weighs".
FROM rust:1-alpine AS builder
# The musl target links statically by default, so the binary that comes out of here has no loader
# and no libc to find at runtime. musl-dev is what its build scripts need to compile against.
RUN apk add --no-cache musl-dev
WORKDIR /src
# Cargo.lock is committed and copied, and --locked makes cargo FAIL rather than quietly resolve a
# newer dependency: an adapter whose transitive versions drift between builds is one whose identity
# hash can move without anyone editing the model.
COPY nexosim/Cargo.toml nexosim/Cargo.lock ./
COPY nexosim/src ./src
RUN cargo build --release --locked

# Alpine, to match the builder's libc and keep the interpreter as small as one comes. adapter_core
# and nx_service are stdlib-only, so there is nothing to pip install.
FROM python:3.12-alpine
COPY --from=builder /src/target/release/nx-model /opt/adapter/nx-model
COPY adapter_core.py /opt/adapter/adapter_core.py
COPY nexosim/nx_service.py /opt/adapter/nx_service.py
ENV NX_MODEL_BIN=/opt/adapter/nx-model

# Fail at BUILD time if the binary cannot run or does not describe itself. Left to runtime, a
# mismatched libc or a stripped-away symbol surfaces as an empty 500 on the first /models poll, long
# after the image was declared good.
RUN /opt/adapter/nx-model describe > /dev/null

EXPOSE 5031
ENTRYPOINT ["python3", "/opt/adapter/nx_service.py", "5031"]
