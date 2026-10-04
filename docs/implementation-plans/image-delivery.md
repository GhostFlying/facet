# GHCR image delivery

Date: 2026-10-04. Status: approved for implementation after independent review. Base:
`89774c7fcacc0cb2ad0a10a34507300ee3352a07`.

Frozen inputs for this revision (verified from upstream tag refs and the
Docker Hub tag manifest on 2026-10-04):

- Base manifest: `python:3.12-slim-bookworm@sha256:54c85f3c47607a77f32adec749d3c81d1348bf25833671f512b26a9b6d778cb3`.
- `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1`.
- `astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7`.
- `docker/setup-qemu-action@29109295f81e9208d7d86ff1c6c12d2833863392`.
- `docker/setup-buildx-action@f87e5991a6d7451dcb8d9637bfbc97413f497069`.
- `docker/login-action@dbcb813823bdd20940b903addbd779551569679f`.
- `docker/metadata-action@dc802804100637a589fabce1cb79ff13a1411302`.
- `docker/build-push-action@c3c9e263c25d99ce0380d002d59b67737d91b0dc`.

## Goal

Make the already-merged Compose image reproducible and publish it to the
authorized public `ghcr.io/ghostflying/facet` registry only from `main`.
Pull-request builds remain credential-free and never publish. This unit does
not deploy a host, create a release tag, run Gmail, or change the dashboard's
read-only contract.

## Scope and files

- Pin `Dockerfile` to the current multi-architecture
  `python:3.12-slim-bookworm` manifest digest; retain non-root UID 10001,
  bundled static assets, and the single `facet web` process.
- Add `.github/workflows/image.yml` using immutable commit-pinned official
  Docker actions: checkout, setup-qemu, setup-buildx, metadata, login, and
  build-push. The build targets `linux/amd64,linux/arm64`, emits SBOM and
  provenance, and publishes only
  `ghcr.io/ghostflying/facet:${{ github.sha }}` on a `push` event whose ref is
  exactly `refs/heads/main`. Buildx's resulting digest is recorded as evidence,
  not used as a second tag. No `latest`, branch, PR, or other mutable tag is
  created. PRs build the same platforms with `push: false` and no registry
  login. The publish job alone grants `packages: write`, `id-token: write`, and
  `attestations: write`; the build/PR job is limited to `contents: read`.
  `workflow_dispatch` may run the credential-free build, but its publish job
  remains disabled unless the event is a push to main.
- Add a small workflow validation test/documentation check that rejects
  mutable action refs, missing platform targets, missing SHA tag, PR push, or
  unscoped write permissions. Do not add a Node runtime or a second sync
  process.
- Update `docs/development-status.md` with the exact candidate/main CI and
  publish-boundary evidence. Anonymous pull and multi-architecture manifest
  verification remain required after the first successful publication; no
  publication is performed by this local unit.

## Acceptance and stop gates

1. `docker compose config --quiet`, repository safety, Ruff/format, and all
   offline tests pass.
2. A static workflow test proves every action ref equals one of the frozen
   SHAs above, the QEMU/multi-platform settings are present, no mutable image
   tag is configured, and the publish condition is a push to `main`; it also
   checks job-level permissions and that PR jobs have no registry login or
   write permission. No token, Gmail data, or private state is in the workflow.
3. GitHub Actions PR CI builds both requested platforms without publishing.
   After merge, main CI publishes only `ghcr.io/ghostflying/facet:<commit-sha>`
   with SBOM/provenance; the digest and anonymous pull/multi-arch checks are
   recorded separately.
4. If Docker Hub or GHCR is unreachable, record that as an external evidence
   gap and do not claim image publication. No retry may broaden registry,
   permission, or deployment scope.
