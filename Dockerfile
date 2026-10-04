FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN pip install --no-cache-dir . \
    && addgroup --system --gid 10001 facet \
    && adduser --system --uid 10001 --gid 10001 --no-create-home facet \
    && mkdir -p /var/lib/facet \
    && chown 10001:10001 /var/lib/facet

USER 10001:10001
EXPOSE 8080
VOLUME ["/var/lib/facet"]
ENTRYPOINT ["facet"]
CMD ["web", "--host", "0.0.0.0", "--port", "8080"]
