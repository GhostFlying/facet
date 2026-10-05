#!/bin/sh

set -eu

image=${FACET_IMAGE:-}
if printf '%s\n' "$image" | grep -Eq '^ghcr\.io/ghostflying/facet:([0-9a-f]{40})$|^ghcr\.io/ghostflying/facet@sha256:[0-9a-f]{64}$'; then
    exit 0
fi
printf '%s\n' 'FACET_IMAGE must be ghcr.io/ghostflying/facet:<40-hex-commit> or @sha256:<64-hex-digest>' >&2
exit 2
