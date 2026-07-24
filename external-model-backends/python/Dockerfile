# Pure-Python external-model backend for PlanDev — container image.
#
# The adapter is stdlib-only (no pip install), so this is a single, tiny stage.
# It serves a toy spacecraft battery model over the PlanDev external-model wire contract.
FROM python:3.12-slim

WORKDIR /opt/adapter
COPY py_model_server.py .

EXPOSE 5002
ENTRYPOINT ["python3", "py_model_server.py", "5002"]
