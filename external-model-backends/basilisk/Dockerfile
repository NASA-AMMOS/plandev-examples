# Basilisk external-model backend for PlanDev — container image.
#
# Basilisk (AVS Lab, University of Colorado; ISC) ships prebuilt abi3 wheels, so unlike the
# Blackbird image there is nothing to compile: no builder stage, no vendored jars, no toolchain.
#
# Build context is external-model-backends/, not basilisk/, so adapter_core.py -- shared with the
# Python and Blackbird adapters -- is reachable:
#   docker build -f basilisk/Dockerfile -t plandev/basilisk-adapter .
FROM python:3.12-slim

# SPICE kernels are NOT in the wheel. Basilisk fetches them from naif.jpl.nasa.gov the first time a
# spice interface is created -- four files, ~128 MB, almost all of it de430.bsp. Left to runtime that
# is a cold first simulate that hangs (or fails outright) on any cluster without egress, so bake them
# in. BSK_SUPPORT_DATA_CACHE pins where pooch looks; it has to be set at RUNTIME as well as at build
# time, hence ENV rather than a build ARG.
ENV BSK_SUPPORT_DATA_CACHE=/opt/bsk-data

# The four kernels createSpiceInterface() loads by default. Fetching exactly these rather than
# running Basilisk's own `bskLargeData` pre-fetch, which pulls all 45 registry entries -- albedo
# grids, atmosphere tables, a sky-brightness FITS -- none of which this model touches.
RUN pip install --no-cache-dir "bsk==2.11.0" "numpy>=1.26" \
 && python3 -c "\
from Basilisk.utilities.supportDataTools.dataFetcher import fetch_support_data;\
[fetch_support_data('supportData/EphemerisData/' + k) for k in \
 ('naif0012.tls', 'pck00010.tpc', 'de-403-masses.tpc', 'de430.bsp')]" \
 && du -sh /opt/bsk-data

COPY adapter_core.py /opt/adapter/adapter_core.py
COPY basilisk/bsk_model.py /opt/adapter/bsk_model.py
COPY basilisk/bsk_service.py /opt/adapter/bsk_service.py

# Importing Basilisk costs ~1.5 s, once per process. Doing it at image build turns the first
# simulate from "slow for no visible reason" into a cost paid before the server ever answers.
RUN python3 -c "import sys; sys.path.insert(0, '/opt/adapter'); import bsk_model" >/dev/null

EXPOSE 5021
ENTRYPOINT ["python3", "/opt/adapter/bsk_service.py", "5021"]
