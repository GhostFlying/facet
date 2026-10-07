# Complete sync entry and granular verification

Date: 2026-10-07. Base: `12953c2`.
Scope of this unit: documentation and existing granular-command verification,
not implementation or authorization of a new live historical backfill.

## User decision

The product must offer one complete CLI sync entry implemented entirely through
the same operations as its granular commands. Users need not manually run preview
then start. The proposed name is `facet sync [--once]`; it is not implemented.
The user requests continued granular-command testing during current validation.

An intentional complete sync invocation selects current enabled rules and the
default fixed six-month discovery window, automatically prepares the scoped
preview/start operations and runs backfill plus History. Separate init/setup,
preview, status and ordinary run/restart remain non-expanding. Rules added/action
labels observed during continuous operation retain prospective behavior; a new
intentional complete-sync scope can include their history. No second sync engine,
shell-command chain, new receipt broker or additional permission is introduced.

## Files and minimum change

- `AGENTS.md`, product/CLI/Gmail specifications: distinguish an intentional
  complete sync operation from setup/startup and standalone preview. Preserve
  granular commands, zero-write preview, configured scope and all safety gates.
- Project/execution plans and progress: update the user journey and acceptance
  in place, without moving M1-M6 or removing existing gates.
- Development status: record that nine live mappings came from three future-rule
  threads; the earlier initial epoch sealed zero rules. Current start rejects
  a second initial epoch; historical expansion and complete sync are still gaps.

## Verification and authority

Use independent plan/document review, whitespace/link/consistency checks and the
repository safety scanner; no full source suite/image rebuild for prose-only work.
Use the unchanged non-root image and real configuration/state for standalone
`backfill preview` and `backfill status`, with external networking disabled where
supported. Record allowlisted aggregate results; no real IDs/credentials in Git.
Preview may persist its metadata receipt but must not insert or create an epoch.

Do not start another live cycle, historical epoch, old-unknown retry, cleanup,
source mutation, scope expansion or daemon. A historical preview/start/runtime
implementation must have its own bounded plan/review before coding; actual bulk
copying needs concrete rule/window authorization and the existing H0/gap gates.
Never clear completed discovery, reset DB/cursor, revive stopped threads or reopen
historic attention to manufacture a successful historical-backfill test.
