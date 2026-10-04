FROM python:3.12-slim-bookworm@sha256:54c85f3c47607a77f32adec749d3c81d1348bf25833671f512b26a9b6d778cb3

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN pip install --no-cache-dir uv==0.12.2 \
    && uv sync --locked --no-dev \
    && addgroup --system --gid 10001 facet \
    && adduser --system --uid 10001 --gid 10001 --no-create-home facet \
    && mkdir -p /var/lib/facet \
    && chown 10001:10001 /var/lib/facet

USER 10001:10001
EXPOSE 8080
VOLUME ["/var/lib/facet"]
ENTRYPOINT ["facet"]
CMD ["web", "--host", "0.0.0.0", "--port", "8080"]
