# Action-label credential TOCTOU stat fix

Date: 2026-10-06. Revision: 1. Status: implementation candidate.

## Scope

Fix the v2-to-v3 action-label backup preflight so reading a managed credential
file does not fail merely because the read updates atime. In
`StateOwner.ensure_action_label_schema`, retain no-follow, owner, mode, regular
file, link-count, size, and stable identity checks, but compare only
`st_dev`, `st_ino`, `st_mode`, `st_uid`, `st_gid`, `st_nlink`, and `st_size`
between the pre-read descriptor and post-read path/stat observations.

Add synthetic regression coverage proving that a first action-label set can
complete v2-to-v3 migration when atime changes, while preserving existing
replacement, size, symlink, owner/mode, and backup-failure refusal checks.

## Acceptance

- A trusted v2 fixture with a readable credential file upgrades to exact v3
  despite an atime-only stat difference and preserves the backup bundle.
- Synthetic replacement, size, symlink, owner/mode, and backup-fault cases
  remain fail-closed before DDL or mapping mutation.
- Focused action-label tests, full offline pytest, Ruff/format, and repository
  safety pass.
- No real credentials, Gmail/OAuth calls, deployment, or live state volume is
  used.

## Stop gates

Stop if the safe identity/mode/ownership/size fields cannot be compared without
weakening no-follow or race protections, or if the fix requires broad
permission changes, credential copying outside the existing synthetic backup
contract, or live validation.
