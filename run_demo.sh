#!/usr/bin/env bash
# Starts the API and UI together so the whole demo is one command.
set -euo pipefail
trap 'kill 0' EXIT

uvicorn api.main:app --host 0.0.0.0 --port 8000 &
streamlit run ui/app.py --server.port 8501 &
wait
