# Parakeet external-model backend for PlanDev — container image.
#
# Parakeet is a Kotlin simulation engine whose tasks are COROUTINES rather than threads, which is
# what lets it save and restore a running simulation with a stated algebraic guarantee. This adapter
# exists to run it against real PlanDev plans without touching merlin — the external-model contract
# used as an evaluation harness for a candidate engine.
#
# Build context is external-model-backends/, so adapter_core.py is reachable:
#   docker build -f parakeet/Dockerfile -t plandev/parakeet-adapter .

# ---------- Stage 1: build the model binary ----------
FROM gradle:8.14-jdk21 AS builder

# Parakeet has no releases and no published Maven artifact, so it is cloned and PINNED to a commit.
# A floating clone would mean the identity hash merlin attests could change with someone else's
# push, which is the exact drift the attestation exists to detect.
ARG PARAKEET_REPO=https://github.com/DavidLegg/Parakeet.git
ARG PARAKEET_SHA=b2ec42f60fa73b22d1cc0ce93d36551e46247d35

WORKDIR /src
RUN git init parakeet-src \
 && cd parakeet-src \
 && git remote add origin ${PARAKEET_REPO} \
 && git fetch --depth 1 origin ${PARAKEET_SHA} \
 && git checkout FETCH_HEAD

COPY parakeet/settings.gradle.kts parakeet/build.gradle.kts /src/
COPY parakeet/src /src/src

# `installDist` rather than a fat jar: Parakeet pulls in kotlinx-serialization, kotlinx-datetime,
# coroutines and commons-math3, and shading them would be work in exchange for nothing -- the image
# is not size-constrained the way the Rust one was, and a start script with a plain classpath is
# easier to debug than a merged jar.
RUN gradle --no-daemon installDist

# ---------- Stage 2: runtime ----------
FROM eclipse-temurin:21-jre-jammy
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 \
 && rm -rf /var/lib/apt/lists/*

COPY --from=builder /src/build/install/parakeet-adapter /opt/parakeet
COPY adapter_core.py /opt/adapter/adapter_core.py
COPY parakeet/pk_service.py /opt/adapter/pk_service.py

ENV PARAKEET_MODEL_BIN=/opt/parakeet/bin/parakeet-adapter

EXPOSE 5041
ENTRYPOINT ["python3", "/opt/adapter/pk_service.py", "5041"]
