# OTH Engineering Execution Contract

## Purpose
The Engineering Execution subsystem turns a bounded software mission into a verifiable repository change while preserving honest failure semantics and lane resilience.

## Completion contract
An engineering execution may be marked successful only when:
1. The worker explicitly reaches a finish action.
2. Every worker tool call succeeds.
3. Verification completes successfully.
4. Mutation tasks produce observable workspace change.
5. Read-only engineering tasks may explicitly opt out of the change requirement.
6. The kernel independently rejects any engineering success that lacks required implementation evidence.

A passing test suite alone is never sufficient evidence that an implementation was completed.

## Workspace evidence
The subsystem snapshots repository state before and after execution using content-level fingerprints. Git status strings are not treated as sufficient because an already-dirty working tree can otherwise hide a no-op.

For non-Git test repositories, the evidence layer falls back to a deterministic repository-tree fingerprint.

## Lane resilience
Engineering currently has three execution lanes:
- ollama-engineer — native local-model execution.
- opencode-engineer — secondary execution adapter.
- engineering-audit-fallback — honest unavailable-provider fallback.

A lane that fails can be quarantined for the current cycle and the kernel can hand the task to the next lane. The evaluator records lane count, failures, quality, and the resulting lesson.

## Continuous runtime
The daemon runner continuously polls the queue. Its loop is regression-tested so a runtime exception cannot silently terminate the polling cycle.

## Scorecard
Engineering performance is persisted in the evaluation store and can be viewed with:

python -m oth.cli engineering scorecard

The scorecard reports runs, successes, failures, average quality, average lane, and last-run timestamp per engineering worker.

## Operating principle
OTH must prefer an honest failed engineering task over a plausible-looking success with no implementation evidence.