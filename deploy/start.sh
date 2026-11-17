#!/bin/sh
# Render gives one container one public port, so both processes start here.
# The API listens on 127.0.0.1 only: the UI in this container can reach it, the internet can't.
set -e

uvicorn app.main:app --host 127.0.0.1 --port 8000 &

# exec: Streamlit replaces this shell, so it receives Render's stop signal directly
exec python -m streamlit run ui/app.py \
  --server.address 0.0.0.0 \
  --server.port "${PORT:-8501}" \
  --server.headless true
