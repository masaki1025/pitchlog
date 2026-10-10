# 両イメージは amd64 と arm64 を含むインデックス digest で固定する。
FROM node:24.16.0-bookworm-slim@sha256:2c87ef9bd3c6a3bd4b472b4bec2ce9d16354b0c574f736c476489d09f560a203 AS node_runtime

FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258 AS build
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
COPY backend/src ./src
RUN python -m pip install --no-cache-dir uv==0.11.21 \
    && uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258 AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/backend/.venv/bin:${PATH}"
WORKDIR /app/backend
RUN groupadd --system pitchlog && useradd --system --gid pitchlog --home-dir /app/backend pitchlog
COPY --from=build /app/backend/.venv ./.venv
COPY --from=node_runtime /usr/local/bin/node /usr/local/bin/node
COPY frontend/public/domain/pitchlog-domain.js /app/frontend/public/domain/pitchlog-domain.js
COPY frontend/public/domain/pitchlog-domain.json /app/frontend/public/domain/pitchlog-domain.json
USER pitchlog
EXPOSE 8000
CMD ["uvicorn", "pitchlog.main:app", "--host", "0.0.0.0", "--port", "8000"]
