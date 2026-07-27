# Pure-Python external-model backend for PlanDev — container image.
#
# The adapter is stdlib-only (no pip install), so this is a single, tiny stage.
# It serves a toy spacecraft battery model over the PlanDev external-model wire contract.
FROM python:3.12-slim

WORKDIR /opt/adapter
# Build context is external-model-backends/, not python/, so that adapter_core.py -- shared with the
# Blackbird adapter -- is reachable. It is copied NEXT TO the server, which is where the server's
# sys.path shim looks first, so the image always runs the core it shipped with.
COPY adapter_core.py .
COPY python/py_model_server.py .

EXPOSE 5002
ENTRYPOINT ["python3", "py_model_server.py", "5002"]
