# SAMVIL v4.32.3 Release Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep GitHub default `main` on a passive v4.32.2 quarantine fuse, then build and release a deterministic, attested v4.32.3 bridge only from non-default `release/v4-stable`, without mutating existing users or any real user `HOME`, `CODEX_HOME`, Claude profile, cache, settings, or project during development and test.

**Architecture:** Treat the bridge as four isolated systems: a same-version passive quarantine fuse, a deterministic signed Release producer, an idempotent asset-aware publisher, and an authorization-rooted Claude selection/recovery engine. All mutation-capable code stays behind external authorization, exact topology classification, durable receipts, and fail-closed release-control gates. Existing v4.32.2 users are diagnosed but never adopted or rewritten by this bridge; their supported transition remains the later version-independent v4.33 bootstrap.

**Tech Stack:** Python 3.12 standard library for trusted build/control code, Python 3.9-compatible single-file stdlib entrypoints for bootstrap/preflight, C11 for the self-contained darwin-arm64 authorization verifier, POSIX shell, Git plumbing, pytest, GitHub Actions, GitHub REST/GraphQL metadata, artifact attestations, deterministic USTAR/gzip assets, and the existing PR #14 release-control foundation.

---

## 1. Fixed inputs and non-negotiable safety boundary

- Plan worktree: the isolated planning worktree created at the frozen PR #14
  head and preserved after review as
  `codex/v4.32.3-release-bridge-plan`. It is a plan/control container, not the
  bridge implementation ancestry.
- Plan/control ref: `codex/v4.32.3-release-bridge-plan`. Preserve the reviewed
  plan there before reusing the implementation branch name.
- Final implementation branch name: `codex/v4.32.3-release-bridge`; create or
  repoint it to the exact reviewed Unit 0 fuse commit only after the plan is
  preserved on the design/control ref. Do not cherry-pick a plan-only commit
  into the nine-unit release ancestry.
- Approved original/default-main commit and Unit 0 parent:
  `81c0c3468ed8757513fc4bf76b028736197bc556`
- Frozen PR #14 head:
  `141da457a98b552047f0388b9967664e11aff8b1`
- The exact original commit is the only allowed Unit 0 implementation base.
  PR #14 and reviewed prerequisite commits advance the separately pinned
  trusted control ref, but do not silently enter the candidate/fuse tree.
- Default quarantine branch remains `main` and its manifest version remains
  `4.32.2`.
- Stable Release branch is exactly `release/v4-stable` and must remain
  non-default.
- Future development branch is exactly `codex/v4.33-integration`.
- Bridge Release version is exactly `4.32.3`; the quarantine fuse and its
  legacy catalog rows remain `4.32.2`.
- The literal user-owned untracked `$CODEX_HOME/` entry in the original
  checkout must never be read, copied, staged, modified, deleted, or used as a
  fixture.
- Every development/test command uses an invocation-owned temporary `HOME`,
  `CODEX_HOME`, `CLAUDE_CONFIG_DIR`, `GNUPGHOME`, `TMPDIR`, `XDG_*`, Git global
  config, cache, and project root.
- No test may issue `git push`, create/update/delete a remote ref, mutate a
  GitHub ruleset, create/publish a Release, dispatch a real workflow, retarget a
  PR, or invoke mutation against a real Claude profile.
- Do not run the known-stuck local Seatbelt/copied-runtime/full release-control
  paths. Canonical execution is allowed only in the separately approved
  Task -2 environment described below.
- A portable unit/integration test PASS is never reported as a canonical
  release-control PASS.

At trusted-control bootstrap, after preserving this plan and before creating
prerequisite or implementation refs, verify that the plan/control commit is a
single direct child of the frozen PR #14 head and the isolated worktree is
clean:

```bash
repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"
test "$(git branch --show-current)" = "codex/v4.32.3-release-bridge-plan"
test "$(git rev-parse HEAD^)" = "141da457a98b552047f0388b9967664e11aff8b1"
test -z "$(git status --porcelain)"
git diff --check
```

Expected: all commands exit `0`; `git status --porcelain` prints nothing. Later
prerequisite control commits advance only this trusted-control ancestry. Unit
0 independently verifies the approved original parent, and Units 1–8 verify
their exact Unit 0/prior-unit parents and receipts instead of reusing this
control-branch assertion.

## 2. Execution topology and commit graph

The nine implementation units are one fuse commit plus eight bridge commits.
They form one linear ancestry, but two remote PR/ref boundaries:

```text
trusted control ref
  PR #14 exact head 141da457...
    └─ reviewed P0/P1 control commits and external authorization sidecars

candidate/release ancestry
  approved original 81c0c346...
    └─ Unit 0 quarantine-fuse commit (parent == original; one reachable commit)
         ├─ branch ref codex/v4.32.2-quarantine-fuse
         │    └─ reviewed Stage A fast-forward target for default main
         └─ release/v4-stable created at the exact fuse commit
              └─ Units 1..8 on codex/v4.32.3-release-bridge
                   └─ reviewed bridge PR targets release/v4-stable only
```

`main` must never receive Units 1..8. The bridge PR must never target `main`.
The fuse ref must remain pinned at Unit 0 even while the bridge branch advances.
Candidate code never imports or replaces trusted-control bytes; external
receipts bind both ancestries explicitly.
Every canonical invocation receives two independently descriptor-pinned roots:
`trusted_control_root` at the exact reviewed PR #14+prerequisite control commit
and `candidate_root` at the exact unit tree. P1/P3 executables are opened only
from `trusted_control_root`; candidate tests/assets are opened only from
`candidate_root`. These roots are controller-owned manifest fields, not
candidate environment variables, and no control file is copied into the
candidate tree.

## 3. Prerequisites and unit entry gates

These are trusted-control prerequisites, not bridge implementation units. P0
must be reviewed and pinned before Unit 0; P1 before Unit 1; and each P2 lock
row before the unit that consumes it.

### Prerequisite R0 — Pinned Python 3.12 test/runtime closure

**Trusted control files:**

- Create: `tools/release-control/materialize-python-closure.py`
- Create: `tools/release-control/python-closure-lock.v1.json`
- Create: `tools/release-control/tests/test_python_closure.py`

- [ ] Before Unit 0/1 RED, materialize the P0 digest-pinned Python 3.12 runtime,
  pytest closure, and trusted pytest configuration into each invocation-owned
  worktree/test root without network or user package caches.
- [ ] Bind interpreter path/realpath/version/ABI/platform, package/wheel
  digests, import paths, pytest config digest, and pre/post identity in an
  external runtime receipt.
- [ ] Never use bare `python3` for trusted build/control commands. Use the
  receipt-pinned Python 3.12 interpreter; after Unit 2 creates reviewed locks,
  rebuild the closure from those locks and compare identities.
- [ ] Reserve `/usr/bin/python3 -I -S -B` only for the Python 3.9 compatibility
  surfaces explicitly required by the acquisition runner, runtime guard, and
  Codex preflight. Test those entrypoints separately on the actual 3.9
  interpreter.
- [ ] Fault-test missing runtime/wheel, digest or ABI mismatch, partial
  extraction, path collision, symlink/hardlink/special file, ambient cache or
  `PYTHONPATH` influence, and response loss. The materializer never installs to
  a user prefix and never downloads after its externally pinned input bundle is
  admitted.

### Prerequisite P0 — Task -2 canonical execution environment

- [ ] Implement or provision an invocation-exclusive filesystem storage quota
  enforced by the kernel, with class/identity/capacity bound into the full-gate
  manifest and receipt.
- [ ] Provide the reviewed detached-process identity/signal authority required
  by the exact darwin-arm64 canary boundary, or fail before candidate/profile
  materialization with a typed blocker.
- [ ] Prove that quota exhaustion, file-count exhaustion, detached descendant,
  held descriptor, timeout, receipt-close failure, and controller death cannot
  escape the invocation-owned root or become PASS.
- [ ] Run the existing PR #14 control suite twice in that environment using
  distinct externally signed run envelopes, unique run IDs/nonces, and
  independent observer identities. Require equality of the policy-defined
  normalized deterministic projection—not byte identity of whole receipts.
  Only a same-run, same-nonce response-loss replay may require byte-identical
  authoritative receipt bytes.
- [ ] Pin the environment class, control commit, copied runtime, trusted tool
  closure, policy digest, quota identity, and receipt schema in a reviewed
  sidecar.

Current expected terminal until this prerequisite exists:

```text
BLOCKED_ENVIRONMENT
UNSUPPORTED_INVOCATION_STORAGE_QUOTA
```

Do not begin Unit 0 while that is still the canonical result.

### Prerequisite P1 — External bridge-development gate

The quarantine authorization becomes stale as soon as Unit 1 adds a file, and
the current normal pre-commit expects active skills/hooks that the fuse
intentionally removed. Therefore a third, externally authorized gate is
required before Unit 1.

**Trusted control files:**

- Create: `tools/release-control/verify-bridge-candidate.py`
- Create: `tools/release-control/run-bridge-focused-isolated.py`
- Create: `tools/release-control/tests/test_bridge_candidate_control.py`
- Create: `release/bridge/v4323-development-gate-policy.json`
- Modify: `tools/release-control/run-full-gate-isolated.py`

- [ ] Add exact target kinds `bridge_candidate_precommit` and
  `bridge_candidate_postcommit`; candidate bytes cannot select either kind.
- [ ] Require parent ancestry to contain the exact Unit 0 fuse commit and
  verify, as a separate trusted-control input, that remote default `main`
  still projects to the exact reviewed Unit 0 fuse ref/SHA/tree and ruleset.
- [ ] For Units 1–6 reject any candidate activation of plugin hooks, MCP
  routes, legacy updater/sync surfaces, or direct raw entrypoints. For Unit 7
  only, an exact unit-scoped authorization may admit the generated
  verifier-first runtime-guard hook roles and canonical guarded MCP route whose
  paths and digests are fixed by the command manifest. Legacy updater/sync,
  direct shell/Python, unguarded MCP, unknown roles, and any default-`main`
  activation remain forbidden. Unit 8 may finalize version/assets/manifests
  but may not broaden that Unit 7 allowlist.
- [ ] Treat the Unit 0 protected-base topology workflow, wrapper,
  `tools.release_topology_guard` package, policy, and action lock as immutable
  semantic roles through Units 1–8. Any modification, shadow same-name check,
  candidate-source checkout, or alternate producer invalidates authorization.
- [ ] Bind a unit-specific command/test/import manifest, expected parent,
  candidate tree, staged semantic roles, and the prior unit receipt.
- [ ] Reject candidate-local authorization, unknown semantic role, omitted
  focused test, forged candidate PASS, control-file drift, same-name test
  substitution, wrong prior unit, and fabricated post-commit identity.
- [ ] Preserve the PR #14 rule that the external verifier alone owns PASS.
- [ ] Make `run-bridge-focused-isolated.py` own `env -i`, invocation-only
  `HOME`/`CODEX_HOME`/Claude/TMPDIR/XDG/Git config, network denial, bounded
  process supervision, and the unit-specific fixed argv manifest. Focused
  snippets in this plan are argv tails and must never be run bare.
- [ ] Run RED/GREEN tests on portable fixtures, then run the canonical P0 gate
  twice with distinct signed run/auth envelopes and pin both receipts before
  Unit 1. Their unique envelope/run/observer fields must differ while the
  policy-defined normalized deterministic projection is identical. Reserve
  whole-receipt byte equality for same-nonce response-loss replay only.
- [ ] Add explicit tests proving an authorized Unit 7 guarded hook/MCP
  projection passes while the same bytes under an unapproved role, any raw
  direct entry, or any active projection on remote default `main` fails.
- [ ] The verifier implementation may be reviewed before Unit 0, but finalize
  the development policy/authorization only after Unit 0 supplies the exact
  fuse commit/tree. Keep that policy on the trusted control side, not in the
  candidate tree as self-authorization.

Focused command in the P0 environment:

```bash
{trusted_control_root}/mcp/.venv/bin/python -B \
  {trusted_control_root}/tools/release-control/tests/test_bridge_candidate_control.py
```

Expected: exit `0`, followed by a canonical external receipt whose target kind
is `bridge_candidate_precommit`; a portable result alone is insufficient.

### Prerequisite P2 — External source and workflow locks

- [ ] Before Unit 0, approve the exact full-SHA Action/runtime rows used by the
  dormant protected-base `release-topology-guard` and legacy monitor, and
  materialize only those rows as
  `release/quarantine/v4322-workflow-actions.lock.json` in the fuse.
- [ ] Approve the exact rows that Unit 2 will materialize as
  `release/workflow-actions.lock.json`: repository, tag, peeled commit SHA,
  source tree, and license identity for every GitHub Action used by bridge
  workflows. Bind the approved row set in an external control receipt.
- [ ] Approve the exact rows that Units 2 and 5 will materialize as
  `release/runtime-sources.lock.json` and `release/native-sources.lock.json`
  for the darwin-arm64 Python runtime, runtime builder, and native verifier's
  vendored cryptographic source. Bind the approved row set externally.
- [ ] Record immutable URLs, upstream digests, versions, license/SBOM identity,
  and allowed output filenames. Branch/latest URLs are forbidden.
- [ ] Review the out-of-band canary verifier root, Ed25519 current/next public
  keys, key epoch, revocation epoch, audience, repository id/name, workflow
  identity constraints, and max lifetime before Unit 5. Do not pretend the
  future Unit 5 verifier/runner/policy digests are known: finalize those exact
  bytes in the P3 `component` narrowing sidecar only after Unit 5 GREEN and
  before its canonical precommit gate. Candidate and draft sidecars are
  finalized at their later evidence boundaries.
- [ ] Record unavailable or unreviewed external inputs as typed blockers; do
  not insert temporary hashes or sample keys into production policy.

Workflow/runtime lock rows must be concrete before Unit 2. Native verifier
source and canary key/policy rows must be concrete before Unit 5.

### Prerequisite P3 — Out-of-band bootstrap, remote-ref controller, and external monitors

These files live only on the trusted control ref and are never copied into the
candidate/release tree:

- Create: `tools/release-control/launch-bridge-canary.py`
- Create: `tools/release-control/verify-bridge-bootstrap.py`
- Create: `tools/release-control/remote-ref-transaction.py`
- Create: `tools/release-control/github-release-transaction.py`
- Create: `tools/release-control/integration-pr-transaction.py`
- Create: `tools/release-control/verify-bridge-readiness.py`
- Create: `tools/release-control/external-default-monitor.py`
- Create: `tools/release-control/external-claude-host-watcher.py`
- Create: `tools/release-control/observe-codex-no-write.py`
- Create: `tools/release-control/canary-verifier-root.v1.json`
- Create: `tools/release-control/bridge-bootstrap-policy.v1.json`
- Create: `tools/release-control/remote-ref-policy.v1.json`
- Create: `tools/release-control/external-monitor-policy.v1.json`
- Create: `tools/release-control/codex-no-write-observer-policy.v1.json`
- Create: `tools/release-control/tests/test_bridge_bootstrap.py`
- Create: `tools/release-control/tests/test_remote_ref_transaction.py`
- Create: `tools/release-control/tests/test_github_release_transaction.py`
- Create: `tools/release-control/tests/test_integration_pr_transaction.py`
- Create: `tools/release-control/tests/test_bridge_readiness.py`
- Create: `tools/release-control/tests/test_external_monitors.py`
- Create: `tools/release-control/tests/test_codex_no_write_observer.py`

- [ ] Verify an exact absolute regular `gh` executable by path components,
  realpath, owner/mode, device/inode, digest, version, and required capability;
  reject PATH/alias/function substitution and recheck before every use.
- [ ] Enforce exact repository id/name, source ref/digest, signer
  workflow/digest, SLSA predicate, OIDC issuer, subject digest, and
  deny-self-hosted policy before Python or runner invocation where the mode
  requires production attestation. Cover online and exact offline-bundle
  verification.
- [ ] Split bootstrap/authorization into exact schemas `component`,
  `candidate`, and `draft`. The pre-Unit-5 prerequisite pins only framework
  code, root/current+next keys, epochs, audiences, constraint language, and
  maximum lifetime. After Unit 5 produces its staged tree/native verifier/
  generated runner/policy bytes, P3 finalizes a narrowing `component` sidecar
  immediately before the Unit 5 canonical gate; it trusts the exact P0 tree,
  build and external control signature and does not require a nonexistent tag
  attestation. At choreography step 13, `candidate` binds the non-publishable
  candidate index, reviewed candidate workflow run/digest set, external unit/
  review receipts and steps 11–13 topology/payload receipts; PR workflows do
  not issue production SLSA. `draft` alone requires exact tag workflow
  production SLSA/OIDC online and offline attestation plus Release index/assets.
- [ ] Emit distinct external receipt IDs
  `component_canary_bootstrap_verified`,
  `component_canary_authorization_verified`,
  `candidate_canary_bootstrap_verified`,
  `candidate_canary_authorization_verified`,
  `draft_canary_bootstrap_verified`, and
  `draft_canary_authorization_verified`. Mode/channel substitution, a generic
  reusable authorization, duplicate ID, or use outside its exact causal chain
  fails.
- [ ] Emit typed bootstrap reasons `GH_MISSING`, `GH_TOO_OLD`,
  `GH_AUTH_REQUIRED`, `GH_SSO_REQUIRED`, `GH_RATE_LIMITED`,
  `NETWORK_UNREACHABLE`, `TLS_OR_CA_FAILURE`, `PROXY_FAILURE`,
  `PYTHON_MISSING`, `PYTHON_UNTRUSTED`, `RUNTIME_ASSET_MISSING`,
  `RUNTIME_ASSET_UNSUPPORTED`, `RUNTIME_BUILDER_MISSING`,
  `RUNTIME_BUILDER_UNSUPPORTED`, and `WHEEL_CLOSURE_MISMATCH`; prove attestation
  failure means Python invocation zero.
- [ ] Implement exact controller actions `create_original_anchor`,
  `create_fuse_branch`, `create_bridge_candidate_branch`,
  `create_release_branch`, `stage_a`, and `stage_r`. Ref creation is
  expected-absent at the exact authorized SHA/tree; Stage A/R are expected-old
  single-ref transactions. Every action uses one-shot authorization
  consumption, response-loss journal/read-back reconciliation, exact ref/tree
  verification, ruleset activation/relock, and idempotent same-identity replay.
  Raw operator `git push`/ad-hoc mutating `gh api` is not an approved path.
  The controller emits action-specific receipts; it never collapses prepared
  Stage R, rehearsal, live Stage A, and actual incident Stage R into one
  success ID.
- [ ] Implement separate one-shot GitHub transaction actions `open_fuse_pr`,
  `open_bridge_pr`, `merge_release_pr`, `create_tag`,
  `create_draft_release`, `upload_verified_assets`, `publish_release`,
  `create_integration_branch`, `update_pr13_head`, and `retarget_pr13`.
  Candidate publisher code owns only deterministic plan/journal/response
  validation and never receives credentials; P3 owns the exact GitHub App/`gh`
  capability, request execution, authorization consumption, response-loss
  read-back, and signed result. Each action verifies its immediately prior
  publisher/readiness state and cannot be reused for another state or object.
- [ ] `verify-bridge-readiness.py` is the sole authority that evaluates the
  control-pinned schema plus candidate Unit 7 policy/report, external receipt
  chain, causal dependencies, freshness and evidence planes, then emits signed
  terminal receipts `candidate_merge_ready`, `tag_ready`, or `publish_ready`.
  Candidate Unit 7/8 code may render a structural report but can never advance
  a terminal. Every mutating P3 action consumes the exact matching signed
  terminal/state capability.
- [ ] Provision a primary external GitHub App/org-control monitor that pins
  repository/default/ref/SHA/tree, ruleset identities, and admin/bypass
  inventory. Combine repository-edited/audit-log webhook with bounded poll;
  drift opens a kill switch and human alert, never a blind rewrite.
- [ ] Provision an external Claude package/host watcher that characterizes new
  executable/package/schema identities and blocks rollout on unknown behavior.
- [ ] Provision an external deny-write/deny-network Codex observer that owns
  the authoritative syscall/filesystem/process receipt. Candidate stdout and
  Merkle equality are corroborating evidence only; they cannot assert their
  own write-zero verdict.
- [ ] Fault-test missed webhook, delayed poll, wrong App, admin inventory drift,
  response loss at every ref/PR/merge/tag/draft/asset/publish/retarget boundary,
  ref race, asset conflict, wrong synthetic merge tree, ruleset relock failure,
  stale readiness, action-capability replay, and monitor/controller death. Bind
  monitor/controller/readiness receipts into the appropriate terminal.

## 4. Shared implementation conventions

### 4.1 New bridge code boundary

Do not rename or repurpose `mcp/samvil_mcp/release.py` or
`scripts/build-release-bundle.py`; they currently represent app release
readiness/evidence, not the v4.32.3 distribution bridge.

New trusted bridge code lives under:

```text
tools/__init__.py
tools/release_bridge/
  __init__.py
  contracts.py
  legacy_distribution.py
  legacy_host.py
  build_release_assets.py
  publisher.py
  github_remote.py
  publisher_journal.py
  claude_selection.py
  current_classifier.py
  next_session_verifier.py
  bridge_guard.py
  receipt_store.py
  canary_authorization.py
  acquisition.py
  registry_transaction.py
  capability_gate.py
  tests/
```

Thin public entrypoints live under `scripts/`. The one remote topology
evaluator is the Unit 0 protected-base
`tools/release_topology_guard/guard.py`; the bridge publisher imports it
unchanged. `tools/release-control/` owns external observation, signed receipt
aggregation, and mutation controllers, but no second topology evaluator. The
acquisition and Codex check entrypoints must stay Python 3.9-compatible and
stdlib-only.
`tools/release_bridge` is a normal underscore-named package with an explicit
`__init__.py`; tests import it through normal importlib semantics from the
repository root. No entrypoint may invent a private `sys.path`/dynamic-loader
rule or load candidate code by filename from an attacker-selected CWD.
All package-internal modules use valid underscore names. Public `scripts/*.py`
wrappers never consult `PYTHONPATH` or caller-selected module names; after
their own external regular-file identity is verified, they execute one fixed
`-B -m tools.release_bridge.<module>` target with the receipt-pinned
interpreter. P1 binds the wrapper, both package `__init__.py` files, imported
module blobs, exact CWD, and argv. Tests poison CWD, `PYTHONPATH`, and an
installed same-name `tools` package and require the resolved blobs to remain in
the authorized candidate tree.

### 4.2 Strict JSON and receipt contract

Every bridge JSON loader must reject duplicate keys, non-UTF-8 input, unknown
top-level fields, floats where schemas require integers, booleans used as
integers, oversized strings/arrays/maps, excessive depth, and non-canonical
paths. Tracked/public immutable JSON uses canonical UTF-8, sorted keys, compact
separators, one trailing newline, and archive mode `0644`. Runtime journals,
state, private receipts, and locks use an existing descriptor-validated parent
mode `0700` and file mode `0600`.

Candidate-produced unit result files include at least:

```json
{
  "canonical_gate_receipt_sha256": "64 lowercase hexadecimal characters",
  "focused_gate": "pass",
  "input_digests": {},
  "output_digests": {},
  "pre_commit_gate": "pass",
  "protected_scope_mutations": 0,
  "schema_version": "samvil.bridge-unit-receipt.v1",
  "source_commit": "full git sha",
  "source_tree": "full git tree sha",
  "unit": 1
}
```

Candidate files never assert authoritative canonical PASS. The separately
signed external control receipt owns the canonical verdict and binds the unit
result digest, authorization, control commit, candidate tree, command manifest,
storage/admission identity, and prior-unit receipt.

All runtime durable writers use one shared primitive with `O_NOFOLLOW`, regular
file/`nlink=1` validation, exclusive temp creation, bounded write, file `fsync`,
atomic rename/no-replace policy appropriate to the schema, parent-directory
`fsync`, close-error handling, monotonically linked sequence/hash, and
descriptor/path identity recheck. Crash/fault tests cover every write and close
boundary for publisher journals, activation journals, accepted-version,
commit/ready/serving, capability, and admission receipts.

No local absolute path, username, token, proxy credential, custom CA path, or
real profile identity may enter a promotable receipt.

### 4.3 Focused-command isolation and Python ownership

Every focused command block below is an argv manifest, not a command to run in
the ambient shell. Execute it through the pinned P1
`run-bridge-focused-isolated.py`, which supplies the R0 Python 3.12 interpreter,
`env -i`, isolated roots/config, network denial, process supervision, and an
authoritative execution receipt. Bare `python3` text in an argv block means the
pinned R0 interpreter after manifest substitution; only explicitly written
`/usr/bin/python3 -I -S -B` remains the system 3.9 compatibility probe.
Likewise, displayed `bash`, `make`, `git`, or other tool names are semantic argv
roles that P1 resolves to exact P0-pinned absolute executable identities; PATH
lookup, aliases, shell functions, and candidate-selected executables are not
allowed.
Where a command names `{trusted_control_root}` or `{candidate_root}`, those are
typed descriptor-root substitutions performed by P1 from the signed command
manifest—not shell/environment interpolation. A path under
`tools/release-control/` belongs to the trusted root unless the unit explicitly
creates a candidate-side structural aggregator and labels its result
non-authoritative.

### 4.4 Per-unit RED → GREEN → canonical gate → one commit

For every Unit 0..8:

- [ ] Write only that unit's focused tests and fixtures first.
- [ ] Run the focused command and verify failure is the intended missing
  behavior, not collection/import/syntax failure.
- [ ] Implement only the current unit's production code.
- [ ] Re-run focused tests to GREEN.
- [ ] Run related regression tests and `git diff --check`.
- [ ] Stage the exact unit tree and obtain a fresh external candidate
  authorization for its tree and semantic-role digests.
- [ ] Run `bash scripts/pre-commit-check.sh` in an isolated environment.
- [ ] Unit 0 runs the F0 canonical `candidate_precommit` gate. Units 1..8 run
  the P1 `bridge_candidate_precommit` gate.
- [ ] Commit once without `--no-verify`, using an invocation-owned hooks path
  that contains the trusted pre-commit hook and no post-commit mutator.
- [ ] Unit 0 runs `candidate_postcommit`; Units 1..8 run
  `bridge_candidate_postcommit` against the exact new commit and accepted
  precommit receipt.
- [ ] If any byte changes after authorization or review, discard the receipt,
  regenerate the tree authorization, and repeat both independent reviews and
  both canonical gates.

If P0 or the external authorization is unavailable, stop before commit and
report `BLOCKED_ENVIRONMENT`; do not weaken the gate.

## 5. Unit 0 — v4.32.2 passive quarantine fuse and Stage R

This unit executes Tasks 0–6 of the existing detailed subplan
`docs/superpowers/plans/2026-07-29-samvil-v4322-quarantine-fuse-f0.md` under
that document's binding section 1.1 current-execution mapping. Task -2/Task -1
are preserved historical acceptance context and must not be rerun as branch
creation, fixup, autosquash, or history rewrite. Current P0 closes their
remaining environment blocker on the frozen PR #14 descendant control
ancestry. The checklist below is the bridge-program boundary and must not
replace any stricter F0 safety or verification requirement.

**Branch:** `codex/v4.32.2-quarantine-fuse`

**Required parent:**
`81c0c3468ed8757513fc4bf76b028736197bc556`

**Create:**

- `release/quarantine/v4322-policy.json`
- `release/quarantine/v4322-passive-surface-manifest.json`
- `scripts/quarantine-fuse.py`
- `scripts/rehearse-quarantine-refs.py`
- `scripts/check-release-topology.py`
- `tools/__init__.py`
- `tools/release_topology_guard/__init__.py`
- `tools/release_topology_guard/guard.py`
- `tools/release_topology_guard/tests/__init__.py`
- `tools/release_topology_guard/tests/test_guard.py`
- `mcp/tests/test_quarantine_fuse.py`
- `mcp/tests/test_release_topology_guard.py`
- `quarantine-skills/samvil/SKILL.md`
- `quarantine-skills/samvil-update/SKILL.md`
- `.github/workflows/legacy-feed-monitor.yml`
- `.github/workflows/release-topology-guard.yml`
- `release/quarantine/v4322-topology-guard-policy.json`
- `release/quarantine/v4322-workflow-actions.lock.json`

**Control-side evidence:**

- `release/quarantine/v4322-original-receipt.json`
- `release/quarantine/v4322-candidate-authorization.json`
- `release/quarantine/v4322-candidate-authorization.json.sig`
- `release/quarantine/v4322-historical-surface-ledger.json`
- `release/legacy-v4322-distributions.json`
- `release/legacy-v4322-distributions.json.sig`

**Modify:**

- `.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `.mcp.json`
- `README.md`
- `AGENTS.md`
- `CLAUDE.md`
- `references/opencode-agents-section.md`
- `references/gemini-gemini-md-section.md`
- every ledger-listed `skills/**/SKILL.md` and `SKILL.legacy.md`
- every ledger-listed `references/codex-commands/*.md`
- every ledger-listed `references/gemini-commands/*.toml`
- `scripts/setup-codex.sh`
- `scripts/sync-cache.sh`
- `scripts/install-git-hooks.sh`
- every ledger-listed `hooks/*` and `.githooks/*`
- `mcp/tests/test_update_smoke.py`
- `mcp/tests/test_sync_cache_smoke.py`
- `mcp/tests/test_ci_workflow.py`
- `scripts/pre-commit-check.sh`

- [ ] Freeze all retrievable historical rows and the historical-only surface
  union before rendering the fuse; missing official artifacts remain typed
  blockers.
- [ ] Create the implementation worktree directly from the approved original
  commit. Abort unless `git rev-parse HEAD` equals the required parent before
  edits, and after commit require `parent == original` plus
  `git rev-list --count original..implementation == 1`.
- [ ] Write RED tests named
  `test_original_tree_is_not_quarantine_fuse`,
  `test_plugin_manifest_has_no_hooks_or_mcp`,
  `test_marketplace_catalog_has_no_installable_plugin`,
  `test_every_historical_surface_resolves_to_passive_content`,
  `test_passive_entries_are_no_write_idempotent`,
  `test_stage_a_allows_only_original_to_fuse_main`, and
  `test_stage_r_requires_fuse_parent_and_original_tree`.
- [ ] Implement strict APIs `load_policy()`, `collect_git_inventory()`,
  `verify_quarantine_tree()`, `render_passive_overlay()`,
  `verify_passive_surface_manifest()`, `render_deferred_receipt()`,
  `create_stage_r_commit()`, `apply_expected_old_ref_update()`, and
  `rehearse_stage_a_and_r()`.
- [ ] Keep plugin version `4.32.2`, expose quarantine skills only, remove all
  plugin-owned hooks/MCP registration, make `.mcp.json` empty, and make the
  marketplace plugin list empty.
- [ ] Include the protected-base `release-topology-guard` as a dormant,
  explicit `pull_request`-to-`release/v4-stable` workflow in the fuse. It has no
  default-main push/schedule/manual trigger, no secrets or write permission,
  uses only the pre-Unit-0 full-SHA action/runtime lock, checks out and executes
  the exact protected base source, and emits the check identity later verified
  by Unit 3/P3. Candidate Units 1–8 may not modify its workflow, wrapper,
  package, policy or lock. It is absent from plugin/runtime discovery and has
  zero effect on users or default-main checkout execution.
- [ ] Make `tools.release_topology_guard.guard` the single topology evaluator
  used by the dormant workflow and later publisher. RED tests reject PR-
  modified same-name workflows/scripts, wrong base source SHA/App, implicit
  default refs, wrong default main/fuse, wrong stable base/head/synthetic tree,
  ruleset/bypass drift, and any candidate attempt to configure authority.
- [ ] Replace every current or historical auto-loaded/user-followable active
  surface with deterministic `DEFERRED_TO_V433` content.
- [ ] Prove two independent invocations with distinct signed envelopes,
  nonces, run IDs, and observers produce identical normalized deterministic
  projections and mutation cardinality zero across isolated
  profile/cache/settings/project, temp, network, Git refs, and process
  inventory. Separately prove same-nonce response-loss replay returns
  byte-identical receipt bytes without a duplicate event.
- [ ] Build Stage R with `parent == exact fuse commit` and
  `tree == exact original tree`; do not update a real ref.
- [ ] Rehearse Stage A and Stage R only in a disposable bare mirror, with one
  expected-old CAS update of `refs/heads/main` per transition and idempotent
  response-loss retry.
- [ ] Finalize exactly one signed `quarantine_fuse` row after the fuse commit
  identity exists.

Focused RED/GREEN command is the exact pinned command from the F0 plan, not an
ad-hoc local pytest invocation. The canonical terminal must be PASS in P0.

Commit:

```bash
git commit -m "v4.32.2 격리 퓨즈와 Stage R 복구 계약을 고정한다"
```

Expected: one fuse implementation commit; a separate local branch ref remains
pinned to it while bridge development continues from that commit.

## 6. Unit 1 — Legacy ledger, straggler, stale-process, and shadow-host characterization

Before editing, preserve the plan on
`codex/v4.32.3-release-bridge-plan`, then create the fresh
`codex/v4.32.3-release-bridge` implementation ref at the exact reviewed Unit 0
fuse commit. Abort unless its parent chain contains the approved original
followed by exactly one Unit 0 implementation commit. The plan-only control
commit must not appear in this ancestry.

**Create:**

- `tools/release_bridge/__init__.py`
- `tools/release_bridge/tests/__init__.py`
- `tools/release_bridge/legacy_distribution.py`
- `tools/release_bridge/legacy_host.py`
- `tools/release_bridge/characterize_legacy_host.py`
- `tools/release_bridge/tests/test_legacy_distribution.py`
- `tools/release_bridge/tests/test_legacy_host.py`
- `tools/release_bridge/tests/fixtures/legacy/`
- `release/legacy-host-matrix.json`
- `release/bridge/v4323-candidate-contract.json`
- `release/legacy-v4322-distributions.json`
- `release/legacy-v4322-distributions.json.sig`
- `release/quarantine/v4322-historical-surface-ledger.json`

The three legacy evidence files above are materialized byte-for-byte from the
externally reviewed F0 control evidence; they are not assumed to exist in the
fuse tree and are never regenerated from candidate Git history.

**Modify:**

- `scripts/pre-commit-check.sh`

**Required public APIs:**

```python
load_distribution_ledger(path)
load_historical_surface_ledger(path)
validate_materialized_legacy_evidence(distribution_ledger, historical_surface_ledger, expected_binding)
validate_distribution_ledger(ledger)
discover_surface_set_from_git(git_dir, commit)
surface_set_digest(paths)
build_snapshot_manifest(git_dir, commit)
replay_legacy_rsync_sequence(rows)
derive_known_residue(sequence)
semantic_class_id(projection)
classify_topology_observation(observation, matrix)
validate_host_matrix_coverage(matrix, ledger)
build_legacy_catalog(ledger, matrix)
build_legacy_observation_receipt(observation)
validate_legacy_observation_receipt(receipt)
```

- [ ] First add the bridge-development pre-commit selector. It accepts only a
  P1 external authorization whose parent is the exact fuse commit, whose unit
  is `1`, and whose semantic roles enumerate the ledger, host matrix, policy,
  gate, implementation modules, and focused tests.
- [ ] P1 materializes the distribution ledger, detached signature, and
  historical surface ledger only from externally signed F0 control evidence.
  P1—not candidate code—verifies release-authority signature, control
  commit/tree, source blob IDs, exact byte length/digests, embedded historical
  ledger binding, modes, no-follow destination creation, and materialized Git
  blob IDs before focused code executes. Candidate code only validates the
  already pinned schema/binding and cannot synthesize, normalize, reserialize,
  edit, or sign those bytes.
- [ ] Treat `v4323-candidate-contract.json` as candidate-declared schema/input
  only. It cannot authorize bridge mode, choose trusted commands, or weaken the
  external `v4323-development-gate-policy.json`.
- [ ] RED: reject an empty historical ledger, zero/multiple fuse rows,
  post-cutoff non-fuse rows, dynamic Git-history expansion, missing historical
  surfaces, incomplete semantic projection, unknown official artifact digest,
  stale-process active delta reported as PASS, and an uncovered
  semantic-class/platform pair. Add an explicit test proving candidate code
  cannot alter or reserialize the externally signed imported bytes.
- [ ] Model a semantic class from exact platform/package/updater/skill-discovery/config-root
  projections. Bind all projection digests into `semantic_class_id`; display
  labels, mtime, version strings, and folder names are not authority.
- [ ] Replay real old no-delete rsync/rename/sibling-cleanup semantics for A→B
  and A→B→C. Only exact replay output becomes `known_residue`.
- [ ] Preserve `STOCK_EXACT`, `KNOWN_HYBRID`, and
  `QUARANTINE_FUSE_EXACT` as diagnosis-only results. All three terminate
  `DEFERRED_TO_V433` with protected-scope mutation zero.
- [ ] Classify two-process stale memo as
  `STALE_HOST_MEMORY_RISK_OBSERVED`; active/hybrid switch-attributable delta is
  `SEMANTIC_FUSE_OR_UNKNOWN` and blocks Stage A/bridge merge.
- [ ] Preserve discovery-failure clone plus old rsync/rename/sibling-delete as
  `LEGACY_RISK_OBSERVED`; it is never a no-write PASS, while the cloned source
  must still contain only the passive fuse and zero bridge/v4.33 bytes.
- [ ] Define this exact receipt taxonomy; missing, merged, renamed, or
  PASS-normalized risk receipts fail:

| `receipt_id` | Exact terminal/reason |
|---|---|
| `legacy_successful_discovery_no_write` | `SUCCESSFUL_DISCOVERY_NO_WRITE` |
| `legacy_discovery_failure_risk` | `LEGACY_RISK_OBSERVED` |
| `stale_catalog_risk` | `STALE_CATALOG_RISK_OBSERVED` |
| `stale_host_memory_risk` | `STALE_HOST_MEMORY_RISK_OBSERVED` |
| `pinned_source_risk` | `PINNED_SOURCE_RISK_OBSERVED` |
| `host_topology_risk` | `HOST_TOPOLOGY_RISK_OBSERVED` |
| `refreshed_pause_cold` | `REFRESHED_PAUSE_COLD` |
| `fixture_passive_only_no_worse` | fixture-only `PASSIVE_ONLY_NO_WORSE` branch proof |
| `fixture_semantic_fuse_or_unknown_rejection` | fixture-only rejection terminating `SEMANTIC_FUSE_OR_UNKNOWN` |

  Bind each to semantic class, platform/package/updater/source/ref/catalog and
  process generation, inert-control identity, pre/post installed/cache/
  settings/selection digests, switch-attributable delta, protected-scope
  mutation count, and external canonical receipt digest where applicable.
- [ ] Focused/property tests write only `fixture_<live-receipt-id>` with
  `evidence_plane=portable_fixture`, except the two explicitly fixture-only IDs
  above. Actual readiness IDs omit the prefix and require
  `evidence_plane=live_candidate`, an external signer/control chain, exact live
  default-main/ref/tree and candidate head, host/process generation, bounded
  freshness, and causal parent receipts. A portable or shadow receipt can
  never be relabelled as live.
- [ ] Successful discovery requires exact `CURRENT == LATEST`, default-main
  fuse identity, and plugin/cache/settings/selection mutation zero; it is
  independent from discovery-failure evidence.
- [ ] Running-memo residuals may be recorded only as
  `BASELINE_EQUIVALENT_OLD_ACTIVE` or `PASSIVE_ONLY_NO_WORSE`; neither is a
  holdback PASS. Any hybrid/active delta, downgrade/uninstall, extra
  selection/settings mutation, or unknown class is
  `SEMANTIC_FUSE_OR_UNKNOWN` and blocks Stage A and bridge merge.
  `stale_host_memory_risk` carries the actual residual subtype;
  `fixture_passive_only_no_worse` is a required characterization receipt that
  proves that allowed branch, not a claim that every live host has that
  subtype.
- [ ] Ensure every exact historical artifact maps to one semantic class and
  every semantic-class/platform cell has both focused and full-topology
  receipts. Missing artifacts remain explicit blockers.

Focused commands:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 mcp/.venv/bin/python -I -m pytest \
  -p no:cacheprovider --rootdir=. --import-mode=importlib \
  tools/release_bridge/tests/test_legacy_distribution.py \
  tools/release_bridge/tests/test_legacy_host.py -q
mcp/.venv/bin/python -B -m tools.release_bridge.characterize_legacy_host \
  --fixture-root tools/release_bridge/tests/fixtures/legacy \
  --ledger release/legacy-v4322-distributions.json \
  --matrix release/legacy-host-matrix.json \
  --check
```

Expected RED: named schema/topology invariant failures. Expected GREEN: exit
`0`, no protected-scope mutation, and no residual risk counted as PASS.

Commit:

```bash
git commit -m "레거시 배포 원장과 호스트 토폴로지 판정을 고정한다"
```

## 7. Unit 2 — Deterministic core, wheel/runtime bundle, and signed manifest contract

**Create:**

- `tools/release_bridge/contracts.py`
- `tools/release_bridge/build_release_assets.py`
- `tools/release_bridge/render_core_manifest.py`
- `tools/release_bridge/tests/test_release_contracts.py`
- `tools/release_bridge/tests/test_release_assets.py`
- `tools/release_bridge/tests/test_core_manifest_renderer.py`
- `tools/release_bridge/tests/test_release_bridge_workflow.py`
- `release/core-manifest-policy.json`
- `release/version-domains.json`
- `release/bridge/v4323-limitations.json`
- `release/bridge/v4323-candidate-index-policy.json`
- `mcp/uv.lock`
- `mcp/runtime-requirements.lock`
- `release/runtime-sources.lock.json`
- `release/platform-policy.json`
- `release/workflow-actions.lock.json`
- `.github/workflows/release-bridge-build.yml`
- `scripts/validate-release-bridge-workflow.py`
- `scripts/build-release-bridge.py`

**Modify:**

- `mcp/pyproject.toml`
- `mcp/samvil_mcp/__init__.py`
- `hooks/validate-version-sync.sh`

**Required public APIs:**

```python
load_strict_json(path, schema)
canonical_json_bytes(value)
verify_tracked_core_manifest(repo_root, manifest)
render_tracked_core_manifest(repo_root, policy)
write_tracked_core_manifest_explicit(output_path, rendered, expected_absent_or_digest)
normalized_core_tree_digest(records)
build_deterministic_core_archive(repo_root, output_path)
materialize_runtime_requirements(uv_lock, output_path)
inspect_wheel_identity(wheel_path)
verify_wheel_closure(requirements, wheel_paths)
build_wheel_bundle(wheel_paths, output_path)
verify_runtime_source_lock(lock, platform)
build_candidate_index(inputs)
verify_candidate_index(index, authorization)
build_release_index(inputs)
fixed_payload_equality_set(candidate_index, release_index)
build_release_assets(inputs, output_dir)
```

- [ ] RED: canonical JSON instability, supported-platform key-set mismatch,
  stale core manifest, extra immutable entry, symlink/hardlink/device/FIFO,
  path collision, archive resource-limit overflow, non-epoch timestamp,
  missing/extra wheel, lock-closure mismatch, runtime source digest mismatch,
  mutable Action ref, broad candidate-workflow permissions, untracked build
  input, release mode accepting a missing later-unit subject, an MCP wheel not
  named exactly `samvil_mcp-4.32.3-py3-none-any.whl`, and missing/unknown or
  wrong-typed `limitations` fields. Also reject a publishable candidate index,
  candidate/tag identity confusion, missing CI/review/control receipt, and an
  equality set that includes either index or detached provenance.
- [ ] Establish explicit version domains in `release/version-domains.json`.
  The exact roots are `default_quarantine=4.32.2` and
  `bridge_release=4.32.3`. Unit 2 sets the MCP distribution
  (`mcp/pyproject.toml`, package `__version__`, lock metadata, and wheel
  filename) to exact `4.32.3`, while the candidate plugin manifest and all
  quarantine/legacy identities remain `4.32.2` under one externally
  authorized pre-final Units 2–7 rule. `--mode release` remains blocked until
  Unit 8 removes that exception and finalizes the plugin domain. Extend
  `hooks/validate-version-sync.sh` here so this intentional split is
  machine-checked rather than warning-only; candidate input cannot select the
  phase.

```json
{
  "bridge_plugin_version_by_phase": {
    "final": "4.32.3",
    "pre_final": "4.32.2"
  },
  "bridge_release": "4.32.3",
  "default_quarantine": "4.32.2",
  "phase": "pre_final",
  "pre_final_units": [2, 3, 4, 5, 6, 7],
  "release_mode_allowed_by_phase": {
    "final": true,
    "pre_final": false
  },
  "schema_version": "samvil.version-domains.v1"
}
```

  P1 fixes `phase=pre_final` for Units 2–7. Unit 8 alone changes the tracked
  phase to `final`; unknown phases, altered unit sets, or a release-mode true
  pre-final policy fail.
- [ ] Generate `mcp/uv.lock` from the reviewed dependency constraints, then
  materialize exact URL-free name/version/hash rows into
  `mcp/runtime-requirements.lock`; bind the source lock digest in its header.
- [ ] Build the SAMVIL MCP wheel and darwin-arm64 dependency wheel bundle so
  their union exactly equals the direct/transitive lock closure.
- [ ] Repack only runtime sources named by the reviewed lock. Use fixed
  `SOURCE_DATE_EPOCH=0`, normalized owner/group, modes `0644`/`0755`, sorted
  USTAR entries, and deterministic gzip headers.
- [ ] Enforce archive limits from the design at header preflight and streaming
  extraction: 128 MiB compressed, 512 MiB expanded regular-file bytes, 64 MiB
  per file, 20,000 entries, depth 32, UTF-8 path 256 bytes, ratio 200:1.
- [ ] Implement verify-only handling for the tracked
  `.samvil-release/core-manifest.json`. Before Unit 8, release mode returns
  typed `CORE_MANIFEST_MISSING_OR_INCOMPLETE`; contract/determinism tests may
  render an invocation-owned candidate manifest, but never inject it into a
  Release asset. The exact immutable set excludes the manifest file itself and
  includes no other implicit exclusion. Unit 8 performs the sole tracked
  regeneration; the archive contains the manifest and the Release index binds
  its digest without a self-hash cycle.
- [ ] Keep core-manifest generation separate from release build. The reviewed
  renderer may write only an explicitly named
  `.samvil-release/core-manifest.json` using no-follow/no-replace-or-expected-
  digest semantics; `scripts/build-release-bridge.py` and all normal checks are
  verify-only and never repair a stale/missing manifest. Fault-test source-tree
  drift during generation, output collision, file/parent fsync and close.
- [ ] Define the exact fixed-subject role schema for core archive, release
  index, acquisition runner, authorization policy/verifier, legacy catalog,
  legacy host matrix, MCP wheel, dependency lock digests, wheel bundle, Python
  runtime, and runtime builder. Unit 2 materializes only the core/runtime/lock
  roles it owns; `--mode release` must fail closed while later-unit roles are
  absent. No placeholder/stub asset is allowed.
- [ ] Implement three non-overlapping build modes. `core-runtime` is Unit 2
  component evidence only. `candidate` builds every deterministic fixed payload
  plus non-publishable `samvil-4.32.3-candidate-index.json`, which binds exact
  repository, fuse base, Unit 8 head, synthetic merge tree, candidate workflow
  id/run/attempt/head, review/control receipt digests, release epoch/protocol,
  platform policy, and payload digest map; it has `publishable=false`, no tag,
  and is never a Release asset. `release` is allowed only from the frozen
  post-merge stable/tag source and creates
  `samvil-4.32.3-release-index.json` with the exact tag/source identity.
- [ ] Candidate-to-pretag equality covers every deterministic fixed payload—
  core, acquisition runner, authorization policy/verifier, legacy catalog and
  host matrix, MCP wheel, lock digests, wheel bundle, Python runtime, and
  runtime builder—but explicitly excludes candidate index, release index,
  detached provenance, attestation envelopes, and timestamps whose source/ref
  identity legitimately differs. Same-name fixed payload mismatch blocks tag.
- [ ] Make `release/bridge/v4323-limitations.json` the exact structured SSOT
  and make `build_release_index()` copy it without defaults, merge, omission,
  or override. Unknown, omitted, duplicated, wrong-typed, noncanonical, or
  wrong-valued fields fail; Unit 7 carries the canonical object and digest,
  while Unit 8 renders Korean copy from it without rewriting it.

```json
{
  "bootstrap_system_python_required": true,
  "canonical_stable_branch": "release/v4-stable",
  "codex_native_migration_supported": false,
  "default_marketplace_plugin_installable": false,
  "external_acquisition_canary_authorization_required": true,
  "external_acquisition_single_tenant_enclave_required": true,
  "external_acquisition_user_supported": false,
  "future_host_behavior_preventable": false,
  "github_default_branch": "main",
  "historical_pinned_source_revocable": false,
  "legacy_custom_updater_transactional": false,
  "legacy_default_branch_quarantine_required": true,
  "legacy_discovery_failure_no_write": false,
  "newly_published_allowlisted_source_marketplace_plugin_installable": false,
  "runtime_offline_supported": true,
  "runtime_offline_supported_platforms": ["darwin-arm64"],
  "shared_db_compatibility": "unverified",
  "stale_marketplace_catalog_revocable": false
}
```
- [ ] Pin every Action to the full commit SHA in
  `release/workflow-actions.lock.json`. Candidate build permissions are
  `contents: read`. Set `persist-credentials: false`; forbid self-hosted
  runners and secrets. Unit 7 creates the protected exact-tag workflow only
  after every fixed subject producer exists; only its attestation job may
  receive `id-token: write` and `attestations: write`.
- [ ] Build twice from two clean roots with different parent paths and require
  byte-identical deterministic fixed payload digests.
- [ ] Treat Unit 2 `--mode core-runtime` outputs as non-promotable component
  determinism evidence for the Unit 2 tree. They are not the candidate fixed
  payload set and cannot satisfy publisher states. The first promotable
  candidate set is built in `--mode candidate` from the exact frozen
  base/head/synthetic-tree decision at choreography step 13. Production
  `--mode release` runs only after merge at step 18.

Focused commands:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 mcp/.venv/bin/python -I -m pytest \
  -p no:cacheprovider --rootdir=. --import-mode=importlib \
  tools/release_bridge/tests/test_release_contracts.py \
  tools/release_bridge/tests/test_release_assets.py \
  tools/release_bridge/tests/test_core_manifest_renderer.py \
  tools/release_bridge/tests/test_release_bridge_workflow.py -q
mcp/.venv/bin/python -B scripts/validate-release-bridge-workflow.py
mcp/.venv/bin/python -B scripts/build-release-bridge.py --mode core-runtime --check-determinism
```

Expected: all exit `0`; the determinism report shows equal digest maps for two
clean roots. `--mode release` returns typed missing-role and
`CORE_MANIFEST_MISSING_OR_INCOMPLETE` blockers until Unit 8 finalizes every
subject, version, workflow, runtime route, and tracked manifest; those blockers
are expected and are not replaced with stubs. The Unit 2 result ID is
`deterministic_release_assets_verified` and binds only this component tree plus
its external canonical receipt digest.

Commit:

```bash
git commit -m "결정적 v4.32.3 Release 자산 계약을 구현한다"
```

## 8. Unit 3 — Asset-aware resumable publisher and pre-merge stable freeze guard

**Create:**

- `tools/release_bridge/publisher.py`
- `tools/release_bridge/github_remote.py`
- `tools/release_bridge/publisher_journal.py`
- `tools/release_bridge/durable_store.py`
- `tools/release_bridge/tests/test_publisher.py`
- `tools/release_bridge/tests/test_publisher_faults.py`
- `tools/release_bridge/tests/test_durable_store.py`
- `tools/release_bridge/tests/run_publisher_fixture.py`
- `tools/release_bridge/tests/fixtures/publisher/`
- `release/bridge/v4323-publisher-policy.json`
- `scripts/publish-release-bridge.py`

**Modify:**

- `scripts/publish-verified-release.py`
- `mcp/tests/test_publish_verified_release_cli.py`
- `mcp/tests/test_ci_workflow.py`

**Required public APIs:**

```python
evaluate_publish_plan(local, remote, policy)
resume_publisher(journal, local, remote, policy)
verify_fixed_subjects(index, artifacts)
verify_remote_assets(release, index)
verify_attestation_subject_set(index, bundle)
advance_publisher_state(current, observed, policy)
build_remote_mutation_request(state, identities, readiness_receipt)
validate_remote_transition_result(request, signed_external_result)
```

**Imported unchanged from Unit 0:**

```python
verify_release_freeze(metadata, policy)
verify_check_run_identity(check_run, policy)
scan_implicit_default_refs(repo_root, allowlist)
```

- [ ] RED: publisher must fail before any remote call on dirty tree, wrong
  branch, wrong base/head/tree, missing local/canonical gate, ruleset bypass,
  wrong App/check/workflow identity, implicit default ref, existing tag at a
  different peeled commit/tree, same asset name with different digest,
  published Release missing an asset, or attestation subject-set mismatch.
- [ ] Import the unchanged Unit 0 `tools.release_topology_guard.guard` contract
  for freeze/check validation. Unit 3 does not create or modify a second
  topology implementation or the protected-base workflow; tests verify the
  imported module/blob and workflow source SHA equal the externally authorized
  fuse identities.
- [ ] Implement only this exact 25-state publisher sequence, with no aliases,
  skips, backward transitions, or state inference from asset existence:

```text
LOCAL_GATES_PASSED
REMOTE_GATES_PASSED
FUSE_PR_APPROVED
MAIN_QUARANTINE_RULESET_VERIFIED
ORIGINAL_ANCHOR_AND_STAGE_R_PINNED
HOST_MATRIX_AND_STALE_PROCESS_GATE_PASSED
MAIN_FUSE_STAGE_A_APPLIED
RELEASE_BRANCH_CREATED_AND_FROZEN
OPERATIONAL_PROPAGATION_BARRIER_PASSED
DEFAULT_MAIN_LIVE_CONTAINMENT_VERIFIED
FROZEN_BASE_HEAD_TREE_PINNED
CANDIDATE_PAYLOADS_VERIFIED
PREMERGE_RUNTIME_CANARY_PASSED
RELEASE_BRANCH_MERGED_AND_PINNED
PRETAG_PAYLOADS_VERIFIED
TAG_CREATED
TAG_BUILD_COMPLETED
TAG_ARTIFACTS_VERIFIED
DRAFT_RELEASE_READY
ASSETS_UPLOADED
REMOTE_ASSETS_VERIFIED
ATTESTATION_VERIFIED
DRAFT_RUNTIME_CANARY_PASSED
RELEASE_PUBLISHED
PUBLIC_DISCOVERY_VERIFIED
```

  Journal the exact accepted local/remote identity before each advance. Add a
  table-driven test for the complete enum and adjacent allowed-transition set,
  plus rejection of every skip, rollback, unknown state, and response-loss
  ambiguity.
- [ ] Model GitHub as an injected adapter. Unit tests use fixture responses and
  a mutation log; no test may invoke real `gh`, `git push`, or GitHub writes.
- [ ] Keep `github_remote.py` credential-free and network-free: it defines
  canonical request/response schemas and pure validation only. Production
  mutation requests are executed exclusively by P3's signed GitHub
  transaction controllers. Candidate code cannot access a token, resolve
  `gh`, open the network, or declare a request successful without the signed
  external result and matching one-shot capability.
- [ ] Convert `scripts/publish-verified-release.py` into a compatibility
  wrapper that delegates exclusively to the new publisher state machine with
  an explicit reviewed policy, or exits `LEGACY_PUBLISHER_DISABLED` before any
  remote call. Remove `--allow-dirty`, `--skip-local-release-checks`, direct
  branch push, direct tag creation/push, and every `git push --no-verify`
  path. Fixture injection exists only on a private test adapter, never as a
  public unsafe flag. The public CLI explicitly rejects `--remote-fixture` and
  equivalent hidden/environment inputs. Grep and behavior tests prove there is
  no alternate mutation entrypoint.
- [ ] Verify default `main` is the approved v4.32.2 fuse while the stable branch
  is non-default, frozen at the approved bridge base/head/synthetic tree, and
  has zero broad bypass actors.
- [ ] Verify the required check is produced by the exact GitHub Actions App
  integration, repository/workflow id/path, protected workflow source SHA,
  event, run/head SHA, base/head, and synthetic merge tree.
- [ ] Create the tag only after post-merge fixed payload equality succeeds.
  Tag creation is expected-absent create-only CAS. Any response-loss retry
  re-reads the peeled tag identity before continuing.
- [ ] Create a draft Release, upload only missing identical fixed subjects,
  verify every remote digest and attestation, then stop at the draft-runtime
  canary boundary. Publication remains impossible until Unit 7/8 readiness.
- [ ] Treat an identical published Release as success/no-op. Never delete,
  replace, retag, or repair a published stable Release in place.
- [ ] Use the shared durable writer for every publisher journal/receipt and
  inject failures at temp create/write, file `fsync`, rename, parent-directory
  `fsync`, final identity recheck, and close. No failed boundary may advance
  the sequence hash or become resumable PASS.

Focused commands:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 mcp/.venv/bin/python -I -m pytest \
  -p no:cacheprovider --rootdir=. --import-mode=importlib \
  tools/release_bridge/tests/test_publisher.py \
  tools/release_bridge/tests/test_publisher_faults.py \
  tools/release_bridge/tests/test_durable_store.py \
  mcp/tests/test_publish_verified_release_cli.py -q
mcp/.venv/bin/python -B -m tools.release_bridge.tests.run_publisher_fixture \
  --fixture tools/release_bridge/tests/fixtures/publisher/resume-identical.json \
  --expect-state REMOTE_GATES_PASSED --format json
```

Expected: focused tests exit `0`; dry-run reports the next deterministic state
and a remote mutation count of zero. The Unit 3 result ID is
`publisher_resume_freeze_verified`.

Commit:

```bash
git commit -m "자산 검증형 재개 가능 publisher와 freeze guard를 구현한다"
```

## 9. Unit 4 — Claude selection adapter, current classifier, and next-session verifier

**Create:**

- `tools/release_bridge/claude_selection.py`
- `tools/release_bridge/current_classifier.py`
- `tools/release_bridge/next_session_verifier.py`
- `tools/release_bridge/bridge_guard.py`
- `tools/release_bridge/receipt_store.py`
- `tools/release_bridge/render_runtime_guard.py`
- `release/bridge/bridge-runtime-guard.py`
- `tools/release_bridge/tests/test_claude_selection.py`
- `tools/release_bridge/tests/test_current_classifier.py`
- `tools/release_bridge/tests/test_bridge_guard.py`
- `tools/release_bridge/tests/test_next_session_verifier.py`
- `tools/release_bridge/tests/test_runtime_guard_generation.py`
- `tools/release_bridge/tests/fixtures/claude-selection/`
- `release/claude-host-adapters.json`
- `scripts/release-bridge-guard.py`

**Required public APIs:**

```python
resolve_host_adapter(executable_identity, adapter_catalog)
inventory_claude_selection(invocation, adapter)
classify_marketplace_catalog(inventory, policy)
classify_topology(inventory, legacy_catalog, receipts)
verify_current_bridge(inventory, release_index, receipts)
build_selected_root_intent(pre_identity, target_identity)
verify_next_session(pending, observed, release_index)
render_guard_result(result)
```

- [ ] RED: unknown CLI/schema, custom `CLAUDE_CONFIG_DIR`, split roots,
  non-user scope, directory source, multiple candidates, foreign marketplace,
  explicit custom ref, stale installable catalog, stale process memory,
  receiptless exact bridge bytes, global MCP row, ambiguous selected root, and
  mtime-only current-root inference.
- [ ] Resolve an adapter only from exact executable/package/schema identity.
  Opaque Claude CLI is allowed only in disposable shadow fixtures, never as a
  production inventory/mutation primitive.
- [ ] Implement exact topology enums `EMPTY_READY`,
  `BRIDGE_GUARDED_CURRENT`, `BRIDGE_PENDING_OWNED`, `LEGACY_STOCK`,
  `LEGACY_KNOWN_HYBRID`, `QUARANTINE_FUSE`, `DIRECTORY_SOURCE`,
  `MULTIPLE_CANDIDATES`, `FOREIGN`, and `UNKNOWN`.
- [ ] Require `REFRESHED_PAUSE_COLD` to bind all pre-refresh Claude process and
  relevant open-FD count zero plus a new process generation. Disk-only pause
  is never `EMPTY_READY`.
- [ ] Use Unit 1's unchanged receipt taxonomy/schema for actual Claude
  successful-discovery, discovery-failure, stale-catalog, two-process
  stale-memory, pinned-source, unsupported-topology, refreshed-cold, and
  passive-no-worse observations. Unit 4 supplies the exact host adapter and
  process-generation evidence; it cannot merge risk rows or normalize them to
  PASS.
- [ ] In-session `BRIDGE_GUARDED_CURRENT` performs local verification only:
  network/temp/state-root/target/registry mutation zero, returning `CURRENT`
  only when final, accepted-version, serving, capability, and same-epoch
  admission-release receipts plus core/runtime/selection/catalog identity all
  match.
- [ ] Legacy/fuse/receiptless states return `DEFERRED_TO_V433`; directory,
  ambiguous, foreign, and unsupported states return a typed block. None may
  create a new transaction.
- [ ] Build a next-restart selected-root intent from exact pre/target registry
  digests and verify it only in a fresh process/session fixture.
- [ ] Write promotable receipts without absolute user paths; represent roots by
  typed identity/digest tokens.
- [ ] Render `release/bridge/bridge-runtime-guard.py` deterministically from the
  reviewed source modules and require `render_runtime_guard.py --check` to
  reject manual/generated drift. Unit 4 does not yet wire plugin hooks or MCP;
  Unit 7 owns that integration boundary.
- [ ] In P1's isolated prepared profile, execute the generated guard with the
  actual absolute `/usr/bin/python3 -I -S -B` and its normal containment argv,
  not a production fixture/test bypass flag. Require Python invocation one,
  project/profile write zero, and a typed closed-capability result; syntax-only
  3.12 coverage is insufficient.

Focused commands:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 mcp/.venv/bin/python -I -m pytest \
  -p no:cacheprovider --rootdir=. --import-mode=importlib \
  tools/release_bridge/tests/test_claude_selection.py \
  tools/release_bridge/tests/test_current_classifier.py \
  tools/release_bridge/tests/test_bridge_guard.py \
  tools/release_bridge/tests/test_next_session_verifier.py \
  tools/release_bridge/tests/test_runtime_guard_generation.py -q
mcp/.venv/bin/python -B -m tools.release_bridge.render_runtime_guard --check
mcp/.venv/bin/python -B scripts/release-bridge-guard.py \
  --fixture tools/release_bridge/tests/fixtures/claude-selection/bridge-current.json \
  --format json
/usr/bin/python3 -I -S -B release/bridge/bridge-runtime-guard.py \
  hook compatibility-probe
```

Expected: exact current fixture returns `CURRENT` with write/network/temp count
zero; receiptless and legacy fixtures return `DEFERRED_TO_V433`. The Unit 4
result ID is `claude_selection_current_verified`.

Commit:

```bash
git commit -m "Claude 선택 상태와 새 세션 검증기를 구현한다"
```

## 10. Unit 5 — Out-of-band authorization, supervised acquisition, registry recovery, and serving boundary

This unit is allowed to mutate only an externally authorized, single-tenant,
disposable-VM `EMPTY_READY` fixture. It never runs mutation against a real or
default Claude profile. If the external root-owned admission controller or
native authorization-verifier prerequisites are absent, implementation tests
may exercise pure/fixture code but the Unit 5 component gate remains
`BLOCKED_ENVIRONMENT`. Unit 5's commit gate is a component-level canonical
transaction proof in P0 using exact synthetic identities and the generated
guard component; it does not claim the full candidate acquisition→restart→MCP
canary. That full live candidate canary runs only after Unit 8 finalizes exact
payloads, hook/MCP wiring, versions, and core manifest, and it is a hard
prerequisite for `candidate_merge_ready`. The external receipt IDs are exactly
`unit5_component_transaction_verified` for this unit gate and
`candidate_empty_ready_acquisition_restart_mcp` for the later full live gate.

**Create:**

- `tools/release_bridge/canary_authorization.py`
- `tools/release_bridge/acquisition.py`
- `tools/release_bridge/runtime_provisioner.py`
- `tools/release_bridge/registry_transaction.py`
- `tools/release_bridge/capability_gate.py`
- `tools/release_bridge/render_acquisition_runner.py`
- `release/bridge/acquire.py`
- `native/canary-authz-verifier/main.c`
- `native/canary-authz-verifier/jcs.c`
- `native/canary-authz-verifier/jcs.h`
- `native/canary-authz-verifier/ed25519.c`
- `native/canary-authz-verifier/ed25519.h`
- `native/canary-authz-verifier/sha512.c`
- `native/canary-authz-verifier/sha512.h`
- `native/canary-authz-verifier/Makefile`
- `release/bridge/canary-authz-policy.json`
- `release/bridge/runtime-provisioning-policy.json`
- `release/native-sources.lock.json`
- `tools/release_bridge/tests/test_canary_authorization.py`
- `tools/release_bridge/tests/test_supervised_capability.py`
- `tools/release_bridge/tests/test_acquisition.py`
- `tools/release_bridge/tests/test_acquisition_policy.py`
- `tools/release_bridge/tests/test_runtime_provisioner.py`
- `tools/release_bridge/tests/test_activation_receipt_durability.py`
- `tools/release_bridge/tests/test_registry_transaction.py`
- `tools/release_bridge/tests/test_capability_gate.py`
- `tools/release_bridge/tests/test_canary_verifier_native.py`
- `tools/release_bridge/tests/fixtures/acquisition/`

**Modify:**

- `tools/release_bridge/bridge_guard.py`
- `tools/release_bridge/receipt_store.py`
- `tools/release_bridge/render_runtime_guard.py`
- `release/bridge/bridge-runtime-guard.py`
- `release/platform-policy.json`
- `scripts/build-release-bridge.py`

The tracked generated runner `release/bridge/acquire.py` is renamed by the
builder to `samvil-4.32.3-acquire.py`. The renderer must be deterministic;
manual edits to the generated file fail the gate.

**Required public APIs:**

```python
load_authorization_policy(path)
read_supervised_capability(script_fd, verification_fd, auth_pipe_fd)
validate_supervised_capability(capability, request, inventory, policy)
derive_transaction_id(authorization)
evaluate_acquisition_policy(request, current, release, accepted_version, capability)
plan_acquisition(request, inventory, release)
stage_verified_release(request, release)
plan_runtime_provision(release, staged_runtime_root, policy)
run_verified_runtime_builder(plan, builder_fd, primitives)
build_runtime_manifest(staged_runtime_root, lock, records)
verify_runtime_manifest_static(staged_runtime_root, manifest, policy)
plan_registry_transaction(pre, target, policy)
apply_registry_transaction(plan, primitives, journal)
reconcile_registry(journal, observed)
advance_capability_gate(stage, evidence, receipt_store)
restore_target_metadata(target_fd, expected_metadata, primitives, receipt_store)
finalize_activation(journal, evidence, receipt_store)
```

- [ ] RED authorization tests: wrong audience/repository/source, unknown or
  revoked key, key-epoch rollback, policy-epoch mismatch, future-issued token,
  overlong/expired token, nonce replay, wrong fixture inode/mode, wrong VM/UID,
  wrong admission-controller identity, sidecar policy widening, direct Python
  runner invocation, fake environment receipt, wrong parent, path-swapped
  runner, and extra inherited writable FD.
- [ ] Candidate Python never loads the out-of-band verifier root, resolves
  `gh` from PATH, verifies its own attestation, or turns candidate bytes into
  authorization. It consumes only the descriptor-pinned, one-shot capability
  emitted by P3 after the exact mode-specific bootstrap: component uses the
  signed P0 tree/build/control sidecar defined below, candidate uses the signed
  candidate index/control chain, and draft uses exact online/offline production
  attestation. It rechecks the bound request/repository/ref/subject-manifest or
  index/runner/native-verifier identities. Direct or path-swapped runner
  invocation has protected-scope mutation zero.
- [ ] For this unit P3 alone emits `component_canary_bootstrap_verified` and
  `component_canary_authorization_verified`. The supervised capability binds
  both receipt digests, control commit, exact `component` mode, repository,
  source, workflow, runner, verifier and policy digests, transaction/nonce,
  fixture/admission lease, and inherited-FD allowlist. Missing, malformed,
  path/environment-loaded, replayed, or candidate-authored capability permits
  bounded diagnosis only and mutation zero. Every P3 bootstrap failure proves
  Python invocation, runner invocation, and protected-scope mutation counts
  are all zero.
- [ ] Define `component` as an exact synthetic P0-only authorization schema,
  not an alias for candidate or draft. Its audience is
  `insamkwon/samvil:samvil.bridge.canary.component.v1`; it binds the exact Unit
  5 staged tree, `component_subject_manifest_sha256`, P0 environment/build
  receipt digests, external control signature, native verifier/runner/policy,
  invocation-owned disposable VM roots, dedicated UID, admission lease,
  transaction/pending/activation IDs, and exact `EMPTY_READY`. It requires
  `tag`, GitHub Release ID/index/assets, production attestation, user profile,
  and user cache fields to be absent. A component capability can emit only the
  Unit 5 component receipt chain, is never accepted by candidate/draft gates,
  and contributes no release-readiness terminal. This is a non-production test
  elaboration; the design's production `candidate-or-draft` authorization
  boundary remains unchanged.
- [ ] Use a reviewed, immutable, license-audited Ed25519 source named by
  `release/native-sources.lock.json`; do not write ad-hoc cryptography or
  substitute Python verification. The authorization schema uses RFC 8785 JCS
  and rejects floating-point values so the native bounded canonicalizer handles
  only the schema's strings, booleans, nulls, integers, arrays, and objects.
- [ ] Build a self-contained arm64 Mach-O verifier whose static load-command
  closure is exactly the policy allowlist. Reject `LC_RPATH`, weak/reexport
  dylibs, DYLD environment commands, `get-task-allow`, disabled library
  validation, unexpected entitlements, writable/plugin search paths, and
  unknown code-directory hash.
- [ ] The preinstalled release-control launcher opens the verifier and runner
  with `O_NOFOLLOW`, validates inode/nlink/mode/digest, sanitizes loader/debug
  environment, materializes no-replace private executable bytes, invokes exact
  absolute `/usr/bin/python3 -I -S -B /dev/fd/{script_fd}` only after native
  verification, and remains the parent/supervisor until the runner exits. The
  P3 component gate executes this real 3.9 path; 3.12-only tests cannot satisfy
  compatibility.
- [ ] RED acquisition tests: anything except exact authorized `EMPTY_READY`
  has protected-scope mutation zero. Pending owned state reconciles only the
  same transaction and performs no network.
- [ ] Implement this exact table-driven result before any protected-scope
  write:

| Condition | Outcome | Exact reason |
|---|---|---|
| Exact synthetic `component` authorization matches its pinned Unit 5 staged subject manifest, P0 receipts, invocation-owned fixture identities, and exact `EMPTY_READY` | `ALLOW_MUTATION` | `AUTHORIZED_EXTERNAL_COMPONENT_EMPTY_READY` |
| Exact candidate or draft authorization matches its pinned identity and exact `EMPTY_READY` | `ALLOW_MUTATION` | `AUTHORIZED_EXTERNAL_EMPTY_READY` |
| Any component/candidate/draft authorization is used by a different mode or audience | `TRUST_POLICY_BLOCK` | `AUTHORIZATION_MODE_MISMATCH` |
| Authorization channel/ref differs from the exact mode-specific pinned source | `TRUST_POLICY_BLOCK` | `CHANNEL_AUTHORIZATION_MISMATCH` |
| Component authorization contains any tag, Release/index/asset, production-attestation, user-profile, or user-cache field | `TRUST_POLICY_BLOCK` | `COMPONENT_PRODUCTION_FIELD_FORBIDDEN` |
| Pinned component subject manifest is malformed, ambiguous, or incomplete | `BLOCKED_ENVIRONMENT` | `COMPONENT_SUBJECT_MANIFEST_MALFORMED` |
| Pinned candidate/draft index is malformed, ambiguous, or incomplete | `BLOCKED_ENVIRONMENT` | `PINNED_INDEX_MALFORMED` |
| Minimum updater protocol exceeds the client protocol | `BLOCKED_ENVIRONMENT` | `MINIMUM_UPDATER_PROTOCOL_UNSUPPORTED` |
| Release epoch differs from pinned policy | `TRUST_POLICY_BLOCK` | `RELEASE_EPOCH_MISMATCH` |
| Release epoch is below the accepted high-water mark | `TRUST_POLICY_BLOCK` | `RELEASE_EPOCH_ROLLBACK` |
| Current installed version is newer | `DEFERRED_TO_V433` | `CURRENT_VERSION_NEWER` |
| Same version has different release/core/runtime identity | `TRUST_POLICY_BLOCK` | `SAME_VERSION_IDENTITY_COLLISION` |
| Repository id/name differs | `TRUST_POLICY_BLOCK` | `REPOSITORY_IDENTITY_MISMATCH` |
| Source commit/tree differs | `TRUST_POLICY_BLOCK` | `SOURCE_IDENTITY_MISMATCH` |
| Tag/ref differs | `TRUST_POLICY_BLOCK` | `TAG_IDENTITY_MISMATCH` |
| Index digest differs | `TRUST_POLICY_BLOCK` | `INDEX_IDENTITY_MISMATCH` |
| Runner digest differs | `TRUST_POLICY_BLOCK` | `RUNNER_IDENTITY_MISMATCH` |
| Same-version bytes lack final/accepted/admission receipts | `DEFERRED_TO_V433` | `RECEIPTLESS_SAME_VERSION` |
| Current version cannot be classified | `BLOCKED_USER_STATE` | `CURRENT_VERSION_UNKNOWN` |
| Pending transaction id or target differs | `RECOVERY_REQUIRED` | `PENDING_TRANSACTION_MISMATCH` |

  Every non-`ALLOW_MUTATION` row proves target/registry/selection mutation,
  accepted-version advancement, capability opening, and sibling cleanup are
  all zero. No row falls back to another release, tag, branch, index, runner,
  or raw clone.
- [ ] Stage the verified core and generated runtime in a private
  same-filesystem directory, statically verify every manifest/runtime record,
  and install the target with atomic no-replace semantics.
- [ ] Provision runtime only from the attested relocatable Python runtime,
  attested descriptor-pinned runtime builder, complete verified wheel bundle,
  MCP wheel and `mcp/runtime-requirements.lock`. In a sanitized environment run
  the exact policy-pinned equivalent of:

```text
uv pip install --python {staged_python} --target {staged_site_packages}
  --offline --no-index --find-links {verified_wheel_dir} --require-hashes
  --requirements mcp/runtime-requirements.lock --link-mode copy
  --no-cache --no-config --no-managed-python --no-python-downloads
```

  Network/dynamic PyPI/files.pythonhosted resolution, PATH builder, shared
  package cache, managed-Python download and editable install are forbidden.
  Candidate input cannot add/remove flags.
- [ ] Emit `samvil.runtime-manifest.v1` binding interpreter
  realpath/version/ABI/platform, copied runtime file digests, installed
  distribution `RECORD`, package/dependency exact set, source lock and builder
  identity. Interpreter/package files are target-owned regular `nlink=1`
  copies; reject arbitrary `.pth`, `sitecustomize.py`, `usercustomize.py`,
  symlink/hardlink/special file, unexpected executable, missing/extra RECORD or
  dependency, and manifestless/pre-existing runtime. The Python 3.9 guard
  statically verifies this manifest before any target runtime execution.
- [ ] Require a root-owned, reboot-persistent same-UID process-admission lease
  before registry mutation. Bind controller executable/policy digest, lease
  epoch, supervisor instance, boot generation, deny-policy receipt, and exact
  one-shot restart handoff into authorization and journal.
- [ ] Prove exact Claude process zero, verifier-supervised transaction tree,
  same-UID process zero outside that tree, background updater zero, writable FD
  zero on the registry inode, and armed directory-event observation before the
  registry gate.
- [ ] Apply the write gate, re-inventory writable FDs, create and seal a
  content-addressed rollback snapshot, move the original registry to an
  expected-absent sealed path, and install the target registry no-replace. Any
  race preserves snapshot, moved-original, live path, target, and temp copies
  and returns `RECOVERY_REQUIRED`.
- [ ] Implement fault-safe ordering:
  `BRIDGE_ACCEPTANCE_INTENT_DURABLE` →
  `ACCEPTED_VERSION_RECEIPT_DURABLE` → `COMMIT_RECEIPT_DURABLE` →
  `READY_TOKEN_DURABLE` →
  `SERVING_INTENT_DURABLE` → remove only the target transaction seal → restore
  original owner/group/mode/ACL/xattr/flags → fsync and durably verify
  `TARGET_METADATA_RESTORED` → `TARGET_GATE_RELEASED` → controlled tool
  serving → `TOOL_SERVING_VERIFIED` → `ADMISSION_FREEZE_RELEASED` →
  `COMMITTED`.
- [ ] Use exact durable receipt IDs
  `bridge_acceptance_intent_durable`,
  `accepted_version_receipt_durable`, `commit_receipt_durable`,
  `ready_token_durable`, `serving_intent_durable`,
  `target_metadata_restored`, `target_gate_released`,
  `tool_serving_verified`, `admission_freeze_released`, and
  `activation_committed`. `target_metadata_restored` binds target
  inode/digest, redacted full metadata projection, parent identity, prior
  receipt digest, transaction id, lease epoch, and sequence hash; no later
  receipt may exist without it.
- [ ] Metadata restore/unseal/post-restore identity failure keeps normal
  capability and admission closed, preserves the rollback snapshot and
  moved-original even after commit, and converges only by exact roll-forward
  or `RECOVERY_REQUIRED`; it never performs automatic rollback after serving
  intent.
- [ ] After accepted-version or serving-intent becomes durable, automatic
  rollback is forbidden; only exact roll-forward or `RECOVERY_REQUIRED` is
  allowed.
- [ ] Inject ENOSPC, SIGKILL, timeout, response loss, network cut,
  no-replace collision, metadata drift, held FD, registry-move-only,
  target-install-only, and every capability-stage crash. Repeated reconcile
  must converge without overwriting concurrent bytes or deleting siblings.
- [ ] Inject the shared durable-writer file `fsync`, parent-directory `fsync`,
  temp close, rename/no-replace, parent close, sequence-link, identity-recheck,
  and response-loss failures at every activation, accepted-version, commit,
  ready, serving, metadata-restored, capability, and admission receipt
  boundary. Each record links `sequence`, `prior_receipt_sha256`, and
  `record_sha256`; same-transaction reconciliation produces byte-identical
  receipt bytes and no duplicate event. A failed stage emits neither its own
  nor any later receipt. A candidate-owned component result contains only the
  digest of the external canonical receipt, never canonical PASS.

Focused commands:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 mcp/.venv/bin/python -I -m pytest \
  -p no:cacheprovider --rootdir=. --import-mode=importlib \
  tools/release_bridge/tests/test_canary_authorization.py \
  tools/release_bridge/tests/test_supervised_capability.py \
  tools/release_bridge/tests/test_acquisition.py \
  tools/release_bridge/tests/test_acquisition_policy.py \
  tools/release_bridge/tests/test_runtime_provisioner.py \
  tools/release_bridge/tests/test_registry_transaction.py \
  tools/release_bridge/tests/test_capability_gate.py \
  tools/release_bridge/tests/test_activation_receipt_durability.py \
  tools/release_bridge/tests/test_canary_verifier_native.py -q
mcp/.venv/bin/python -B -m tools.release_bridge.render_acquisition_runner --check
/usr/bin/python3 -I -S -B -c \
  'import ast,sys; ast.parse(open(sys.argv[1],"rb").read(), filename=sys.argv[1])' \
  release/bridge/acquire.py
make -C native/canary-authz-verifier verify
```

Expected: fixture/property tests exit `0`; native verifier build and static
policy verification exit `0`. The Unit 5 component canonical receipt requires
P0, the P3 out-of-band capability, reviewed keys/native policy, exact
darwin-arm64 build, and the component fault matrix. It is not the live
candidate receipt and cannot advance release readiness; the supervised actual
`EMPTY_READY` acquisition→restart→MCP canary remains mandatory after Unit 8.
The component run emits `unit5_component_transaction_verified`; the later
candidate and draft live gates emit
`candidate_empty_ready_acquisition_restart_mcp` and
`draft_empty_ready_acquisition_restart_mcp` respectively. Its signed component
receipt chain also contains exact IDs `registry_transaction_verified`,
`target_metadata_restored_component`, `capability_admission_chain_verified`,
and `activation_fault_matrix_complete`.
The later aggregate IDs are valid only when they bind their mode-prefixed
actual metadata-restored, gate-released, tool-serving, admission-released,
committed, and independent manual selected-root/MCP observation receipts.

- [ ] Fix one exact `samvil.live-canary-binding.v1` projection shared by every
  candidate and draft stage/aggregate receipt. It contains
  `os_product_version`, `os_build`, `architecture`, `python_version`,
  `python_abi`, the sorted exact `wheel_tags`, `repository_id`,
  `repository_name`, `authorization_mode`, `source_ref`, `source_commit`,
  `source_tree`, `workflow_run_id`, `workflow_run_attempt`,
  `workflow_source_sha`, the sorted exact `asset_subjects` entries of
  `{asset_id, name, sha256, size}`, `claude_executable_sha256`,
  `claude_package_identity`, `claude_schema_version`, `fixture_vm_identity`,
  `dedicated_uid`, `admission_lease_id`, `boot_generation`, `transaction_id`,
  `pending_id`, `activation_id`, `target_core_manifest_sha256`,
  `target_core_tree_sha256`, `runtime_manifest_sha256`,
  `runtime_interpreter_sha256`, `runtime_module_set_sha256`,
  `selected_root_sha256`, `mcp_startup_receipt_sha256`,
  `mcp_serving_receipt_sha256`, and `manual_mcp_observation_sha256`.
  Candidate mode additionally requires `candidate_index_sha256` and the exact
  candidate asset set while requiring `tag`, `release_id`,
  `release_index_sha256`, and production-attestation IDs to be absent. Draft
  mode requires exact `tag=v4.32.3`, `release_id`, `release_index_sha256`, the
  exact pre-canary uploaded Release asset IDs/digests, online attestation ID,
  and detached provenance asset ID/digest. The future draft-canary receipt
  asset must be absent from this base binding so a stage never depends on its
  own not-yet-produced aggregate receipt.
  Missing, extra, mode-incompatible, stale, or unequal binding fields reject
  the stage before it can contribute to readiness.
- [ ] After every required draft stage/manual observation receipt exists, P3
  verifies that exact causal set and signs
  `draft_empty_ready_acquisition_restart_mcp` as the aggregate draft canary
  receipt A. Only then may the upload controller upload receipt A itself under
  the fixed expected-absent canary-receipt asset name and read it back. After
  that remote asset ID/digest is known and verified, P3 creates
  `samvil.draft-canary-publication-binding.v1` receipt B, which binds the
  immutable base canary-binding digest, receipt A digest, exact uploaded
  canary-receipt asset `{asset_id, name, sha256, size}`, tag/Release/index
  identity, prior remote asset-set digest, upload-controller result, and
  read-back verification. `draft_canary_receipt_uploaded` and
  `draft_canary_receipt_verified` bind receipt B; receipt B is not the uploaded
  asset and no underlying canary stage/aggregate receipt contains or depends on
  either later ID. `publish_ready` requires verified receipt B, thereby
  preserving a strictly acyclic receipt graph.

Commit:

```bash
git commit -m "승인 기반 bridge 획득과 복구 트랜잭션을 구현한다"
```

## 11. Unit 6 — True no-write Codex check and verified-source guard

**Create:**

- `scripts/codex-install-preflight.py`
- `mcp/tests/test_codex_install_preflight.py`
- `mcp/tests/fixtures/release-bridge/codex-preflight/`

**Modify:**

- `scripts/setup-codex.sh`

**Required public APIs:**

```python
build_check_report(repo_root, home, codex_home)
classify_install_source(source_root, source_index, evidence_bundle, mode)
verify_preflight_source_identity(script_path, release_index)
write_report_explicit(path, report)
```

The stdout receipt contains exactly one JSON object with at least:

```json
{
  "authority": "candidate_corroboration",
  "canonical_pass": false,
  "install_allowed": false,
  "local_result": "NO_MUTATION_OBSERVED",
  "pre_post_digest_equal": true,
  "receipt_id": "codex_preflight_report",
  "reported_external_mutator_processes": 0,
  "reported_network_connect_events": 0,
  "reported_write_events": 0,
  "schema_version": "samvil.codex-check.v1",
  "source_class": "verified_stable"
}
```

- [ ] Move mode dispatch to the top of `scripts/setup-codex.sh`, before the
  banner, `command -v`, `curl`, `uv`, `cd`, `mkdir`, venv/import smoke, temp
  helper, or profile access.
- [ ] For `--check`, use shell builtins and `${BASH_SOURCE[0]}`/`$PWD` only to
  derive the setup script's absolute lexical repository root and preflight path
  before any CWD change; do not invoke `cd`, `dirname`, `readlink`, an external
  `pwd`, or PATH lookup. Invoke exact absolute `/usr/bin/python3 -I -S -B` once
  with a reviewed stdlib-only descriptor loader and the pinned preflight
  digest. The loader walks absolute path components with no-follow semantics,
  rejects symlink or group/world-writable components, opens a regular
  `nlink=1` source descriptor, verifies the digest, and executes only those
  descriptor-pinned bytes. Path relookup after verification is forbidden.
- [ ] Test repository-root, `scripts/`, and unrelated outside CWD; absolute and
  relative setup invocation; hostile same-name relative file; sourced shell;
  symlink/path replacement; poisoned PATH/Python variables; and setup or
  preflight digest drift. Bind both source digests into candidate and external
  receipts, and require Unit 8 equality with the final tracked core manifest.
- [ ] Stdout is exactly one JSON object. `--save-report PATH` is the only
  candidate write exception and may write only the caller-selected path.
- [ ] RED: trap `uv`, Git, `gh`, curl, mktemp, package managers, hostile
  `sitecustomize.py`, `usercustomize.py`, `.pth`, poisoned PATH, import-time
  side effects, and background mutators; require invocation count zero.
- [ ] Capture event evidence as well as before/after digests so create-delete
  and write-restore attempts cannot masquerade as no-write.
- [ ] Treat the candidate self-check and Merkle comparison as secondary
  evidence. P3's external `observe-codex-no-write.py` descriptor-pins the setup
  and preflight bytes, enforces deny-write/deny-network/process supervision,
  records syscall/filesystem/network events, and alone emits the authoritative
  mode-scoped receipt. Candidate code may not promote
  its own stdout to canonical PASS.
- [ ] Split external evidence planes and IDs. Focused fixtures emit only
  `codex_no_write_fixture` and `codex_source_guard_fixture` and are never
  promotable. At choreography step 13, rerun against the exact Unit 8
  SHA/tree, tracked core-manifest digest and candidate index/control signature
  to emit `candidate_codex_no_write_external` and
  `candidate_codex_verified_source_guard`; candidate mode does not require
  production SLSA. After tag assets/online+offline production attestation are
  available, draft mode emits `draft_codex_no_write_external` and
  `draft_codex_verified_source_guard`. A candidate `source_class` string or
  earlier fixture/tree cannot satisfy any external ID.
- [ ] Require repository, isolated `HOME`, isolated `CODEX_HOME`, temp root,
  and fixture project Merkle equality; require network connect event zero and
  external mutator process zero.
- [ ] Classify install sources as `verified_stable`, `verified_cache`,
  `working_checkout`, or `unknown`. Only exact index+attestation-verified
  stable/cache inputs pass the source boundary.
- [ ] Working checkout use requires the exact pair `--dev --from-local`; either
  flag alone blocks before `uv`. The receipt marks
  `source_class=dev_local_unstable`.
- [ ] Bridge v4.32.3 does not add production Codex native activation. A verified
  source may be inspected/staged for release engineering, but user profile
  activation remains deferred to v4.33.
- [ ] Canonical observation runs without `--save-report` and executes twice.
  Require distinct signed envelope/run IDs, observer instance/process-tree
  identities and monotonic sequences, while the normalized observation
  projection—candidate/source/tree/policy, zero counters, Merkle roots and
  result—is identical. Byte-identical whole envelopes or replay of one receipt
  fails. Separate fault tests prove
  `--save-report PATH` can mutate only the exact caller-selected path and
  handles symlink, collision, file/parent `fsync`, close, and response loss
  without touching siblings. Create-delete, write-restore, detached/delayed
  child, and network-connect attempts fail even when final Merkle roots match.

Focused commands:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 mcp/.venv/bin/python -I -m pytest \
  -p no:cacheprovider --rootdir=. --import-mode=importlib \
  mcp/tests/test_codex_install_preflight.py -q
{trusted_control_root}/mcp/.venv/bin/python -B \
  {trusted_control_root}/tools/release-control/observe-codex-no-write.py \
  --candidate-root {candidate_root} \
  --setup scripts/setup-codex.sh \
  --fixture mcp/tests/fixtures/release-bridge/codex-preflight/verified-stable \
  --repeat 2 --format json
```

Expected: tests exit `0`; each candidate invocation prints one corroborating
JSON object and the P3 observer emits two distinct signed fixture envelopes
with identical normalized zero-event/process/connect projections under
`codex_no_write_fixture` plus `codex_source_guard_fixture`. Never substitute
the real `$CODEX_HOME` for an invocation-owned observer path.

Commit:

```bash
git commit -m "Codex 무변경 점검과 검증된 설치 소스 경계를 추가한다"
```

## 12. Unit 7 — Fault matrix, topology evidence, runtime wiring, and release-check integration

Unit 7 aggregates and wires existing Unit 1–6 contracts. It must not create a
second topology implementation; Unit 0's protected-base
`tools.release_topology_guard.guard` evaluator and workflow remain the single
remote topology authority, while Unit 3's publisher consumes their signed
result.

**Create:**

- `tools/release-control/run-bridge-release-checks.py`
- `tools/release-control/tests/test_bridge_release_control.py`
- `release/bridge/v4323-fault-scenarios.json`
- `release/bridge/v4323-readiness-policy.json`
- `mcp/tests/test_release_bridge_runtime_wiring.py`
- `mcp/tests/test_release_bridge_receipts.py`
- `.github/workflows/release-bridge.yml`

**Modify:**

- `.claude-plugin/plugin.json`
- `.mcp.json`
- `.github/workflows/release-checks.yml`
- `.github/workflows/release-bridge-build.yml`
- `scripts/validate-ci-workflow.py`
- `mcp/tests/test_ci_workflow.py`

`mcp/samvil_mcp/release.py`, `scripts/run-release-checks.py`, and
`scripts/build-release-bundle.py` remain the app release-readiness path with
unchanged default semantics. Bridge aggregation emits a separate
`.samvil/bridge-release-checks.json` and is consumed explicitly by the bridge
publisher/readiness policy.

**Required public APIs:**

```python
load_unit_receipts(paths)
verify_receipt_chain(receipts, policy)
verify_fault_scenario_exact_set(results, policy)
verify_runtime_guard_wiring(plugin_manifest, mcp_manifest, expected_records, manifest_policy)
verify_tracked_runtime_guard_wiring(repo_root, tracked_core_manifest)
build_bridge_release_check_report(inputs, policy)
```

- [ ] Fix the exact `candidate_merge_ready` receipt-ID set in
  `release/bridge/v4323-readiness-policy.json` before Unit 8 exists:

```text
unit_0_canonical_gate
unit_1_canonical_gate
unit_2_canonical_gate
unit_3_canonical_gate
unit_4_canonical_gate
unit_5_canonical_gate
unit_6_canonical_gate
unit_7_canonical_gate
unit_8_canonical_gate
legacy_ledger_materialization
legacy_host_matrix_complete
legacy_successful_discovery_no_write
legacy_discovery_failure_risk
stale_catalog_risk
stale_host_memory_risk
pinned_source_risk
host_topology_risk
refreshed_pause_cold
fixture_passive_only_no_worse
fixture_semantic_fuse_or_unknown_rejection
deterministic_release_assets_verified
publisher_resume_freeze_verified
claude_selection_current_verified
component_canary_bootstrap_verified
component_canary_authorization_verified
candidate_canary_bootstrap_verified
candidate_canary_authorization_verified
unit5_component_transaction_verified
registry_transaction_verified
target_metadata_restored_component
capability_admission_chain_verified
activation_fault_matrix_complete
codex_preflight_report
candidate_codex_no_write_external
candidate_codex_verified_source_guard
runtime_guard_wiring_verified
bridge_fault_matrix_complete
limitations_exact
original_anchor_and_stage_r_commit_pinned
stage_r_rehearsal_verified
live_stage_a_verified
external_default_monitor
external_claude_host_watcher
external_rollout_kill_switch
main_fuse_live_containment
release_branch_created_and_frozen
operational_propagation_barrier_passed
frozen_base_head_tree_pinned
candidate_payloads_verified
candidate_target_metadata_restored
candidate_target_gate_released
candidate_tool_serving_verified
candidate_admission_freeze_released
candidate_activation_committed
candidate_manual_selected_root_mcp_observed
candidate_empty_ready_acquisition_restart_mcp
```

  Missing, extra, duplicate, merged, renamed, or candidate-self-asserted
  external IDs fail. Any actual `SEMANTIC_FUSE_OR_UNKNOWN`, stale/dead monitor,
  triggered kill switch, core-manifest blocker, or missing Unit 8 receipt keeps
  readiness blocked. `fixture_semantic_fuse_or_unknown_rejection` is a required
  negative fixture proving rejection, not a positive live receipt;
  `fixture_passive_only_no_worse` is likewise the required allowed-residual
  fixture, while the actual live subtype is carried by
  `stale_host_memory_risk`.
- [ ] The readiness policy contains an exact per-ID map of schema version,
  `evidence_plane` (`portable_fixture`, `canonical_p0`, `live_candidate`,
  `remote_topology`, or `draft_tag_assets`), candidate-vs-external authority,
  signer/control root, subject/ref/tree/process bindings, freshness window, and
  required predecessor receipt digests. An ID match alone is insufficient;
  plane/authority/freshness/dependency mismatch fails.
- [ ] Fix `tag_ready` as exactly the complete `candidate_merge_ready` set plus
  these additional IDs—no aliases, category expansion, omission, or extra ID:

```text
release_branch_merge_pinned
live_explicit_release_matrix_verified
pretag_payloads_verified
postmerge_topology_rulesets_verified
tag_create_authorization_ready
```

  Every added ID causally depends on the signed `candidate_merge_ready`
  receipt digest and the exact frozen release SHA/tree. The tag authorization
  also binds expected absence of `refs/tags/v4.32.3`, the tag ruleset, and the
  one-shot create-only controller capability.
- [ ] Fix `publish_ready` as exactly the complete `tag_ready` set plus these
  additional IDs—again with no aliases, category expansion, omission, or
  extra ID:

```text
tag_created
tag_build_completed
tag_artifacts_verified
draft_release_ready
assets_uploaded
remote_assets_verified
attestation_online_verified
attestation_offline_verified
detached_provenance_uploaded
detached_provenance_verified
draft_canary_receipt_uploaded
draft_canary_receipt_verified
draft_canary_bootstrap_verified
draft_canary_authorization_verified
draft_codex_no_write_external
draft_codex_verified_source_guard
draft_target_metadata_restored
draft_target_gate_released
draft_tool_serving_verified
draft_admission_freeze_released
draft_activation_committed
draft_manual_selected_root_mcp_observed
draft_empty_ready_acquisition_restart_mcp
external_default_monitor_fresh_for_publish
external_claude_host_watcher_fresh_for_publish
external_rollout_kill_switch_clear_for_publish
```

  Every added ID causally depends on the signed `tag_ready` digest, exact
  immutable tag/source/tree, Release/index identity, and complete fixed asset
  subject set. Draft canary IDs also bind the exact
  `samvil.live-canary-binding.v1` projection defined in Unit 5. The three
  publish-fresh external IDs are newly signed observations—not renamed copies
  of candidate-era receipts—and each binds its predecessor observation plus a
  policy-valid timestamp/window. A later terminal contains all earlier
  evidence and cannot be selected by candidate input.
- [ ] `external_default_monitor` binds repository/default/ref/SHA/tree,
  main/release rulesets, required-check producer, bypass/admin inventory,
  GitHub App identity, webhook/poll freshness, and kill-switch observation.
  `external_claude_host_watcher` binds exact executable/package/schema and every
  semantic/platform class. `external_rollout_kill_switch` requires
  `armed=true`, `triggered=false`.
- [ ] Keep normal and emergency ref evidence distinct:
  `original_anchor_and_stage_r_commit_pinned` proves the immutable original
  anchor plus the pre-reviewed parent=fuse/tree=original restoration commit;
  `stage_r_rehearsal_verified` proves only disposable-mirror response-loss and
  recovery semantics; `live_stage_a_verified` proves the actual expected-old
  main→fuse transaction and relock. A real `stage_r_executed` is incident-only,
  invalidates all readiness terminals, triggers the kill switch, and cannot be
  substituted by the rehearsal receipt.
- [ ] Verify every external receipt through its external signature/control
  chain. Candidate unit results contain only external receipt digests and can
  never satisfy an external ID or assert its PASS.
- [ ] Fix `release/bridge/v4323-fault-scenarios.json` to an exact set covering
  publisher tag/workflow/draft/asset/attestation/publish fail-once and response
  loss; registry gate/seal/move/install/FD/metadata races; every
  acceptance→admission-release durability boundary; topology/ruleset/check
  identity drift; and Codex no-write/source-guard failures. The publisher
  scenario-ID subset is exactly:

```text
publisher_tag_create_matrix
publisher_tag_workflow_matrix
publisher_draft_create_matrix
publisher_fixed_subject_upload_matrix
publisher_detached_provenance_matrix
publisher_remote_verification_matrix
publisher_draft_canary_receipt_matrix
publisher_publish_matrix
publisher_public_discovery_matrix
```

  Each create/publish matrix has exactly
  `before_request_fail_once`,
  `after_request_before_remote_commit_fail_once`,
  `after_remote_commit_before_response_fail_once`, and
  `success_response_loss` trial keys. The exact-tag workflow is triggered only
  by immutable tag creation; no controller dispatch action exists.
  `publisher_tag_workflow_matrix` therefore has exactly
  `run_lookup_before_request_fail_once`,
  `run_lookup_after_request_before_run_id_fail_once`,
  `run_lookup_success_response_loss`, `run_lookup_zero_match`,
  `run_lookup_multiple_match_ambiguity`, `poll_before_request_fail_once`,
  `poll_transient_failure`, `poll_queued_null_conclusion_retry`,
  `poll_in_progress_null_conclusion_retry`, `poll_success_response_loss`,
  `poll_bounded_timeout`, `completed_run_failure_conclusion`,
  `completed_run_cancelled_conclusion`,
  `completed_run_timed_out_conclusion`,
  `completed_run_null_conclusion`, `completed_run_unknown_conclusion`,
  `completed_run_other_non_success_conclusion`, and
  `completed_run_identity_mismatch`. Every lookup binds the exact tag,
  workflow ID/path/source SHA, event, repository, run ID/attempt, head SHA,
  status, conclusion, creation/update timestamps, and expected artifact
  subject set; the publisher never dispatches or reruns the workflow itself.
  Zero-match and transient poll results may retry only within the
  policy-pinned deadline/attempt budget. Exact `status=queued` or
  `status=in_progress` with `conclusion=null` is likewise a nonterminal bounded
  retry, never success or immediate failure. Exhaustion emits
  `BLOCKED_ENVIRONMENT/TAG_WORKFLOW_OBSERVATION_TIMEOUT`; multiple matching runs
  emit `TRUST_POLICY_BLOCK/TAG_WORKFLOW_RUN_AMBIGUOUS`. Only exact
  `status=completed` plus `conclusion=success` and matching identity can emit
  `tag_build_completed`. Conclusion is evaluated only when status is
  `completed`; completed `failure`, `cancelled`, `timed_out`, null, unknown, or
  any other non-success conclusion emits
  `TRUST_POLICY_BLOCK/TAG_WORKFLOW_NON_SUCCESS` and cannot dispatch, rerun, or
  advance the publisher. Any other status/conclusion combination emits
  `TRUST_POLICY_BLOCK/TAG_WORKFLOW_STATUS_CONCLUSION_MISMATCH`.
- [ ] Define `publisher_fixed_subject_upload_matrix` as the exact Cartesian
  product of Unit 2's sorted fixed-subject keys (`name@sha256`) and trial keys
  `before_request_fail_once`,
  `after_request_before_remote_commit_fail_once`,
  `after_remote_commit_before_response_fail_once`,
  `success_response_loss`, and `same_name_digest_collision`. Missing/extra
  subjects or trials fail; one aggregate asset test cannot stand in for this
  product.
- [ ] Give `publisher_detached_provenance_matrix` the four upload trial keys
  above plus `lookup_transient_failure`, `lookup_response_loss`, and
  `lookup_identity_mismatch`. Give `publisher_remote_verification_matrix`
  exactly the asset-digest, online-attestation, and offline-attestation cross
  product with `lookup_transient_failure`, `lookup_response_loss`, and
  `subject_identity_mismatch`. Give
  `publisher_draft_canary_receipt_matrix` the four upload keys plus
  `same_name_digest_collision`, `lookup_transient_failure`,
  `lookup_response_loss`, and `lookup_identity_mismatch`.
- [ ] Give `publisher_public_discovery_matrix` exactly
  `before_request_fail_once`, `success_response_loss`,
  `reconcile_identical`, and `reconcile_identity_mismatch`. Every
  response-loss trial reads back and proves the exact remote identity before
  resuming; discovery reconciliation accepts only the already-published,
  byte-identical tag/index/assets/attestation projection.
- [ ] Require each nested trial result—not merely its scenario aggregate—to
  bind input identity, exact `injected_boundary`, fixed subject when
  applicable, observed state, preserved-copy set, mutation count, terminal
  result, and repeat/reconcile result. Missing or extra scenario IDs, subject
  keys, or trial keys fail.
- [ ] Unit 7 is P1's sole candidate activation exception. Its external unit
  authorization may contain only semantic roles
  `generated_verifier_first_hook` and `canonical_guarded_mcp_route`, with exact
  paths/digests fixed by the command manifest and valid only on the bridge
  candidate/release ref. Reject legacy updater/sync, raw shell/Python hooks,
  unguarded MCP, extra hook/tool roles, role/path substitution, and the same
  guarded bytes projected onto remote default `main`, which must remain the
  passive Unit 0 fuse.
- [ ] Wire every production plugin hook through the generated verifier-first
  runtime guard. No hook may directly invoke unverified shell/Python logic.
- [ ] Make `.mcp.json` use the canonical verifier-first MCP route. Before
  `SERVING_INTENT_DURABLE`, the process advertises only attestation capability;
  normal public/stateful tools remain closed.
- [ ] Machine-check every hook/MCP route against the generated expected-record
  set, manifest policy, and generated guard digest. Direct-entry bypass is a
  hard failure. At Unit 7, the tracked core manifest intentionally does not yet
  exist; component tests render an invocation-owned expected manifest solely
  for path/role/digest linkage and never track, persist as release evidence, or
  insert it into an asset. Structural/runtime wiring tests may pass, but the
  aggregate release report and protected exact-tag workflow must remain
  `CORE_MANIFEST_MISSING_OR_INCOMPLETE`/`BLOCKED_ENVIRONMENT`. Unit 8 performs
  the sole tracked regeneration and reruns the unchanged verifier/aggregator
  against the final manifest.
- [ ] Update workflows to use explicit refs and locked full-SHA actions. The
  portable contract suite remains labelled portable and cannot set bridge
  canonical PASS.
- [ ] Create `.github/workflows/release-bridge.yml` as the protected exact-tag
  builder/attester only: exact `refs/tags/v4.32.3`, trusted GitHub-hosted
  runner, locked full-SHA Actions, `contents: read`, and narrowly scoped
  `id-token: write`/`attestations: write` only in the attestation job. It never
  chooses a source branch, pushes refs, publishes a Release, uses secrets in
  candidate jobs, or tolerates the Unit 7 core-manifest blocker.
- [ ] Aggregate Unit 0's protected topology-guard receipt together with Unit
  3's publisher freeze receipt rather than reimplementing either contract.
  Verify the exact check-run App/workflow/base/head/synthetic-tree identity
  before accepting them.
- [ ] Render separate non-authoritative structural evaluations for
  `candidate_merge_ready`, `tag_ready`, and `publish_ready`. Only P3
  `verify-bridge-readiness.py` emits the signed terminal; missing live
  canary/P0 evidence is `BLOCKED_ENVIRONMENT`, even when every fixture test is
  green.
- [ ] `candidate_merge_ready` additionally requires the P3 bootstrap,
  ref-controller, external default monitor, external Claude watcher,
  kill-switch, authoritative Codex observer, exact remote main fuse/stable
  freeze receipts, and the post-Unit-8 full live candidate
  `EMPTY_READY` acquisition→complete restart→actual MCP receipt. Unit 7's own
  commit cannot synthesize or waive these future receipts.
- [ ] `candidate_empty_ready_acquisition_restart_mcp` must causally bind the
  prior receipt digests for `operational_propagation_barrier_passed`,
  `main_fuse_live_containment`, `release_branch_created_and_frozen`,
  `frozen_base_head_tree_pinned`, and `candidate_payloads_verified`, plus the
  exact candidate index/authorization. Mere coexistence or an earlier canary
  with the same version is rejected as stale evidence.
- [ ] The same live aggregate must bind the actual transaction's externally
  observed `candidate_target_metadata_restored`,
  `candidate_target_gate_released`, `candidate_tool_serving_verified`,
  `candidate_admission_freeze_released`, `candidate_activation_committed`, and
  independent `candidate_manual_selected_root_mcp_observed` receipts. Unit 5
  component receipts or a self-reported aggregate cannot replace any live
  stage.
- [ ] Carry Unit 2's exact `limitations` object unchanged into the bridge
  report and readiness receipts; missing/unknown/different limitations block
  every readiness terminal.

Focused commands:

```bash
mcp/.venv/bin/python -B tools/release-control/tests/test_bridge_release_control.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 mcp/.venv/bin/python -I -m pytest \
  -p no:cacheprovider --rootdir=. --import-mode=importlib \
  mcp/tests/test_release_bridge_runtime_wiring.py \
  mcp/tests/test_release_bridge_receipts.py \
  mcp/tests/test_ci_workflow.py -q
mcp/.venv/bin/python -B scripts/validate-ci-workflow.py
```

Expected: all exit `0`; fixture report can be structurally green but its
release terminal remains `BLOCKED_ENVIRONMENT` until canonical/live receipts
exist. Structural results use exact IDs `runtime_guard_wiring_verified`,
`bridge_fault_matrix_complete`, and `limitations_exact`; none is an
authoritative readiness terminal.

Commit:

```bash
git commit -m "bridge fault matrix와 release-control 통합을 완성한다"
```

## 13. Unit 8 — Default-main holdback, v4.32.3 synchronization, and release readiness

**Create:**

- `docs/releases/v4.32.3-holdback.md`
- `docs/releases/v4.32.3-release-runbook.md`
- `scripts/validate-release-version.py`
- `mcp/tests/test_release_bridge_version.py`
- `mcp/tests/test_release_bridge_docs.py`
- `.samvil-release/core-manifest.json`

**Modify:**

- `README.md`
- `CLAUDE.md`
- `CHANGELOG.md`
- `.claude-plugin/plugin.json`
- `release/version-domains.json`
- `release/bridge/bridge-runtime-guard.py`

- [ ] RED: bridge tree with any bridge-owned version/asset name other than
  `4.32.3`; quarantine fuse/legacy row changed away from `4.32.2`; README or
  runbook suggesting raw marketplace update, `/samvil:update` as safe
  transition, `git pull && setup-codex.sh` as stable install, unchecked latest,
  pipe-to-shell, implicit default clone/ref, or bridge adoption for existing
  users.
- [ ] Finalize the bridge plugin, README/docs, tracked core manifest, and
  version-domain phase at exact `4.32.3`; verify the already-owned
  index/assets/policies at that identity. Reverify—but do not first create or
  silently rewrite—the MCP package/`__version__`/wheel/lock domain established
  at `4.32.3` by Unit 2.
- [ ] Preserve the default-main fuse manifest, original/fuse catalog rows, and
  holdback identity at exact `4.32.2`.
- [ ] Remove the externally authorized pre-final plugin exception from
  `release/version-domains.json` and verify Unit 2's unchanged
  `hooks/validate-version-sync.sh`; do not rewrite the MCP locks, platform
  policy, limitations SSOT, release builder/publisher, or Unit 7 readiness
  policy. Unit 8 supplies the already-required evidence and cannot weaken its
  own gate.
- [ ] Regenerate `release/bridge/bridge-runtime-guard.py` with Unit 4's
  unchanged deterministic renderer solely to bind the final plugin/version
  identity. The generated semantic-role set and guarded hook/MCP behavior must
  remain byte-for-byte equivalent apart from explicitly version-bound records;
  any broadened role requires returning to Unit 7 and fresh authorization.
- [ ] Regenerate the tracked core manifest explicitly after every final
  bridge-owned file/version change, then verify rather than auto-repair it.
  Use Unit 2's dedicated renderer with an external expected-absent or exact
  current-digest authorization; never hand-edit JSON or let the Release builder
  write it. After final generation, any other tracked byte change invalidates
  authorization and requires a new explicit render followed by `--check`.
- [ ] Document the honest user result: existing v4.32.2 installs remain
  unchanged; new default marketplace installation is paused; v4.32.3 is a
  controlled release-engineering bridge; existing-user migration remains the
  later v4.33 bootstrap.
- [ ] Lock Korean copy with snapshot/scanner tests stating that every Claude
  window and background process started before refresh must be fully
  terminated; a stale process may retain the old installable marketplace
  entry; raw marketplace install/update is prohibited during the holdback; and
  only a newly started cold process after confirmed quiescence may be used for
  the controlled canary. Existing users remain unchanged/deferred.

  Exact snapshot paragraph:

  > v4.32.3 controlled canary를 시작하기 전에 refresh 이전에 실행된 모든
  > Claude 창과 백그라운드 프로세스를 완전히 종료하고, 관련 open FD가
  > 0인지 확인해야 합니다. 디스크의 marketplace 목록이 비어 있어도 기존
  > 프로세스는 예전 SAMVIL 설치 가능 항목을 메모리에 보관할 수 있습니다.
  > raw `claude plugin install`, `claude plugin update`, marketplace 설치 또는
  > 업데이트를 실행하지 마세요. 완전한 quiescence가 확인된 뒤 새로 시작한
  > cold process에서만 승인된 canary를 수행합니다. 기존 v4.32.2 사용자의
  > 설치, cache, selection, settings, MCP 등록은 자동으로 전환·수정·삭제되지
  > 않으며, 공식 v4.33 bootstrap까지 그대로 유지되거나 defer됩니다.
- [ ] Render the exact Unit 2 `limitations` object into the Release index,
  readiness receipts, holdback document, and Korean user-facing summary. Doc
  tests reject missing, softened, contradictory, or unsupported claims such as
  transactional legacy update, revocable stale catalogs, user-supported
  bridge acquisition, Codex native migration, or verified shared-DB
  compatibility.
- [ ] Fail docs that omit termination of every pre-refresh window/background
  process or open-FD zero, imply disk refresh clears process-local memory,
  recommend raw marketplace install/update, reuse an old process for canary,
  or imply existing users are migrated/repaired.
- [ ] Write the exact release runbook with approvals and stop conditions for
  Stage A, Stage R, stable-branch creation/freeze, bridge merge, candidate
  canary, tag creation, draft assets, draft canary, publish, public smoke,
  integration branch creation, and PR #13 rebase/retarget.
- [ ] Require three independent readiness terminals:
  `candidate_merge_ready`, `tag_ready`, and `publish_ready`. A portable test or
  missing live receipt cannot advance a later terminal.
- [ ] Run version/doc scanners against all tracked shell, Markdown, JSON, YAML,
  TOML, and Python release surfaces. Explicit fixture/negative-test allowlists
  must be path- and token-specific.

Focused commands:

```bash
mcp/.venv/bin/python -B -m tools.release_bridge.render_core_manifest \
  --policy release/core-manifest-policy.json \
  --output .samvil-release/core-manifest.json \
  --generate --expected-absent
mcp/.venv/bin/python -B -m tools.release_bridge.render_core_manifest \
  --policy release/core-manifest-policy.json \
  --output .samvil-release/core-manifest.json --check
mcp/.venv/bin/python -B scripts/validate-release-version.py
bash hooks/validate-version-sync.sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 mcp/.venv/bin/python -I -m pytest \
  -p no:cacheprovider --rootdir=. --import-mode=importlib \
  mcp/tests/test_release_bridge_version.py \
  mcp/tests/test_release_bridge_docs.py \
  tools/release_bridge/tests \
  tools/release-control/tests/test_bridge_release_control.py -q
mcp/.venv/bin/python -B scripts/build-release-bridge.py \
  --mode core-runtime --check-determinism
mcp/.venv/bin/python -B scripts/build-release-bridge.py \
  --mode candidate --expect-blocker REMOTE_CANDIDATE_EVIDENCE_MISSING
/usr/bin/python3 -I -S -B release/bridge/bridge-runtime-guard.py \
  hook compatibility-probe
/usr/bin/python3 -I -S -B -c \
  'import ast,sys; ast.parse(open(sys.argv[1],"rb").read(), filename=sys.argv[1])' \
  release/bridge/acquire.py
```

Expected: render/check, version/doc/final-tree determinism and actual system
Python compatibility checks exit `0`; candidate mode reaches only the exact
missing-remote-evidence blocker. Readiness remains honest: only P3 terminals
with complete canonical/live evidence may report PASS.

The Unit 8 handoff does not immediately run a live canary. Only after release
choreography steps 5–12 have established quarantine/rulesets, propagation,
live-main containment, and the frozen fuse/base/head/synthetic tree may step 13
build `--mode candidate` payloads in two clean roots and emit
`candidate_payloads_verified`. Step 14 then runs the full externally supervised
candidate `EMPTY_READY` acquisition→complete Claude restart→new-session
selected-root→actual MCP canary on the exact supported darwin-arm64 OS build.
The authorization and receipt bind every step 11–13 prior digest. This is a
separate live evidence plane, not Unit 5's component fixture and not a portable
test. Only then may the external readiness verifier advance
`candidate_merge_ready`; failure invalidates the candidate payload/receipt pair
and requires a new reviewed tree.

Commit:

```bash
git commit -m "v4.32.3 holdback 문서와 최종 release readiness를 고정한다"
```

## 14. Design acceptance-criteria coverage

| Design AC | Owning units and proof |
|---|---|
| AC-1 Dual-branch quarantine topology | Unit 0 fuse identity; Unit 3 freeze guard; Unit 7 exact runtime/topology aggregation |
| AC-2 Straggler containment | Unit 0 passive/default no-write; Unit 1 exact signed-ledger taxonomy/matrix; Unit 4 cold/stale host evidence; Unit 7 exact independent risk receipt set |
| AC-3 Verified stable artifact | Unit 2 fixed deterministic subjects; Unit 5 verified acquisition; Unit 7 attestation aggregation |
| AC-4 No in-place future update | Unit 4 read-only in-session classifier; Unit 5 external-only target transaction |
| AC-5 No automatic cache deletion | Unit 0 passive fuse; Unit 4 topology blocks non-empty/ambiguous states; Unit 5 preserved-copy invariants |
| AC-6 Idempotent update | Unit 3 publisher resume; Unit 4 current/pending classification; Unit 5 reconcile and repeat `CURRENT` |
| AC-7 Fail-closed collision | Unit 2 archive/runtime collision checks; Unit 4 selection ambiguity; Unit 5 no-replace transaction |
| AC-8 True no-write check | Unit 6 candidate corroboration plus P3 authoritative deny-write/network observer and verified-source receipt |
| AC-9 Resumable publisher | Unit 3 full remote fault/response-loss matrix |
| AC-10 Actual Claude selection | Unit 4 selected-root/new-session proof; Unit 5 component transaction; Unit 7 guarded runtime wiring; post-Unit-8 full live candidate and draft canaries |
| AC-11 Honest limitation | Unit 2 exact limitations SSOT/index schema; Unit 7 unchanged receipt carry; Unit 8 Korean snapshot/holdback rendering |
| AC-12 Integration handoff | Unit 8 runbook and Release choreography steps 24–25 |
| AC-13 Supported acquisition separation | Unit 4 lane/topology classifier; Unit 5 out-of-band authorized external acquisition only |
| AC-14 Canary before exposure | Unit 3 25-state publisher boundary; Unit 5 component proof; post-Unit-8 candidate canary; protected draft canary; Unit 7 exact readiness terminals |
| AC-15 Existing-user discovery without legacy mutation | Unit 1 signed legacy diagnosis; Unit 4 in-session write-zero defer; Unit 8 existing-user holdback docs |

Before implementation handoff, verify every design AC maps to at least one
focused test, one owning unit receipt, and—where required—one canonical/live
receipt. No AC may be satisfied only by prose.

## 15. Per-unit regression and commit gate

After each unit's focused GREEN, run the related regression set, then the full
repository gate in an isolated environment. Before running the full gate,
materialize or verify the R0 receipt-pinned worktree-local Python 3.12 closure
without using a real profile, ambient package cache, or network:

```bash
gate_root="$(mktemp -d "${TMPDIR%/}/samvil-bridge-gate.XXXXXX")"
mkdir -p \
  "$gate_root/home" \
  "$gate_root/codex" \
  "$gate_root/claude" \
  "$gate_root/tmp" \
  "$gate_root/xdg/cache" \
  "$gate_root/xdg/config" \
  "$gate_root/xdg/data" \
  "$gate_root/xdg/state"
: > "$gate_root/gitconfig"

env -i \
  PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin \
  HOME="$gate_root/home" \
  CODEX_HOME="$gate_root/codex" \
  CLAUDE_CONFIG_DIR="$gate_root/claude" \
  TMPDIR="$gate_root/tmp" \
  XDG_CACHE_HOME="$gate_root/xdg/cache" \
  XDG_CONFIG_HOME="$gate_root/xdg/config" \
  XDG_DATA_HOME="$gate_root/xdg/data" \
  XDG_STATE_HOME="$gate_root/xdg/state" \
  GIT_CONFIG_GLOBAL="$gate_root/gitconfig" \
  GIT_CONFIG_NOSYSTEM=1 \
  GIT_TERMINAL_PROMPT=0 \
  PYTHONNOUSERSITE=1 \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  /bin/bash scripts/pre-commit-check.sh
```

Expected: `═══ pre-commit check: PASS ═══` and exit `0`. If the worktree-local
venv is missing, stop with `BLOCKED_ENVIRONMENT`; R0 must provision it from its
reviewed digest sidecar before Unit 2, and from Unit 2's reviewed lock closure
after Unit 2. Never point the gate at a user profile, ambient cache, or editable
install outside the worktree.

Then run:

```bash
git diff --cached --check
git status --short
```

Expected: only the current unit's intended files are staged/modified. Run the
P0 external precommit gate, commit once, then run the postcommit gate. Never use
`--no-verify`.

## 16. Independent review program

After Unit 8 and before any remote mutation, run all three reviews independently
against the full diff from the exact fuse commit to the bridge head.

### Review A — Distribution and provenance

- [ ] Search for default-branch escape, implicit ref, tag/ref confusion, asset
  substitution, same-version equivocation, prerelease selection, downgrade,
  replay, protocol mismatch, signer-root confusion, authorization key
  rotation/revocation weakness, direct-runner bypass, and publisher resume
  divergence.
- [ ] Verify every Action/runtime/native source is locked and every fixed
  subject is represented exactly once in index and attestation subject set.
- [ ] Verify publisher performs remote mutation zero before freeze PASS and
  cannot replace/delete published stable assets.

### Review B — Filesystem and interruption

- [ ] Review partial download/extraction, archive collisions, staging
  collision, ENOSPC, SIGKILL, timeout, response loss, no-replace races,
  registry gate/held FD/seal/move/install ordering, metadata drift, journal
  durability, preserved-copy set, and every capability irreversible boundary.
- [ ] Verify no failure path overwrites/deletes current/sibling caches,
  rollback snapshot, moved-original, concurrent registry bytes, user project,
  real profile, or actual `CODEX_HOME`.

### Review C — Real user compatibility

- [ ] Review exact old updater successful discovery, discovery failure clone,
  stale catalog, two-process stale memo, pinned/custom source, unsupported host
  topology, missing `gh`, network/proxy/custom CA, modified/directory/multiple
  cache, restart, selected root, no-write transient observation, and Korean
  actionable copy.
- [ ] Verify existing users are unchanged/deferred, not silently migrated,
  removed, repaired, or counted as bridge adoption.

Any unresolved P1/P2 requires a code change, new candidate tree authorization,
all focused/regression/full/canonical gates again, and all three reviews again.

## 17. Final local validation before release choreography

Run the following only with isolated profile variables and without the known
stuck full release-control paths:

```bash
mcp/.venv/bin/python -B scripts/validate-release-version.py
mcp/.venv/bin/python -B scripts/validate-release-bridge-workflow.py
mcp/.venv/bin/python -B scripts/validate-ci-workflow.py
bash hooks/validate-version-sync.sh
bash scripts/check-broken-references.sh
git diff --check
git status --short --branch
```

Run the complete portable fixture suites, then separately attach P0 canonical
receipts. Do not combine them into one green label.

Required evidence split:

```text
PORTABLE CONTRACTS
  unit/property/integration/workflow/doc tests

CANONICAL P0
  each of Units 0..8 precommit/postcommit full-gate receipts
  Unit 5 component receipt unit5_component_transaction_verified

LIVE CANDIDATE
  old-updater no-write/defer + negative legacy-risk receipts
  candidate_empty_ready_acquisition_restart_mcp

REMOTE TOPOLOGY
  main fuse + stable freeze + rulesets + exact check producer
  pinned Stage R + rehearsal + live Stage A + both external monitors + kill switch

DRAFT TAG ASSETS
  attestation + fixed-subject equality
  draft_empty_ready_acquisition_restart_mcp
```

The bridge workstream is incomplete if any one evidence plane is missing.

## 18. Release choreography after implementation and review

Remote mutation is a separate authorized operation. A green implementation
branch does not authorize any remote mutation. Stage A, Stage R, branch
creation, merge, tag, draft, and publish are performed only by the pinned P3
release-control/App capability and reconciled by exact remote read-back; raw
operator `git push`, `git tag`, or ad-hoc mutating `gh api` is forbidden.

1. Pin the approved v4.32.2 SHA/tree and old-updater behavior of current public
   default `main` in an authoritative receipt.
2. At that exact base, create immutable
   `legacy/v4.32.2-original` and `codex/v4.32.2-quarantine-fuse`. The final
   reviewed fuse head is the direct ancestor/base of every bridge remainder
   commit.
3. Complete and freeze the one fuse unit plus reviewed eight-unit bridge
   implementation plan and exact commit graph.
4. Review the fuse PR against default `main`; from the same fuse base,
   pre-build and review the bridge remainder synthetic
   `release/v4-stable` tree.
5. Before any user-visible tree change, activate the `main` quarantine ruleset,
   pinned `release-topology-guard`, external default monitor, external Claude
   host watcher, and kill switch. Permit only separately authorized one-shot
   Stage A old-base→exact-fuse and Stage R fuse→pre-reviewed-restoration
   mutations.
6. Create, sign, review, and pin the Stage R commit whose parent is the exact
   fuse commit and whose tree/catalog is byte-identical to
   `legacy/v4.32.2-original`. Prepare the stable ruleset to allow only
   fuse-head→approved synthetic bridge tree.
7. In a disposable mirror, characterize the exact fuse, synthetic
   `release/v4-stable` bridge/new-tag empty-catalog tree, and Stage R. Run every
   reviewed semantic×platform legacy-host class across no-ref, custom-main,
   explicit-release, historical/fork/local, cold/stale-disk/stale-process,
   auto/manual, refresh success/failure, >600s, two-restart, discovered-skill,
   and direct-setup axes.
8. Prove `REFRESHED_PAUSE_COLD`: new install is not found and installed state is
   unchanged. Separate cached/recent/failure/fixed-ref residuals. Allow only
   exact `PASSIVE_ONLY_NO_WORSE`; classify hybrid, downgrade/uninstall, active
   surface, extra selection/settings mutation, or unknown behavior as
   `SEMANTIC_FUSE_OR_UNKNOWN`.
9. Using the P3 remote-ref controller, apply Stage A as an expected-old,
   single-ref fast-forward from the approved old `main` to the exact fuse. Keep
   the repository default branch name `main`; mutate no repository setting.
   Read back ref/tree/passive/catalog identity, close the one-shot
   authorization, and relock the ref.
10. Create `release/v4-stable` create-only at the exact fuse head, activate its
    ruleset, and keep it non-default. Create the exact reviewed
    `codex/v4.32.3-release-bridge` candidate ref expected-absent at the Unit 8
    head, then open the bridge remainder PR against `release/v4-stable`.
11. Before bridge merge, pass the operational propagation barrier: at least
    three independent egresses; unauthenticated no-cache metadata and Contents
    APIs, Git HEAD, and first/last no-ref clones; sampled every minute for 15
    consecutive minutes, with a hard 30-minute timeout. Old-base/fuse mixed
    bytes are `LEGACY_RISK_OBSERVED`; bridge/v4.33 bytes must remain zero.
12. On live default `main`, reverify successful-discovery no-op, cold
    not-found/installed-state unchanged, stale-disk/process no-worse behavior,
    API-failure behavior, and passive clone-source receipts.
13. From the frozen fuse base, reviewed bridge head, and synthetic merge tree,
    emit `frozen_base_head_tree_pinned`, build `--mode candidate` twice, and
    emit `candidate_payloads_verified` plus the non-publishable candidate
    index. Bind CI, review, catalog, default-main and steps 11–12 receipts.
    Rerun the P3 Codex observer/source guard against this exact Unit 8 tree,
    tracked core manifest and candidate index to emit
    `candidate_codex_no_write_external` and
    `candidate_codex_verified_source_guard`.
14. With signed single-transaction authorization, pass candidate diagnosis and
    exact `EMPTY_READY` acquisition→complete restart→actual MCP canary on an
    isolated darwin-arm64 exact OS build.
15. Reverify main/release rulesets, default=`main`, base/head, workflow, and
    synthetic tree. On any drift, discard the candidate and its receipts and
    restart from step 5. On exact success, P3's external readiness verifier
    signs `candidate_merge_ready`; candidate code cannot emit it.
16. Merge the bridge remainder PR into `release/v4-stable` at the expected fuse
    base/head; prove the post-merge tree equals the approved synthetic tree and
    freeze the release SHA. Emit `release_branch_merge_pinned`. Default `main`
    remains unchanged.
17. Immediately rerun the live explicit `release/v4-stable` empty-catalog and
    custom-main fuse matrix, then reverify default branch, main/stable
    rulesets, required-check producer/source, bypass inventory, frozen release
    ref/tree, and synthetic-merge identity to emit
    `live_explicit_release_matrix_verified` and
    `postmerge_topology_rulesets_verified`. Missing receipts, topology drift,
    or unexpected install, downgrade, uninstall, or selection rewrite block
    tag and integration work.
18. Rebuild the pretag fixed-payload set from the exact frozen release branch
    using `--mode release`; require equality with the approved candidate fixed
    payload set under Unit 2's explicit exclusion of candidate/release indexes,
    detached provenance and attestation envelopes. Emit
    `pretag_payloads_verified`.
19. Verify the tag ruleset and create immutable-intent `v4.32.3` with
    expected-absent create-only CAS. Before mutation, emit
    `tag_create_authorization_ready`, have P3 sign the exact `tag_ready`
    terminal, and let the one-shot tag controller consume that terminal. After
    read-back reconciliation emit `tag_created`.
20. Verify the exact tag-triggered trusted Release workflow, every fixed-payload
    equality result, and online provenance. Emit `tag_build_completed`,
    `tag_artifacts_verified`, and `attestation_online_verified`.
21. Create the draft Release, promote only verified workflow artifacts, and
    reverify every remote subject. Emit `draft_release_ready`,
    `assets_uploaded`, and `remote_assets_verified`; independently build,
    upload, read back, and verify the detached provenance to emit
    `attestation_offline_verified`, `detached_provenance_uploaded`, and
    `detached_provenance_verified`.
22. Using exact tag/index/runner authorization, pass the draft-assets
    `EMPTY_READY` restart/new-session/MCP canary on the same platform-policy
    build and emit all underlying metadata-restored, gate-released,
    tool-serving, admission-released, activation, and independent manual
    selected-root/MCP observation receipts. Rerun the draft-scoped Codex
    no-write/source guard against exact Release index/assets and online+offline
    production attestation and emit its two draft IDs. P3 then verifies this
    complete base causal set and signs
    `draft_empty_ready_acquisition_restart_mcp` as aggregate receipt A. Only
    afterward upload and read back signed receipt A as the fixed canary-receipt
    asset; then construct publication-binding receipt B from the verified
    asset result and emit `draft_canary_receipt_uploaded` plus
    `draft_canary_receipt_verified`. Finally refresh the three external
    monitor/watcher/kill-switch receipts and have P3 alone sign
    `publish_ready`.
23. Publish the stable Release, verify public discovery, and run repeat
    `CURRENT` with protected-scope writes equal to zero.
24. Create `codex/v4.33-integration` from the frozen bridge
    `release/v4-stable` commit.
25. Rebase PR #13 onto the bridge, retarget it to the integration branch, and
    regenerate its synthetic-merge/Desktop persisted evidence. Never merge PR
    #13 into default `main`.

### Stop, reconciliation, and restart rules

- If any of steps 5–8 fails, Stage A is forbidden.
- A lost or ambiguous remote response is not success and never triggers a blind
  retry. The P3 controller reads back the exact ref/object/state and resumes
  only when it proves the same expected identity.
- After Stage A, a propagation-only timeout blocks bridge merge. Keep default
  `main` locked at the fuse while investigating, or use the separately
  authorized Stage R to forward-restore the pre-promotion tree.
- A semantic fuse defect, switch-attributable active/hybrid delta, unexpected
  mutation, or unknown class is `SEMANTIC_FUSE_OR_UNKNOWN`; immediately execute
  expected-fuse→pre-reviewed-Stage-R as a single-ref forward mutation.
- Do not close a Stage R incident until no-ref and explicit-main
  fresh/stale/process fixtures stabilize at exact original or approved
  no-worse behavior and the incident receipt is durable. Stage R failure or
  post-Stage-R verification failure activates the critical rollout kill
  switch. Any actual `stage_r_executed` invalidates bridge candidate/tag/
  publish readiness; a future attempt begins a new release window with fresh
  topology, propagation, payload and canary receipts.
- Failure of step 11, 12, or 14 forbids merging the bridge into the release
  branch. Drift at step 15 invalidates candidate bytes and receipts; restart
  from step 5 rather than continuing from the drift point.
- Failure of step 17 or 18 forbids tag creation. Failure of step 22 keeps the
  Release in draft state.
- Before a remote tag exists, a local tag may be discarded. After the remote
  tag exists, transient workflow failure may resume only from the same source
  identity. Wrong remote tag source/build identity is never retagged; release
  v4.32.4 as a forward fix.
- Published tags/assets are never moved, deleted, or replaced. Post-publish
  defects use the same stable-only gate for a v4.32.4 forward fix. A
  post-publish default-main fuse incident restores only `main` through Stage R;
  it does not mutate published tag/assets.
- Keep default `main` quarantine until a separate sunset proof, and keep the
  release freeze through final v4.33 stable.

## 19. Hard stop conditions

Stop immediately and preserve evidence when any of these occurs:

- canonical quota/admission/signal authority is unavailable;
- actual user `HOME`, `CODEX_HOME`, Claude profile/cache/settings, or project is
  observed as an input or mutation target;
- the same failure repeats twice at the same boundary;
- a historical official artifact, workflow Action, runtime/native source,
  key/policy, ruleset/check producer, tag/ref, or fixed asset identity is
  missing or ambiguous;
- default `main` is not the exact approved fuse;
- bridge code or release automation uses an implicit default ref;
- a candidate tree changes after authorization/review;
- remote response loss cannot be reconciled to one exact identity;
- registry state cannot be proven as pre, exact target, or transaction-owned
  pending;
- a required live canary receipt is replaced by a fixture/portable PASS;
- independent review has an unresolved P1/P2.

Allowed terminal reports are explicit and evidence-scoped:

```text
BLOCKED_ENVIRONMENT
BLOCKED_RELEASE_AUTHORIZATION
BLOCKED_USER_STATE
RECOVERY_REQUIRED
PORTABLE_CONTRACT_GREEN
CANDIDATE_MERGE_READY
TAG_READY
PUBLISH_READY
```

Never collapse a blocked canonical/live plane into “all tests green.”

## 20. Implementation handoff

Recommended execution is `superpowers:subagent-driven-development`: one fresh
implementation worker per unit, followed by an independent spec-compliance
reviewer and code-quality reviewer before the unit's external authorization,
canonical gate, and single commit. Use
`superpowers:verification-before-completion` for each unit and for the final
bridge report.

Do not begin Unit 0 until R0/P0 are concrete and reviewed. Do not begin Unit 1
until P1 is pinned, Unit 2 until its P2 workflow/runtime rows are pinned, or
Unit 5 until its P2 native/key policy and P3 bootstrap/controller/monitor
capabilities are pinned. The first executable follow-up should therefore be a
separate, narrowly scoped Task -2 quota/admission environment plan and
implementation, followed by P1/P3 trusted-control work—not bridge feature
code.
