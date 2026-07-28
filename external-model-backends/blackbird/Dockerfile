# Blackbird external-model backend for PlanDev — container image.
#
# Two stages:
#   1. builder  — builds jplTime + Blackbird from source (Maven, JDK 21) and compiles the
#                 demo `powermodel` adaptation against them.
#   2. runtime  — a slim JRE + Python 3 that runs bb_service.py (the multi-model HTTP backend).
#
# Blackbird and jplTime are Apache-2.0 and cloned at build time (NOT vendored in this repo).
# JNISpice is a *compile-time* dependency of jpl_time and is NOT on Maven Central; you must
# provide its jar in ./vendor (see vendor/README.md). The native SPICE library is only needed at
# RUNTIME if your Blackbird model actually calls the Spice class (the demo powermodel does not).

# ---------- Stage 1: build Blackbird + jplTime + the demo power model ----------
FROM maven:3.9-eclipse-temurin-21 AS builder

# JNISpice jar. Place it under ./vendor before building.
#   JNISPICE_JAR     — the FILENAME you dropped in ./vendor. Override this if you have a
#                      different SPICE toolkit release (e.g. JNISpice-N0067.jar).
#   JNISPICE_VERSION — the Maven COORDINATE jplTime's pom depends on, NOT a description of your
#                      jar. Whatever file you supply is installed under this coordinate so
#                      jplTime resolves it. Do NOT set it to your jar's release name: jplTime
#                      2025-10a hard-requires v2022-05, and the build fails with
#                      "Could not find artifact gov.nasa.jpl.spice:jnispice:jar:<yours>".
#                      Change it only if jplTime changes the dependency.
ARG JNISPICE_JAR=JNISpice-v2022-05.jar
ARG JNISPICE_VERSION=v2022-05
COPY blackbird/vendor/${JNISPICE_JAR} /tmp/jnispice.jar
RUN mvn -q -B install:install-file \
      -Dfile=/tmp/jnispice.jar \
      -DgroupId=gov.nasa.jpl.spice -DartifactId=jnispice -Dversion=${JNISPICE_VERSION} -Dpackaging=jar

WORKDIR /src

# jplTime — Blackbird pins gov.nasa.jpl:jpl_time:2025-10a (repo default differs, so set it).
RUN git clone --depth 1 https://github.com/nasa-jpl/jplTime.git \
 && cd jplTime \
 && mvn -q -B versions:set -DnewVersion=2025-10a \
 && mvn -q -B -DskipTests install

# Blackbird itself. `target/classes` is the framework + its bundled example adaptation; deps go to /out/lib.
RUN git clone --depth 1 https://github.com/nasa-jpl/Blackbird.git \
 && cd Blackbird \
 && mvn -q -B -DskipTests package \
 && mvn -q -B dependency:copy-dependencies -DoutputDirectory=/out/lib \
 && cp -r target/classes /out/classes

# Compile the demo power model against Blackbird core + jplTime (+ deps).
# Java expands the trailing /* classpath wildcard itself.
COPY blackbird/powermodel/src /src/powermodel/src
RUN mkdir -p /out/powermodel \
 && javac -parameters -cp "/out/classes:/out/lib/*" -d /out/powermodel \
      $(find /src/powermodel/src -name '*.java')

# Accessor for the adaptation's simulation configuration. Blackbird can enumerate, type and SET its
# parameters, but has no command that prints them -- CREATE_DICTIONARY emits activities only. Built into
# /out/tools so it can be run against any adaptation's classpath.
COPY blackbird/tools/BbParams.java /src/tools/BbParams.java
RUN mkdir -p /out/tools \
 && javac -cp "/out/classes:/out/lib/*" -d /out/tools /src/tools/BbParams.java

# Conformance probe: declares one resource of every Blackbird type so adapter coverage is testable.
COPY blackbird/covermodel/src /src/covermodel/src
RUN mkdir -p /out/covermodel \
 && javac -parameters -cp "/out/classes:/out/lib/*" -d /out/covermodel \
      $(find /src/covermodel/src -name '*.java')

# ---------- Stage 2: runtime ----------
FROM eclipse-temurin:21-jre-jammy
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 \
 && rm -rf /var/lib/apt/lists/*

COPY --from=builder /out /opt/blackbird
# Build context is external-model-backends/, not blackbird/, so adapter_core.py -- shared with the
# Python adapter -- is reachable. Copied next to the service, where its sys.path shim looks first.
COPY adapter_core.py /opt/adapter/adapter_core.py
COPY blackbird/bb_service.py /opt/adapter/bb_service.py
# bb_import began as an offline CLI and is now also reached over HTTP by POST /import-plan, so it
# has to be in the image rather than only in the repo.
COPY blackbird/bb_import.py /opt/adapter/bb_import.py

ENV BLACKBIRD_MAIN="gov.nasa.jpl.Blackbird"
# BB_MODELS maps each model key to a classpath = Blackbird core + its deps + one adaptation.
# Here we serve the demo power model. NOTE: /opt/blackbird/classes also contains Blackbird's
# bundled example activities, so this model exposes those too — see README.md ("Caveat").
ENV BB_MODELS='{"powermodel":"/opt/blackbird/classes:/opt/blackbird/lib/*:/opt/blackbird/powermodel","covermodel":"/opt/blackbird/classes:/opt/blackbird/lib/*:/opt/blackbird/covermodel"}'
# If your model uses SPICE, copy the native lib (libJNISpice.so) into the image and point here:
# ENV JPLTIME_LIB="/opt/blackbird/nativelib"

EXPOSE 5011
ENTRYPOINT ["python3", "/opt/adapter/bb_service.py", "5011"]
