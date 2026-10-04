# Read-only Dashboard and Compose alpha

Date: 2026-10-04. Status: approved for implementation after independent review. Base: `27b2047`.

## Goal

Expose the existing typed public status models through a single-process,
read-only HTTP server and provide a non-root Compose smoke fixture that runs
the same image shape. This unit proves the HTTP/privacy/container boundary; it
does not claim that aggregate collectors, live Gmail, or production deployment
verification are complete. The server accepts a typed snapshot provider so the
existing runtime can be connected without making GET perform provider I/O.

## Scope

- `src/facet/web/server.py`: a single-threaded-owner HTTP server and immutable
  per-request `SnapshotProvider` interface. The provider reads only an
  in-memory or already-cached snapshot; GET never triggers provider, Gmail,
  DB, or filesystem I/O. The immutable static page is loaded once while the
  server starts, before requests are served. The default provider returns explicit
  unavailable/unknown envelopes. Snapshot objects are replaced atomically by
  the eventual runtime owner; the HTTP handler never mutates them and never
  runs sync work.
- `src/facet/web/static/index.html`: a bundled aggregate-only page with no
  account, rule, message, ID, or error-detail fields.
- `src/facet/cli/bootstrap.py`: `facet web --host HOST --port PORT`, defaulting
  to `127.0.0.1:8080`; it imports the server lazily and owns the process.
- `Dockerfile`, `.dockerignore`, `docker-compose.yml`: a non-root UID 10001
  image, `/var/lib/facet` volume ownership, one `facet web --host 0.0.0.0
  --port 8080` process, read-only root filesystem with `/tmp` tmpfs, and a
  healthcheck against `/healthz`. Compose publishes only host
  `127.0.0.1:8080:8080`; the CLI default remains `127.0.0.1:8080` outside
  Compose. This is a smoke fixture, not a claim of production state
  initialization or live sync deployment.
- HTTP errors are fixed JSON (`{"error":"not_found"}` or
  `{"error":"method_not_allowed"}`) with no echoed path/query/provider text;
  `BaseHTTPRequestHandler` request logging and exception output are replaced
  with a silent handler. Unknown query strings are rejected. `/healthz` is
  200 with `{"status":"ok"}` when the process serves; `/readyz` is 200 only
  when the provider is readable and otherwise 503 with `{"status":"unavailable"}`.
  API responses preserve the envelope freshness and explicit unknown values.

## Acceptance

Focused tests prove all routes, stale/unavailable semantics, unknown metrics,
method/path/query rejection, fixed error bodies, no handler/provider mutation
or external I/O, silenced stderr, and absence of mail/account/token/path/error
sentinels from every HTTP response and static page. A subprocess smoke test
proves the CLI binds the documented default, serves `/healthz`, and exits
cleanly; a Docker smoke (when the daemon is available) proves UID 10001,
container HTTP reachability through host loopback publication, the volume
mount, and one web process. Existing offline tests, Ruff, safety,
and package build pass. This unit does not claim live dashboard counts,
Compose deployment, browser acceptance, or GHCR publication; those remain
later gates once aggregate collectors and the approved Actions workflow are
ready. No real Gmail or account selection is performed.

## Stop gates and external boundary

Do not add a collector that invents counts, read raw Gmail, or widen OAuth
scope in this unit. If the runtime cannot yet supply typed aggregate snapshots,
the fixture remains explicitly unavailable and the missing consumer is recorded
in `docs/development-status.md`; that is an incomplete dashboard gate, not a
successful live dashboard claim. No host deployment, image push, release, or
mailbox mutation is authorized here.
