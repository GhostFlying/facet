# Target agent outbound contract correction

Base: `36a2926e7fafd585160200c3bb986bed0a7e199c`. User decision: target remains
dedicated, but authorized external agents may create sent mail/drafts using the
source identity; replies go to source. Recipient-derived automatic rules are
recorded as future work, not Phase 1. Root owns documentation; independent Sol
review covers the revised contract and actual candidate.

## Bounded delivery

Update AGENTS and canonical product/project/execution/Gmail/CLI/setup documents,
Dashboard counting, cleanup warning and current status. This is documentation
only: current setup probes profiles, and a complete target unmanaged-content
enforcement/audit is not implemented. Do not claim the new classification runs.
No source, dependency, schema, OAuth or Gmail changes; no deployment/live action.

## Required semantics

- Source remains the truth for projected content. Facet is the projection writer,
  not the only mailbox writer; its DB/process single-writer rule is unchanged.
- External agents may send/create drafts in target with From using source; agent
  send-as/reply routing and separate sending credentials belong to the agent/Gmail
  integration, not Facet. Facet never sends, provisions send-as or expands scope.
- Unmanaged SENT/DRAFT items with source From are permitted, not blocking errors.
  Matching From alone or arbitrary unmapped mail is not enough. Existing managed
  mappings/owned insert outcomes retain their identity regardless of labels.
- These outbound items are not projection successes, mapped/adopted recovery
  candidates or new rule inputs. Other unexpected/unmanaged content and binding
  failures remain blocked/report-only; nothing is automatically deleted.
- Replies enter source and use normal source rules/History. Untracked replies
  need current admission; receiving a reply does not itself authorize disclosure.
- Recipient-to-rule learning is deferred, with no new To/Cc persistence or scope.
  Explicit target-cleanup can still delete approved outbound/draft IDs; its old
  approval is not authority for a new preview or automatic cleanup.

## Acceptance

Independent plan and candidate documentation reviews; diff/consistency and
staged/tracked safety checks. No repeated local full suite or image build for a
docs-only correction; any published PR retains required CI. Record runtime
classification and controlled live verification as uncompleted existing gates.
Future target checks must cover managed and in-flight ownership, allowed outbound,
wrong/ambiguous From, unexpected incoming/imports, recovery exclusion and unchanged
success counts. Avoid reinterpreting old live cleanup evidence as a new operation.
Stop if a change would implement sending, silently grow source disclosure, claim
an unmanaged message, change credentials or require external authority.
