# SAMVIL v4.32.2 Quarantine Fuse F0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use
> `superpowers:subagent-driven-development` or `superpowers:executing-plans`.
> Production behavior must follow test-first RED → GREEN. Do not push, open a
> PR, update a remote ref, or touch a user-owned `HOME`/`CODEX_HOME` while
> executing this plan.

**Goal:** Freeze PR #14 as a fail-closed release-control foundation and, only
after a separately reviewed Task -2 quota-storage adapter exists, build and
prove the exact v4.32.2-version passive quarantine fuse and its pre-reviewed
Stage R semantic restoration commit without changing the public repository.

**Architecture:** Keep the current v4.32.2 tree as immutable input, render a
same-version passive overlay for every auto-loaded or historically
user-invokable surface, verify that overlay with a quarantine-specific gate,
and rehearse expected-old Stage A plus fuse-parent/original-tree Stage R in a
disposable local bare mirror. The fuse does not install v4.33 and is not the
v4.32.3 bridge. The current foundation stops at storage-capability admission;
the remaining architecture is the conditional target after that blocker is
removed.

**Tech stack:** Python 3.12 standard library, POSIX shell, Git plumbing,
existing pytest environment for the pre-render baseline, local bare Git
repositories for ref-transaction rehearsal. No new runtime dependencies.

---

## 1. Fixed identities and safety boundary

- Approved original commit:
  `81c0c3468ed8757513fc4bf76b028736197bc556`
- Original branch name: `main`
- Fuse manifest version: `4.32.2`
- Public default branch setting remains `main`.
- Historical design evidence branch:
  `codex/v433-safe-upgrade-design` (provenance only during the current bridge
  execution; do not check it out or rewrite it)
- Implementation branch:
  `codex/v4.32.2-quarantine-fuse`
- Public remote mutation: forbidden in F0.
- Actual user profile/cache/config/project paths: forbidden in F0.
- Every fixture uses a fresh temporary repository and fresh temporary
  `HOME`, `CODEX_HOME`, and Claude config root.
- The literal user-owned untracked `$CODEX_HOME/` entry in the original
  checkout is never read, staged, copied, or removed.

The implementation must abort if `origin/main`, the original commit tree, or
the version files differ from the pinned identities captured at plan start.

F0 defines two distinct success terminal states, but neither is reachable on the
currently audited host boundary:

- `F0_LOCAL_IMPLEMENTATION_GREEN`: trusted control verifier, exact fuse commit,
  local Stage R object, no-write fixtures and disposable mirror are green.
- `STAGE_A_PROMOTION_READY`: additionally requires approved signatures,
  complete historical official-artifact ledger, actual supported-host
  cold/stale-disk/stale-process/no-ref/custom-main results and every design
  promotion receipt. F0 local success alone can never emit this verdict.

Canonical PASS first requires a Task -2-owned invocation-exclusive filesystem
whose fixed capacity is enforced by the kernel and whose class and identity
digest are bound into the manifest and receipt. No reviewed adapter currently
provides that boundary. Until it does, the exact F0 terminal is
`BLOCKED_ENVIRONMENT` with low-level blocker
`UNSUPPORTED_INVOCATION_STORAGE_QUOTA`; neither
`F0_LOCAL_IMPLEMENTATION_GREEN` nor `STAGE_A_PROMOTION_READY` may be claimed.
`INVOCATION_STORAGE_QUOTA_NOT_OS_ENFORCED` is a runtime-admission limitation,
not a `promotion_limitations` entry that permits a local PASS. PR #14 therefore
delivers a fail-closed control foundation only. Portable Linux/test-double
results validate schema and orchestration contracts, not an actual supported-
host canonical end-to-end gate. A Linux test that replaces the platform parser,
host tool or quota adapter with a mock is never reported as a real external-
parser or real OS-boundary result.

### 1.1 Current v4.32.3 bridge execution mapping

The Task -2/Task -1 branch-history commands below record how PR #14's
fail-closed foundation was originally produced. For the current v4.32.3 bridge
run they are historical acceptance context, not executable steps. The binding
current procedure is:

- Preserve frozen PR #14 head
  `141da457a98b552047f0388b9967664e11aff8b1` and every ancestor byte/commit.
  Do not fixup, amend, autosquash, rebase, or otherwise rewrite
  `f6d50644a01c925b7910c494e2160bbac504dbd8`, PR #14, or the historical design
  branch.
- Create the reviewed v4.32.3 plan commit as one direct child of PR #14 on
  `codex/v4.32.3-release-bridge-plan`. Add the current implementation plan's
  P0/P1/P3 trusted-control prerequisites only as descendants of that preserved
  plan/control ancestry.
- P0 must supply and review the missing invocation-exclusive kernel-quota and
  detached-process authority, then rerun PR #14's exact committed control
  suite. This closes the old Task -2/Task -1 acceptance blockers without
  replaying their obsolete history-rewrite procedure.
- Unit 0's candidate ancestry starts independently at exact original
  `81c0c3468ed8757513fc4bf76b028736197bc556` and executes only Tasks 0–6 of
  this document. Any later phrase such as “exact amended control commit” means
  the exact descriptor-pinned, reviewed current trusted-control commit/receipt
  on the v4.32.3 plan ancestry; it never means rerun the old fixup/autosquash.
- The Unit 0 candidate result remains exactly one direct fuse commit above the
  original. No plan/control commit enters that ancestry. All Task -2/Task -1
  security invariants remain acceptance requirements; only their obsolete
  branch names and history-rewrite mechanics are superseded by this mapping.

If a later historical instruction conflicts with this subsection on branch,
commit, ref, or rewrite mechanics, this subsection controls. Safety,
isolation, fail-closed, receipt, and external-authority requirements are never
weakened.

---

## 2. Code-fact scope correction

The approved design requires the fuse tree not to retain active production
skill, hook, setup, update, or MCP entry behavior. The current repository's
normal full gate expects those production surfaces to exist and be wired:

- `.claude-plugin/plugin.json` currently registers `./skills/`, hooks, and
  `.mcp.json`.
- `.claude-plugin/marketplace.json` currently publishes an installable
  `samvil` row with `source: "./"`.
- `skills/samvil-update/SKILL.md` currently clones `main`, rsyncs into the
  plugin cache, renames the cache directory, and deletes sibling versions.
- `references/codex-commands/samvil-update.md` currently fetches and pulls
  `origin main`.
- `scripts/setup-codex.sh`, `scripts/sync-cache.sh`,
  `scripts/install-git-hooks.sh`, and `hooks/setup-mcp.sh` currently mutate
  host state when invoked.
- `.githooks/post-commit` automatically invokes `scripts/sync-cache.sh`, and
  that script writes an unversioned cache root while the updater expects
  version-child directories. Both paths must become passive in the fuse;
  neither topology may be guessed or normalized in F0.
- The hard version gate compares plugin and MCP `__init__` versions while the
  README mismatch is warning-only and `mcp/pyproject.toml` remains an
  independent `1.0.0` package version. F0 pins this existing distinction
  explicitly rather than silently treating all four values as one version.
- The current release publisher defaults to `main` and can push a branch and
  tag before the complete publish decision, and partial tag publication is not
  safely resumable. That publisher is not used or repaired during F0; remote
  access is prohibited and bridge unit 3 owns its replacement.

Therefore F0 defines two independent future canonical gate target contracts
rather than pretending the normal production wiring suite remains meaningful
after production wiring is intentionally removed:

1. **Original-tree baseline gate:** an isolated exact-original clone will be
   driven by the exact committed control-only
   `tools/release-control/run-full-gate-isolated.py` described below. Its one
   Seatbelt child is a digest-pinned trusted wrapper, not candidate shell
   bytes. The wrapper runs fixed independent runtime/import/test probes and the
   unmodified candidate subcommand `/bin/bash scripts/pre-commit-check.sh` with
   disjoint non-authoritative stdout/stderr channels.
2. **Fuse-tree quarantine gate:** an isolated exact-candidate snapshot will run
   the same trusted wrapper/probe sequence and candidate subcommand through that
   same committed runner before the final fuse
   commit exists, then the committed runner repeats the full gate after commit
   against that exact final commit and the same authorized tree. Quarantine
   mode is accepted only when an external candidate-tree authorization from
   the trusted control branch matches the candidate tree/policy/manifest/gate
   digests; candidate files cannot select the mode by themselves. The gate then runs
   the complete quarantine contract suite: exact tree identity, passive
   surface inventory, no-write dynamic execution, no installable catalog,
   empty MCP/hook registration, workflow containment, Stage A single-ref
   semantics, and Stage R byte-identical restoration.

The outer trusted verifier is the only authority that may issue PASS, and only
after Task -2 has admitted and attested the invocation-exclusive kernel-quota
storage boundary. Until then it must emit the path-free
`UNSUPPORTED_INVOCATION_STORAGE_QUOTA` blocker before wrapper, probe, candidate
or target materialization and the F0 terminal remains `BLOCKED_ENVIRONMENT`.
Candidate pre-commit/tests must print the original baseline receipt identity
and the quarantine receipt, but their output is auxiliary untrusted data. A forged
candidate `PASS`, omitted command or altered test runner is rejected by the
outer verifier. Missing or stale original baseline evidence is a hard failure.

---

## 3. File map

### Trusted control-branch evidence, never trusted from candidate bytes

| File | Action | Responsibility |
|---|---|---|
| `release/legacy-v4322-distributions.json` | Create/update on design control branch | Canonical signed historical distribution SSOT: non-empty official snapshot/manifest rows plus exactly one final `quarantine_fuse` cutoff exception |
| `release/legacy-v4322-distributions.json.sig` | Create on design control branch | Detached release-authority signature; required before public promotion readiness |
| `release/quarantine/v4322-candidate-authorization.json` | Create/update signed sidecar on design control branch | Pre-commit candidate tree/policy/manifest/passive/gate authorization; never a distribution row |
| `release/quarantine/v4322-candidate-authorization.json.sig` | Create signed sidecar on design control branch | Detached authorization signature or typed local-only unsigned status |
| `release/quarantine/v4322-original-receipt.json` | Generate on design control branch | Original commit/tree/version/file inventory and isolated baseline-gate digest; contains no local absolute path |
| `release/quarantine/v4322-historical-surface-ledger.json` | Generate on design control branch | Every retrievable official artifact/class and union of historically discoverable skill/hook/setup/update/MCP/instruction paths; missing artifacts are explicit blockers |
| `release/quarantine/v4322-passive-surface-manifest.json` | Create in the candidate and bind in external authorization | Canonical policy-classified passive-surface path/mode/blob manifest used as the explicit passive semantic role digest |
| `tools/release-control/inherited_context.py` | Create and pin on design control branch before candidate work | Internal control-plane validator/probe module for the exact inherited-sandbox context and outer receipt protocol; not a candidate or public runtime API |
| `tools/release-control/run-isolated.py` | Create and pin on design control branch before candidate work | Trusted `env -i`/sandbox/network-deny/child-supervision launcher |
| `tools/release-control/run-full-gate-isolated.py` | Create and pin on design control branch before candidate work | Fail-closed control foundation for the future original/candidate canonical gate; before materialization or execution it requires Task -2-attested invocation-exclusive kernel-quota storage evidence, otherwise emits `UNSUPPORTED_INVOCATION_STORAGE_QUOTA` and cannot issue PASS |
| `tools/release-control/verify-quarantine-candidate.py` | Create and pin on design control branch before candidate work | Independently verify authorization signature, control commit, candidate tree and every policy/manifest/passive/gate digest |
| `tools/release-control/tests/test_release_control.py` | Create on design control branch | RED/GREEN tests for candidate bypass, forged GREEN output, sandbox escape, real-repository target and signature/digest failures |

The canonical catalog schema fixes its cutoff, known-official completeness
rules, historical snapshot/manifest rows and exactly-one fuse invariant. Each
historical row binds its discovered-surface-set digest, and the signed catalog
binds the complete historical-surface-ledger digest. Candidate authorization
is a separate sidecar and can never satisfy a distribution-row schema.

The trusted inherited-validator/verifier/launcher/full-gate-runner commit SHA,
file digests and approved public-key identity are pinned before any candidate
edit.
Candidate-controlled code cannot replace or configure them. The separate
candidate-tree authorization is keyed by tree SHA and content digests, so
it can exist before a commit object. After the exact fuse commit exists, the
final `quarantine_fuse` row binds its commit SHA and tree SHA. If an approved
release signature cannot be produced locally, F0 may complete local code and
rehearsal evidence but must report `BLOCKED_RELEASE_AUTHORIZATION`; it is not
eligible for Stage A.

### Control and verification files retained in the fuse tree

| File | Action | Responsibility |
|---|---|---|
| `release/quarantine/v4322-policy.json` | Create | Canonical surface classifications, pinned original identity, forbidden operations, expected passive message and landing URL |
| `release/quarantine/v4322-topology-guard-policy.json` | Create | Protected-base topology/check/ruleset contract for the dormant explicit stable-PR guard and later bridge publisher |
| `release/quarantine/v4322-workflow-actions.lock.json` | Create | Exact full-SHA Actions/runtime allowlist used by the protected-base workflow; candidate units cannot widen it |
| `scripts/quarantine-fuse.py` | Create | Deterministically render or verify a candidate tree; render requires an explicit output root and refuses repository/profile roots |
| `scripts/rehearse-quarantine-refs.py` | Create | Create-only local Stage R commit and disposable-mirror Stage A/R rehearsal; never contacts a remote |
| `scripts/check-release-topology.py` | Create | Thin descriptor-safe CLI over the single protected topology evaluator; it owns no duplicate policy logic |
| `tools/__init__.py` | Create if absent | Fixed package root required for descriptor-pinned topology imports |
| `tools/release_topology_guard/__init__.py` | Create | Protected topology package marker with no import-time mutation |
| `tools/release_topology_guard/guard.py` | Create | Single evaluator for stable base/head/tree, default-main fuse, rulesets, bypass actors, and exact check-run producer/source identity |
| `tools/release_topology_guard/tests/__init__.py` | Create | Test package marker with no runtime behavior |
| `tools/release_topology_guard/tests/test_guard.py` | Create | Pure evaluator tests including forged candidate authority, implicit refs, and wrong producer/source identities |
| `mcp/tests/test_quarantine_fuse.py` | Create | Policy, renderer, passive content, no-write, collision and Stage R contract tests |
| `mcp/tests/test_release_topology_guard.py` | Create | Candidate-tree integration tests proving the protected guard is dormant on default main and exact on explicit stable PRs |
| `mcp/tests/test_update_smoke.py` | Modify | In quarantine mode replace the documented interactive-only updater gap with passive/no-subprocess assertions |
| `mcp/tests/test_sync_cache_smoke.py` | Modify | Prove quarantine sync and post-commit paths are no-write and do not infer either conflicting cache topology |
| `mcp/tests/test_ci_workflow.py` | Modify | Prove the legacy monitor is the only active default-main schedule and the protected topology guard is dormant except for explicit PRs targeting `release/v4-stable` |
| `.github/workflows/legacy-feed-monitor.yml` | Create | Reviewed read-only active default-main schedule; no release mutation authority |
| `.github/workflows/release-topology-guard.yml` | Create | Dormant-on-main read-only PR guard that runs only for explicit `release/v4-stable` targets from protected-base source |
| `scripts/pre-commit-check.sh` | Modify | Select normal or quarantine gate by validated policy/manifest identity; never silently skip both |

### Fuse runtime and discovery surfaces

| Surface | Required candidate state |
|---|---|
| `.claude-plugin/plugin.json` | version remains `4.32.2`; `skills` points only to `./quarantine-skills/`; no hooks; no `mcpServers` |
| `.claude-plugin/marketplace.json` | metadata retained; exact empty `plugins` array |
| `.mcp.json` | exact empty `mcpServers` map |
| `quarantine-skills/samvil/SKILL.md` | passive `DEFERRED_TO_V433` response only |
| `quarantine-skills/samvil-update/SKILL.md` | same passive response; no command block or mutation instruction |
| every tracked `skills/**/SKILL.md` and `SKILL.legacy.md` | passive compatibility overlay at the historical path |
| root `README*`, `AGENTS.md`, `CLAUDE.md`, `GEMINI.md` | installation pause only; no setup/update/bootstrap commands |
| `references/codex-commands/*.md` | passive host command overlay |
| `references/gemini-commands/*.toml` | passive host command overlay with no executable command |
| OpenCode/Gemini host instruction fragments | passive overlay |
| historically user-invokable setup/update/cache/hook paths in policy | executable no-write guard that prints the passive receipt and exits successfully |
| `.githooks/post-commit` and installed-hook-visible sync paths | passive no-write guard; no cache topology discovery |
| MCP package entry points in policy | passive/no-tool server or explicit deferred exit; no project/profile/cache mutation |
| `.github/workflows/*` | no implicit development/release workflow on default `main`; the reviewed read-only legacy-feed monitor is the only active default-main schedule, while `release-topology-guard` is dormant on main and runs only for an explicit pull request targeting `release/v4-stable` from exact protected-base source |

The policy inventory is allowlist-based. A new auto-loaded or executable path
found in the original tree but absent from the policy is a render and verify
blocker.

The allowlist source is not only the current original tree. It is the union of
every historically discoverable path in the complete official-artifact ledger.
A path that existed only in an older artifact must still be materialized as a
passive overlay in the fuse so a no-delete rsync cannot preserve active residue.
Unknown or unavailable official artifact identity blocks
`STAGE_A_PROMOTION_READY` and cannot be represented by the current tree.

The release recovery label **Stage R** is a release-ref transaction name. It
must not be added to `mcp/samvil_mcp/models.py::Stage` or the application-build
chain marker because those types model a different pipeline.

---

## 4. One-unit commit boundary

F0 produces exactly one implementation commit on
`codex/v4.32.2-quarantine-fuse`. The plan and external distribution-ledger
evidence are separate control-branch commits and are not part of the fuse
runtime tree.

The implementation commit may contain multiple RED/GREEN cycles, but no
intermediate production commit is allowed. Before creating the exact fuse
commit, and only after the quota-backed storage adapter exists:

- the original-tree baseline receipt is fixed;
- all focused tests have demonstrated the expected RED failure at least once;
- the quota-backed canonical candidate quarantine gate is green;
- the candidate tree SHA and all candidate content digests are fixed in an
  external candidate-tree authorization;
- the staged diff contains only the F0 surface;
- `git diff --cached --check` is green.

After the exact fuse commit exists, and before calling F0 promotion-ready:

- the final external `quarantine_fuse` row binds that exact commit/tree;
- Stage R is created with that exact fuse commit as parent and exact original
  tree as its tree;
- Stage R and the final catalog are signed by the approved release authority,
  or the result is explicitly `BLOCKED_RELEASE_AUTHORIZATION`;
- the disposable mirror Stage A/R rehearsal is green for those exact objects.

No bridge publisher, signed release bundle, Claude selection adapter, v4.33
installer, profile transaction, or public GitHub ruleset implementation may be
included in this commit.

---

## 5. Task -2 — Bootstrap the first trusted execution boundary

> **Current bridge run:** historical prerequisite context only. Do not execute
> its old branch/bootstrap history mechanics; satisfy its unresolved acceptance
> requirements through the current plan's P0 on preserved PR #14 ancestry, as
> fixed by section 1.1.

Task -1 cannot trust code that Task -1 is itself creating. Its first RED/GREEN,
review and control-foundation operations therefore run through a minimal
bootstrap boundary fixed by this already-reviewed plan commit. A canonical
full-gate or F0 implementation-commit operation additionally requires Task -2-
attested quota-backed invocation storage. On the current host the boundary must
stop before wrapper/probe/candidate/materialization and report
`UNSUPPORTED_INVOCATION_STORAGE_QUOTA` / `BLOCKED_ENVIRONMENT`.

### Scope correction — macOS Seatbelt must be applied exactly once

This is a scope correction to the Task -2 execution topology, not a reduction
of security requirements or product scope. Confirmed macOS behavior makes the
previous nested-sandbox design structurally impossible:

```bash
/usr/bin/sandbox-exec -p '(version 1)(allow default)' \
  /usr/bin/sandbox-exec -p '(version 1)(allow default)' /usr/bin/true
```

The command fails with `sandbox_apply: Operation not permitted` and exit 71.
The outer profile already allows default behavior, so adding broader Seatbelt
profile rules cannot make a process apply a second sandbox. A previous run
without the outer sandbox produced 22/22 focused GREEN, but that run is
explicitly rejected as Task -2 evidence because it did not execute inside the
required bootstrap boundary.

Task -2 therefore applies one outer sandbox around all uncommitted Task -1
test, verifier and launcher code. `run-isolated.py` retains its normal/default
contract: when invoked outside the bootstrap it directly invokes
`/usr/bin/sandbox-exec` itself. Only the Task -2 bootstrap may request a
`verified inherited sandbox` mode, in which the launcher reuses the already
active outer sandbox instead of attempting a nested Seatbelt application.

### Task -1 scope correction — split the inherited control protocol

The staged launcher has no verified inherited-sandbox mode. Putting schema
validation, trust-receipt validation, live `EPERM` probes, CLI mode selection,
direct sandboxing, child supervision and receipt rendering into
`run-isolated.py` would create an unreviewable control-plane monolith. Add the
private internal module `tools/release-control/inherited_context.py` and split
authority as follows:

- `inherited_context.py` owns the exact v1 context and outer-receipt schemas,
  canonical compact/sorted JSON serialization and SHA-256 hashing, strict
  unknown/missing-field rejection, canonical path containment plus
  regular-file/`nlink == 1` checks, protected-root digest binding, sanitized
  environment-key binding, and independently executed inherited-mode boundary
  probes. It must not invoke `sandbox-exec`, execute candidate code, import
  candidate modules, or issue the final candidate PASS.
- `run-isolated.py` owns CLI parsing, direct-mode `sandbox-exec`, child
  supervision, environment construction/stripping and orchestration. In
  inherited mode it calls the internal validator/probe module and must not
  invoke nested `sandbox-exec`.
- `run-full-gate-isolated.py` owns only the exact original/candidate trusted
  wrapper protocol. It validates the immutable external full-gate manifest and
  control commit, then validates Task -2-supplied quota storage attestation
  before any materialization. Missing, invalid, reused or drifted attestation
  is `UNSUPPORTED_INVOCATION_STORAGE_QUOTA` and forbids PASS. After admission it
  materializes verified Git-object bytes, constructs the
  hermetic runtime/facade and applies the one fixed
  `pinned-full-gate-loopback-only` profile. Its one Seatbelt child is the
  digest-pinned trusted wrapper, which runs fixed independent probes and only
  the fixed candidate subcommand `/bin/bash scripts/pre-commit-check.sh`. It is not
  a generic command launcher and is not imported or invoked by candidate bytes.
- `verify-quarantine-candidate.py` remains the final outer verdict authority.
  It calculates trust evidence independently and never trusts candidate output.

These private control files are a prerequisite scope correction, not product
expansion. They introduce no public behavior or runtime API, candidate
authority, remote/user-profile access, or additional control-plane
implementation commit. All five Task -1 files remain one control-plane commit.
The trusted wrapper is not a sixth tracked file: its canonical source bytes,
mode, interpreter contract and source/content digests are constants inside
`run-full-gate-isolated.py`, are covered by that file's control identity, and
are materialized only below the invocation-owned temporary root.
The generic launcher mode, never candidate CLI, environment or receipt bytes,
selects one of two network-zero classes:
`release-control-network-zero` for the trusted inherited control process and
`release-candidate-network-zero` for a direct untrusted candidate process. The
existing `pinned-full-gate-loopback-only` class remains full-gate-only and is
selected internally only by the control-only full-gate runner.

The launcher grammar is exact for both modes:

```text
<PINNED_PYTHON> <PINNED_CONTROL>/tools/release-control/run-isolated.py --root ABS_EXECUTION_ROOT --nonce HEX64 --timeout POSITIVE_SECONDS --receipt ABS_JSON --denial-log ABS_LOG [--inherited-sandbox-context ABS_JSON] -- ABS_COMMAND [ARG...]
```

- `<PINNED_PYTHON>` is the absolute copied Codex-owned Python 3.12 executable
  selected by the Task -2 TCB. Its canonical path, blob identity and SHA-256 are
  bound in the bootstrap receipt before Task -1 execution. There is no system
  Python, user Python, `PATH` lookup or live-venv fallback. After resolving and
  verifying this receipt-pinned executable, the remaining argv grammar shown
  above is exact in both commands and tests.
- `<PINNED_CONTROL>` is the absolute trusted-control snapshot selected by the
  Task -2 TCB. Its control commit, tree, launcher path/blob/mode and every
  imported control-module blob identity are bound in the bootstrap receipt.
  Candidate bytes cannot provide, redirect or shadow this path.
- Direct mode omits `--inherited-sandbox-context`; inherited mode requires it
  exactly once in the shown position before `--`. Duplicate, reordered or
  unknown launcher options, a missing command separator, a non-absolute
  receipt, denial-log, context or command path, a nonce other than exactly 64
  lowercase hexadecimal characters, or a non-finite/non-positive timeout fails
  closed. In both modes, `--root` must already exist as a directory and the
  supplied absolute spelling must exactly equal its resolved canonical path.
  A symlink, `..`/`.` alias, non-canonical spelling, nonexistent path or
  non-directory root is rejected before any file, probe or writable directory
  is created. In inherited mode that canonical root must additionally exactly
  equal context `execution_root`.
- In inherited mode, CLI `--root` and `--nonce` must exactly match context
  `execution_root` and `nonce`; CLI nonce must also exactly match
  `SAMVIL_BOOTSTRAP_NONCE`. The required inherited-only environment variables
  are `SAMVIL_BOOTSTRAP_NONCE` and `SAMVIL_BOOTSTRAP_CONTEXT_SHA256`; each value
  is exactly 64 lowercase hexadecimal characters, and the latter must equal the
  canonical context JSON SHA-256. The context is SSOT for profile, outer
  receipt, protected roots/write paths and temp probe. Timeout remains trusted
  caller input. Candidate bytes cannot supply, select or override any launcher
  option, inherited environment binding or context field. Environment-only,
  CLI-only, missing or mismatched inherited requests fail with distinct typed
  blockers.
- Direct mode accepts neither the inherited flag nor inherited bootstrap
  environment authority; any `SAMVIL_BOOTSTRAP_*` input without the inherited
  flag is an environment-only typed blocker. Its trusted-caller `TMPDIR` must
  already exist as a canonical absolute directory outside `execution_root`.
  After validating CLI/output paths, the launcher uses its fixed
  `release-candidate-network-zero` profile, creates its direct invocation root
  strictly below that `TMPDIR`, and applies `sandbox-exec` exactly once. That
  direct profile permits the initial candidate `process-exec`, denies
  `process-fork` and signal authority, and therefore denies `fork`, `vfork`,
  `posix_spawn`, native-FFI fork and detached-child creation with `EPERM` at the
  OS boundary. An `exec` replacement remains the same supervised PID under the
  same Seatbelt policy. Inherited mode instead uses
  `release-control-network-zero`, validates `TMPDIR` strictly inside the
  context-bound invocation root and must not invoke `sandbox-exec`. After its
  single trusted `Popen` and before executing the requested command, an
  immutable no-shell exec wrapper lowers macOS `RLIMIT_NPROC` soft and hard
  limits to `(1, 1)` and then `execve`s the exact command in the same PID. The
  inherited command therefore cannot create a `fork`, native-FFI fork,
  `posix_spawn` or detached `setsid` descendant; those attempts fail with
  `EAGAIN`, and the hard limit cannot be raised again. A command that requires
  subprocesses belongs in the outer trusted-control manifest, not inside the
  inherited launcher child.
- Before either mode executes its final command, the trusted wrapper lowers a
  fixed defense-in-depth resource manifest covering CPU time, regular-file size
  and open descriptors. On macOS the TCB must first behaviorally probe whether
  a meaningful hard address-space limit is enforceable: `RLIMIT_AS` aliases the
  shared-region/RSS limit on supported hosts and may be impossible to lower
  below the runtime's large mapped region. If so, the external controller uses
  a fixed low RSS watchdog through the read-only kernel process API and records
  that measured policy instead of claiming a nonexistent hard limit. Logical
  path scans, `st_size`/`st_blocks`, FD/map inventories and
  `RLIMIT_FSIZE × RLIMIT_NOFILE` are diagnostic telemetry only. They do not
  account completely for `F_PREALLOCATE`, file or directory xattrs, metadata,
  sparse/clone allocation, or mmap-unlink-close allocation and therefore cannot
  establish an aggregate host-disk bound. Any execution that contributes to a
  canonical F0 PASS must instead run on a Task -2-owned invocation-exclusive
  fixed-capacity filesystem whose hard quota is kernel enforced, charges every
  allocation class above, has no other writer, and cannot be mounted,
  remounted, resized or replaced by candidate code. Its held filesystem/mount
  identity, hard capacity, cleanup/unmount proof, `storage_boundary_class` and
  `storage_boundary_sha256` are manifest/receipt authority. Missing or drifted
  evidence is `UNSUPPORTED_INVOCATION_STORAGE_QUOTA` and
  `BLOCKED_ENVIRONMENT` before the final command. Stdout/stderr remain
  controller-owned bounded captures and are never loaded with an unbounded
  `.read()`. Limit signals, watchdog termination and bounded-capture overflow
  produce a path-free `RESOURCE_LIMIT_EXCEEDED` blocker with the exact fixed
  limit manifest; candidate output cannot downgrade it to PASS. Post-exit
  telemetry may detect an additional failure, but it can never upgrade an
  unsupported storage boundary to PASS.
- In both modes, `--receipt` and `--denial-log` targets must be distinct
  absolute paths whose parents are already-existing canonical directories.
  Both targets must be absent, strictly contained within the mode's validated
  invocation-owned `TMPDIR`, and outside `execution_root`. Parent aliases or
  symlinks, pre-existing targets of any type, non-directory/non-canonical
  parents and escaping targets are rejected before any probe or writable
  directory is created. After all path validation succeeds, each target is
  created atomically and exclusively and verified as a regular file with
  `nlink == 1` before use. If either output path is invalid, the typed blocker
  is emitted only on stderr with a nonzero exit; the launcher performs no
  unsafe fallback write. Later blockers may be written atomically to the
  already validated receipt.
- Before creating either output or running any probe, the receipt and
  denial-log targets must also be pairwise distinct from `temp_probe_path` and
  every `protected_write_paths` entry. In inherited mode these values come only
  from the validated context; direct mode derives its equivalent trusted probe
  paths before output creation. Any equality or canonical-path collision is a
  typed blocker and creates no file, probe or writable directory.

The inherited protocol is exact and private:
- The context schema is exactly
  `samvil.bootstrap.inherited-sandbox-context.v1`; the outer receipt schema is
  exactly `samvil.bootstrap.outer-receipt.v1`; and the inherited profile class
  is exactly `release-control-network-zero`. A context or outer receipt pinned
  to `pinned-full-gate-loopback-only` is rejected as a typed class-selection
  blocker before inherited probes or candidate execution. Candidate and Task
  -1 bytes cannot select the loopback-only class.
- The context contains exactly these fields: `schema`, `nonce`,
  `profile_class`, `profile_path`, `profile_sha256`, `outer_receipt_path`,
  `outer_receipt_sha256`, `invocation_root`, `execution_root`,
  `protected_read_roots`, `protected_write_paths`, and `temp_probe_path`.
  `protected_read_roots` has exact length two. `protected_write_paths` has
  exact length two. Each write path must be absent and be an immediate child of
  its positionally paired protected root: its canonical parent must exactly
  equal that root and its final component must be one safe, non-empty basename
  containing no separator or NUL and not equal to `.` or `..`.
- Every path is absolute and canonical. The context file, profile file and
  outer receipt are regular files with `nlink == 1`, contained within
  `invocation_root`, and outside `execution_root`. The supplied execution root
  must exactly match the launcher's independently known execution root.
  `TMPDIR` itself must already exist as a canonical absolute directory, be
  strictly contained within `invocation_root`, and be outside `execution_root`.
  `temp_probe_path` must be strictly contained within that validated `TMPDIR`.
  Missing, non-canonical, non-directory or escaping `TMPDIR` is rejected before
  creating any probe or writable directory.
- Each protected read root must already exist as a canonical absolute directory
  and is validated as such without enumerating its contents. Canonicalization,
  directory type and positional protected-write containment are established
  before any denial probe. The outer trusted controller calls
  `os.lstat(protected_write_path)` immediately before sandbox entry and requires
  it to raise `OSError` with `errno == ENOENT` for each paired path.
- The outer receipt contains exactly `schema`, `status`, `nonce`,
  `profile_class`, `profile_sha256`, `protected_roots_sha256`, and
  `environment_keys`. `status` is exactly `PASS`; every value must exactly
  match independently calculated context/profile/protected-root/environment
  evidence, and unknown or missing fields are rejected. The receipt is
  path-free. Its `PASS` attests only to the outer bootstrap boundary and never
  replaces the verifier's final candidate verdict.
- `profile_sha256` is per-invocation evidence: it is the SHA-256 of that
  invocation's exact expanded profile bytes and must match the profile file,
  context and outer receipt for that invocation. Because canonical invocation
  and execution roots differ, raw expanded `profile_sha256` equality is never a
  direct-versus-inherited requirement.
- Context, outer receipt, protected-root and environment-key digests use the
  same canonical compact/sorted JSON bytes. `protected_roots_sha256` is the
  SHA-256 of the canonical `protected_read_roots` array, and
  `environment_keys` binds the exact sorted sanitized child-environment key
  set. Before candidate execution,
  `run-isolated.py` strips every key whose name begins
  `SAMVIL_BOOTSTRAP_`, including the two required parent-only keys.
- Direct-versus-inherited policy equivalence compares only: exact
  `profile_class`; SHA-256 of the fixed trusted source-template bytes before
  path substitution; a trusted sentinel-rendered normalized-policy digest; the
  exact sanitized environment-key set; and behavioral allow/deny decisions.
  Global substring replacement or searching expanded profile bytes is
  forbidden. The trusted source template and its ordered slot manifest declare
  every non-overlapping `invocation_root` and `execution_root` substitution
  slot. The normal renderer fills those slots with the controller-known exact
  canonical literals; the normalization renderer fills the same slots with the
  fixed sentinels `<INVOCATION_ROOT>` and `<EXECUTION_ROOT>` and hashes those
  rendered bytes. Nested roots are valid, including the normal case where
  `execution_root` is below `invocation_root`, because neither literal is ever
  found by substring search in expanded bytes. Rendering and normalization
  fail closed if the trusted template/renderer exposes a missing, extra,
  duplicated, reordered, overlapping or unexpected path-bearing slot or path
  occurrence outside the declared manifest. Candidate bytes cannot provide or
  alter the template, slot manifest, slot spans, sentinels or trusted literals.

Inherited validation executes behavioral probes rather than accepting claims:

- for each protected read root, the list probe is exactly
  `os.listdir(root)`, and the open/read-authority probe is exactly
  `os.open(root, os.O_RDONLY | os.O_DIRECTORY)` followed by `os.close(fd)` only
  if the open unexpectedly succeeds. Each operation must raise `OSError` with
  `errno == EPERM`; `EISDIR`, `ENOENT`, `EACCES`, any other errno and success
  are failures;
- the paired create-write probe is exactly
  `os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)`. It must raise
  `OSError` with `errno == EPERM`; `ENOENT`, `EACCES`, `EISDIR`, any other errno
  and success are failures. If open unexpectedly succeeds, the probe closes the
  descriptor immediately, returns a typed failure and never executes candidate
  code;
- writing, reading and deleting `temp_probe_path` succeeds;
- reading the exact execution root succeeds;
- AF_INET loopback bind and connect each fail with `EPERM`; creating an
  unbound socket object may succeed and is not itself a failure.

The loopback-only negative control is class-selection rejection, not execution
under a broader profile: a context/receipt naming
`pinned-full-gate-loopback-only` must be rejected before any inherited probe,
Task -1 import or candidate execution. No Task -1 code is executed or imported
under that profile. The probe module reports typed evidence to its trusted
caller but cannot select a profile or issue a final PASS.

Protected-write post-absence is outer evidence, not an inherited-probe claim.
The probe may be unable to call `lstat` because the inherited sandbox correctly
denies it. After the sandboxed launcher/probe exits, the outer trusted
controller calls `os.lstat(path)` again and requires `ENOENT`. In inherited
mode the Task -2 controller performs the pre-entry and post-exit checks around
the one outer sandbox; in direct mode the committed trusted controller performs
them around its one `sandbox-exec`. If an artifact exists, the controller
captures its type/identity in the path-free failure evidence and returns a typed
blocker; it must not silently remove the artifact before evidence capture. The
pre-entry result is bound by the context/outer-bootstrap evidence, while the
post-exit result belongs to the final outer controller/verifier run receipt;
the pre-existing `samvil.bootstrap.outer-receipt.v1` cannot claim evidence from
after its own creation.

Inherited mode is fail-closed and is never authorized by an environment
variable or command-line flag alone. Before running any untrusted command, the
launcher must independently require and verify all of the following:

- a fresh invocation nonce is present;
- the expanded outer profile file exists and its SHA-256 equals the expected
  profile digest;
- an independently generated outer-bootstrap receipt pins that same profile
  digest and invocation identity;
- actual probes prove that protected-root list/read and paired protected-path
  create-write operations are denied with `EPERM`;
- actual AF_INET loopback bind and connect probes are denied with `EPERM`;
- an invocation-temp write probe and exact-root read probe both succeed.
- the outer trusted controller's post-exit `os.lstat` checks prove every paired
  protected write path remains absent before it can issue the final verdict.

A forged inherited-mode request outside a sandbox, missing nonce or profile,
missing or mismatched digest/receipt, or weakened denial must return a typed
blocker. Candidate output and candidate-generated receipts remain untrusted;
only the outer trusted controller may issue PASS. Bootstrap variables and
context may be propagated only among trusted Task -1 test, verifier and
launcher processes, and must be stripped from the candidate command
environment.

### Task -2 TCB completion — invocation-owned tool facade

The first plan-only gate-construction attempt exposed that the prior bootstrap
executable closure was incomplete. It did not establish canonical PASS.
Completing that closure is part of the Task -2 trusted
computing base; it does not expand production behavior, product scope, or the
sandbox's authority.

- Before creating the facade, use `git grep` against tracked gate-reachable
  files to enumerate every supported `mktemp` argument shape. At this plan
  correction, the complete tracked allowlist is
  `scripts/dogfood-smoke.sh:60`:
  `mktemp -d -t samvil-dogfood-smoke-XXXXXX`.
- Create a bootstrap-owned, digest-pinned `tools/facade/bin/mktemp` Python
  facade. It accepts only the enumerated shape, generates a bounded sequence of
  candidate names below the invocation-owned `TMPDIR`, and calls
  `os.mkdir(candidate, 0o700)` directly. Only `EEXIST` permits a bounded retry;
  every other error fails closed, and only the successfully created path is
  printed. There is no reservation file, unlink step or check-then-create gap.
  It never execs
  `/usr/bin/mktemp` or another helper.
  Unknown flags, prefixes, missing arguments, extra arguments, or newly tracked
  shapes fail closed. Focused probes must prove the allowed shape writes only
  below invocation `TMPDIR` and every unknown shape is rejected.
- Do not execute the `/usr/bin/git` xcrun shim. Copy the exact
  regular `/Library/Developer/CommandLineTools/usr/bin/git`, `git-shell`, and
  `scalar` binaries plus
  `/Library/Developer/CommandLineTools/usr/libexec/git-core` under the exact
  relative topology `<temp>/tools/usr/bin` and
  `<temp>/tools/usr/libexec/git-core`, preserving git-core symlinks. Every
  symlink must resolve inside `<temp>/tools/usr` and every target must exist;
  missing or external targets block preflight. Set `GIT_EXEC_PATH` to the
  copied git-core path, and hash the complete copied `tools/usr` tree, all
  three regular bin targets, and the symlink inventory. Probe copied
  `git --version`, `git --exec-path`, and `git rev-parse`. No read permission
  for `/var/select/developer_dir` is allowed.
- Copy the exact Codex bundled Node dependency tree from
  `codex-primary-runtime/dependencies/node` into the invocation root. Reject
  symlinks that resolve outside that copied tree, record tree and executable
  digests, and place the copied `node/bin` before system paths. The current
  bundle contains `node` and bundled `pnpm` bytes but no `npm` executable, so
  create a bootstrap-owned, digest-pinned `node/bin/npm` compatibility facade
  that accepts only the tracked gate's required `npm run <script>` and
  `npm <script>` forms. The facade is executed directly by copied Node, parses
  the fixture `package.json`, accepts only the exact tracked `build` and
  `start` command bodies, and spawns copied Node without a shell or pnpm
  self-spawn. Unknown arguments, script names or command bodies fail closed.
  The preflight must prove
  `shutil.which("npm")` resolves inside the invocation root before any dogfood
  subprocess runs, so `/opt/homebrew` is never probed or allowed.
- Pin the exact effective `PATH` order as `tools/facade/bin`,
  `tools/usr/bin`, copied `node/bin`, `/usr/bin`, `/bin`, `/usr/sbin`, `/sbin`.
  The bootstrap receipt must bind the facade script digest, copied Git closure
  digest, copied Node closure digest, every required executable identity, this
  ordered path list, and the allowed/unknown-shape facade probe results.
- Retain `(deny default)`, no writes below `/private/var/folders`, no reads of
  `/opt/homebrew` or `/var/select`, and actual read/write denial probes for the
  real `HOME` and `CODEX_HOME`. Network authority is selected only by the
  trusted bootstrap according to the three fixed profile classes below.
- The tracked archive has no `.git`, but the future canonical full gate exercises
  `git rev-parse HEAD` and `git rev-parse --abbrev-ref HEAD`. After
  materializing the exact staged tracked snapshot and before creating ignored
  `mcp/.venv`, initialize an invocation-owned Git repository inside the temp
  snapshot using only copied Git, temporary identity, isolated config, and an
  invocation-owned empty hooks directory. Commit exactly the staged tracked
  files, assert its tree equals the previously calculated staged snapshot
  tree, assert `git remote` is empty, and bind the temporary commit, tree and
  branch identities into the bootstrap receipt. Never recursively read the
  source worktree while creating this metadata.

### Task -2 network correction — three fixed profiles, one Seatbelt layer

The plan's original statement that Phase 6 is "network-free" means it makes no
external request. The pinned original
`scripts/phase6-real-runtime-dogfood.py` nevertheless binds an ephemeral
`127.0.0.1` TCP port, starts the generated app with `npm start`, and fetches
that app over loopback. Running the unmodified original full gate under a
profile that denies every socket therefore fails at `bind(("127.0.0.1", 0))`
with `EPERM`. Skipping or rewriting that pinned runtime-real test would weaken
the baseline and is forbidden.

Task -2 keeps the single-sandbox topology but fixes three immutable policy
classes. Each subprocess is enclosed by exactly one Seatbelt profile; profiles
are never nested or switched inside a running sandbox:

1. `release-control-network-zero` is used for uncommitted Task -1 pure/control
   tests, inherited launcher probes and staged static review. It contains
   `(deny network*)` and no network allow rule. The language runtime may create
   an unbound AF_INET socket object, but loopback bind and connect probes must
   fail with `EPERM`; no endpoint or packet authority is granted. It may retain
   the process authority needed by the trusted controller to launch its test
   process, so it is never the final boundary for an untrusted candidate.
   Broad `mach-lookup`, POSIX shared-memory and unproven `sysctl-read` grants
   are absent; otherwise a same-PID `exec` of `launchctl`/XPC could ask an
   external daemon to create a process that does not inherit the caller's
   Seatbelt or resource limit. Any indispensable Mach service must be an exact,
   independently probed allowlist entry. Signal authority is limited to
   `(target self)` and `(target children)` so the launcher can supervise its
   one child but that child cannot signal its parent or any pre-existing
   same-UID host process.
2. `release-candidate-network-zero` is used only by normal direct launcher mode
   for untrusted candidate checks. It has the same network, protected-root,
   execution-root, invocation-root and sanitized-environment decisions as the
   control class, but allows only the initial candidate `process-exec`, denies
   `process-fork` and signal authority, and makes fork/spawn/detached-child
   attempts fail with `EPERM`. The trusted external controller invokes exactly
   one `sandbox-exec`; candidate bytes cannot select this class or the broader
   control class. Its only device read exception is the exact literal
   `/dev/null`; no `/dev` subpath or other device authority is granted. Pytest
   receives an invocation-owned trusted config whose fixed bytes are embedded
   in the pinned verifier, not a candidate-owned config and not `/dev/null` as
   config discovery input.
3. `pinned-full-gate-loopback-only` is used only for the exact trusted wrapper
   command plus its fixed `/bin/bash scripts/pre-commit-check.sh` candidate
   subcommand and pinned `mcp/tests` collection/probe sequence. It retains
   `(deny network*)` and adds
   only `(allow network-inbound (local tcp "localhost:*"))` plus
   `(allow network-outbound (remote tcp "localhost:*"))`. Broad rules such as
   `(allow network*)`, `(allow network* (local ip))`, wildcard remote IPs,
   UDP, Unix sockets, DNS/mDNS sockets and external TCP remain forbidden. The
   wildcard port is required because Phase 6 binds port `0`; macOS Seatbelt
   grants the fixed IPv4 localhost TCP endpoint class and cannot prove that
   only one invocation-owned ephemeral port is used. The trusted runner proves
   only that fixed endpoint class plus the exact gate and denial probes below.

The control-only full-gate runner CLI is target-kind-discriminated and exact,
with no command separator, generic command tail, root argument or profile-class
option. `original` and `candidate_precommit` use exactly:

```text
<PINNED_PYTHON> <PINNED_CONTROL>/tools/release-control/run-full-gate-isolated.py --manifest ABS_JSON --nonce HEX64 --timeout POSITIVE_SECONDS --receipt ABS_JSON --denial-log ABS_LOG
```

`candidate_postcommit` instead requires `--prior-receipt ABS_JSON` exactly once
in the fixed position immediately after `--manifest ABS_JSON`:

```text
<PINNED_PYTHON> <PINNED_CONTROL>/tools/release-control/run-full-gate-isolated.py --manifest ABS_JSON --prior-receipt ABS_JSON --nonce HEX64 --timeout POSITIVE_SECONDS --receipt ABS_JSON --denial-log ABS_LOG
```

`original` and `candidate_precommit` reject `--prior-receipt`; a
`candidate_postcommit` invocation missing it is rejected. Duplicate,
reordered, unknown or missing options fail closed. The nonce, timeout and
absent output targets follow the strict launcher rules above;
receipt and denial-log parents must be existing canonical directories, and
each created output must remain an exclusive regular `nlink == 1` file through
final `fsync`. The manifest is a canonical regular `nlink == 1` external
control artifact, outside the target tree and candidate-writable roots, whose
caller spelling and descriptor identity remain stable before and after use.
It uses exact schema `samvil.full-gate-manifest.v1`, rejects unknown or missing
fields and binds exactly:

- the nonce; exact amended control commit SHA/tree SHA; and the ordered
  path/mode/blob and SHA-256 map for all five Task -1 control files;
- a discriminated `target_kind` and exact tracked path/mode/blob inventory:
  `original` binds the exact source commit SHA and tree SHA;
  `candidate_precommit` binds the exact candidate tree SHA, expected parent
  SHA and control authorization digest while requiring the final commit field
  to be canonically and explicitly `null`; and `candidate_postcommit` binds
  the exact final commit SHA, tree SHA and expected parent SHA and must match
  the precommit tree and authorization digest. It additionally binds
  `prior_receipt_sha256` and the expected precommit nonce, control commit/tree,
  authorization digest and `expected_precommit_manifest_sha256`;
- a digest-pinned verified Git object pack/closure containing exactly the
  required commits, trees and blobs. It may carry a candidate tree and blobs
  without a final candidate commit object for `candidate_precommit` and must
  carry and verify the exact final commit for `candidate_postcommit`;
- the exact trusted wrapper command vector, wrapper blob/digest, ordered probe
  command vectors/digests, fixed candidate subcommand
  `/bin/bash scripts/pre-commit-check.sh`, the entry script, Phase 6 script/test and
  complete collected `mcp/tests` inventories;
- the expected import allowlist and import-manifest digest, with every
  `tools/release-control` import in the gate process forbidden;
- copied Codex Python 3.12 runtime/dependency and reviewed non-platform
  portable-tool archives, runner-derived trusted facade digests, and an ordered
  canonical host-tool manifest. Apple platform/SSV tools execute only at their
  verified absolute host paths; no
  Apple system binary is raw-byte copied and executed;
- the exact five `/tmp` log names, semantic counter schema/expected values and
  deterministic receipt schema.

The current `samvil.full-gate-manifest.v1` foundation has no trusted storage-
boundary descriptor and therefore cannot authorize production execution or
PASS. Enabling PASS requires a separately reviewed schema revision that binds a
Task -2-issued, single-invocation storage attestation: exact
`storage_boundary_class=invocation_exclusive_kernel_quota`, fixed hard capacity
no greater than the manifest aggregate limit, held filesystem/mount identity,
adapter/policy digest, exclusive-writer proof and cleanup/unmount contract. The
matching PASS receipt must bind `storage_boundary_class` and
`storage_boundary_sha256`. Candidate, CLI and environment input can neither
supply nor weaken this evidence. A v1 manifest or an absent/invalid/drifted
attestation deterministically returns `UNSUPPORTED_INVOCATION_STORAGE_QUOTA`
before materialization.

Every manifest-referenced input artifact, including the Git object pack and
runtime/dependency/portable-tool archives, must be an external canonical regular
`nlink == 1` file with an exact digest and stable held-descriptor identity.
The `candidate_postcommit` prior receipt follows the same external canonical
regular `nlink == 1` and stable held-descriptor rules, has strict duplicate-key,
depth, integer, Unicode and size bounds, and must match
`prior_receipt_sha256`. Before any postcommit object materialization or target
command, the runner independently requires its status/verdict to be `PASS` and
its nonce, control commit/tree, candidate tree, authorization and manifest
identities to match the postcommit manifest exactly. In particular,
`expected_precommit_manifest_sha256` must equal the manifest SHA bound by the
accepted prior receipt.
Candidate bytes, environment variables and generic launcher CLI cannot
provide, redirect or replace the manifest or any artifact. `profile_class` is
not a manifest field:
it is never accepted from CLI or environment input, and the runner derives
`pinned-full-gate-loopback-only` internally only after the exact
command/tree/test/import manifest matches. It then validates its own
control commit/file digests, materializes tracked target bytes only from the
verified Git objects into an invocation-owned temporary root, copies and
verifies the pinned Python/tool closure, builds the internal `mcp/.venv`
facade, creates temporary `HOME`, `CODEX_HOME`, `CLAUDE_CONFIG_DIR`,
`GNUPGHOME`, `TMPDIR`, `XDG_*` and Git configuration before any repository or
target command, and invokes exactly one fixed trusted wrapper under exactly one
Seatbelt layer. That wrapper alone owns the authority channel. It executes the
ordered fixed runtime/import/test probes and candidate subcommand as separate
children whose stdout/stderr are redirected to non-authoritative held files;
the candidate receives no authority path, descriptor or environment key.
Before `sandbox-exec`, the outer runner creates one bounded `O_CLOEXEC` pipe
and passes only its write endpoint plus an exact nonce to the wrapper. The
runner retains the read endpoint, supervises the exact wrapper PID plus a
kernel-derived birth identity (`proc_bsdinfo` seconds+microseconds on macOS,
`/proc/<pid>/stat` start ticks on Linux; second-resolution `ps lstart` is not
authority) and treats the pipe as exclusive only because no other process may
inherit or obtain its write endpoint; an anonymous pipe does not authenticate
the writer of each frame. The wrapper receives that one endpoint only for its own initial exec,
immediately restores non-inheritable/`CLOEXEC`, closes every duplicate, and
writes canonical length-prefixed frames bounded by the manifest. Every probe
or candidate child uses `close_fds=True`, an explicit empty `pass_fds`, and
separate held stdout/stderr descriptors. The outer runner rejects malformed,
duplicate, reordered, oversized, wrong-nonce or post-wrapper-exit frames, any
wrapper PID/start drift, and any demonstrated authority-FD leak to a child.

The materialized target snapshot, trusted wrapper, runtime, dependencies,
facade and tool closure are read-only under the profile. Candidate and probe
writes are limited to disjoint invocation-owned scratch roots plus the exact
fixed-log protocol; target bytes cannot be chmodded, renamed, replaced or
created. The runner validates every executable/test/import identity immediately
before its phase and revalidates the complete tracked path/mode/blob inventory
and all runtime/facade/tool identities after the candidate exits and before
PASS. Independent probes execute only held/materialized verified bytes, never
paths that candidate code can replace.

The full-gate manifest also fixes CPU/wall/RSS/address-space, `RLIMIT_FSIZE`,
`RLIMIT_NOFILE`, maximum observed descendant count, per-file logical bytes,
entry/depth bounds, candidate stdout/stderr bytes, authority frame count and
per-frame/aggregate frame bytes. The runner concurrently drains bounded
candidate stdout/stderr and the authority pipe so no child can deadlock the
controller; exceeding any controller-observable limit terminates the supervised
tree, invalidates PASS and emits a typed resource blocker. Logical aggregate
invocation-root byte counts and final no-follow size/entry scans remain
diagnostic and cleanup checks only; they are not an aggregate quota and cannot
authorize PASS. The Task -2 kernel quota is the sole hard storage-capacity
boundary, and quota exhaustion after admission emits
`GATE_INVOCATION_STORAGE_QUOTA_EXCEEDED`.

The runner acquires the fixed exclusive `/tmp` full-gate lock, requires all
five fixed log paths and both output paths to be absent, allows no other `/tmp`
write, and moves each verified log into the invocation root before releasing
the lock. Pre-existing logs/outputs, lock contention, missing or extra logs,
move/identity mismatch, temp cleanup failure or invocation-root cleanup failure
replaces every prior result with a typed blocker. A PASS requires the trusted
runner to independently match the discriminated target identity, object
closure, gate/runtime/test/import manifests, independently observed
runtime/import/test evidence, candidate exit status, semantic counters and the
Task -2 storage-boundary attestation. It additionally binds
`storage_boundary_class` and `storage_boundary_sha256`;
manifest text, candidate stdout/stderr, a forged `PASS` line or
candidate-authored counters are never authority. The path-free receipt contains
only semantic counters, typed promotion limitations and command/content/
profile/import/identity/tree/runtime digests and must be byte-identical when the
same manifest and nonce are retried. It records
`LOOPBACK_PORT_OWNERSHIP_NOT_OS_ISOLATED` and
`DETACHED_DESCENDANT_NOT_OS_ISOLATED`, with no attempt-free, exact-port-
ownership or complete descendant-absence assertion. Both limitations block
`STAGE_A_PROMOTION_READY`. A `candidate_postcommit` receipt additionally binds the
exact final commit and the matching `candidate_precommit` tree and
authorization digest plus the accepted prior receipt digest.

`INVOCATION_STORAGE_QUOTA_NOT_OS_ENFORCED` must never appear in a PASS receipt's
`promotion_limitations`: unlike the two limitations above, it is a canonical
runtime-admission blocker. The failure receipt uses
`samvil.full-gate-failure.v1`, verdict `BLOCKED`, exit 2 and the exact
`UNSUPPORTED_INVOCATION_STORAGE_QUOTA` status with no local path. Retrying the
same manifest and nonce must produce a byte-identical failure receipt and no
candidate execution, materialization or release event.

The loopback-only profile is not a candidate-selectable mode. The trusted
bootstrap must fail closed unless all of the following are true before
Seatbelt invocation:

- Task -2 supplied a fresh single-invocation, descriptor-held attestation for an
  invocation-exclusive kernel-quota filesystem, and its class, hard capacity,
  filesystem/mount identity, adapter/policy digest and exclusive-writer proof
  match the reviewed manifest. This check precedes wrapper, probe, candidate and
  materialization work;
- the requested profile class is derived by the trusted controller from a
  fixed trusted-wrapper/candidate-subcommand/probe manifest, not from an
  environment variable, CLI flag,
  candidate receipt or candidate-controlled configuration;
- the trusted wrapper, executable candidate entrypoint,
  `scripts/pre-commit-check.sh`, Phase 6 script, Phase 6 test and complete
  collected `mcp/tests` path/blob/mode inventory
  match the staged snapshot identities recorded before the run;
- the collected test/import manifest proves no `tools/release-control` module,
  candidate verifier, candidate launcher or candidate authorization helper is
  imported or executed under the loopback-only profile;
- the profile digest, selected class, exact command manifest, entrypoint/test
  digests and import manifest are bound into the outer bootstrap receipt.

Profile acceptance is behavioral as well as textual. Before any gate:

- both network-zero classes must reject IPv4 loopback bind and connect with
  `EPERM`; `release-candidate-network-zero` must additionally reject exact
  `fork`, native-FFI fork, `posix_spawn` and parent-signal probes with `EPERM`;
- both network-zero classes must explicitly deny protected-root metadata and
  existence queries before the global runtime metadata allowance: exact
  `stat`/`lstat` return `EPERM`, while `access`/`exists` return only false and
  reveal no size, type, mode or timestamp;
- the control class's inherited wrapper must fix `RLIMIT_NPROC=(1,1)`, make
  direct/native fork and `posix_spawn` fail with `EAGAIN`, deny
  `launchctl`/XPC communication, and leave no external-controller post-check
  process or invocation artifact;
- after every direct candidate outcome, the trusted controller must remove the
  candidate-writable invocation tree without following symlinks, repair
  candidate-applied restrictive directory modes as needed, and verify the root
  is absent. Cleanup never changes modes or contents of non-directory entries:
  files, FIFOs, hardlinks and symlinks are unlinked only, so a same-filesystem
  hardlink cannot mutate a signed snapshot or external owner inode.
  Cleanup failure replaces any prior PASS, FAIL or resource result with the
  typed `INVOCATION_CLEANUP_FAILED` blocker and exit code 2;
- for the subprocess-capable full gate, the trusted wrapper and outer runner
  maintain a baseline plus continuous descendant inventory keyed by PID and a
  kernel-derived birth identity, including detected `setsid` children. A `ps`
  row whose parent/birth binding cannot be corroborated is retained as an
  unavailable-identity sentinel so a possibly relevant wrapper/descendant
  blocks before file inspection rather than disappearing from accounting. Any descendant
  observed after nominal candidate/probe completion, or any cleanup required,
  makes the local gate fail. Process-group cleanup remains allowed for the
  owned wrapper group. Detached PID signaling is allowed only through an
  identity-bound OS handle (Linux `pidfd`); macOS has no reviewed atomic handle
  in this implementation, so after quota authority succeeds it blocks before
  temp creation, materialization or execution with
  `DETACHED_PROCESS_SIGNAL_UNAVAILABLE` and never calls `kill(pid)` for a
  detached child. This is detection and fail-closed cleanup, not a kernel
  process namespace: macOS `kqueue`
  `NOTE_FORK` does not expose the child PID and polling can miss a sufficiently
  fast fork/reparent sequence. A supported-host PASS receipt therefore always
  records `DETACHED_DESCENDANT_NOT_OS_ISOLATED`, which permits only disposable
  local Stage A transaction rehearsal but blocks public Stage A mutation and
  `STAGE_A_PROMOTION_READY` until a supported host supplies a reviewed
  VM/process namespace or equivalent OS boundary;
- `pinned-full-gate-loopback-only` must successfully bind an ephemeral
  `127.0.0.1` TCP port and connect over the fixed IPv4 localhost TCP endpoint
  class, but neither Seatbelt nor the receipt may claim exact-port ownership or
  that no other localhost attempt occurred;
- the loopback-only profile must reject a TCP connect to the TEST-NET address
  `192.0.2.1` with `EPERM` and must not resolve a hostname to perform the
  probe;
- all three profiles must retain the required real-profile read/write denials,
  only their explicitly partitioned invocation-owned scratch/log write
  authority, read-only executable/snapshot closure and sanitized environment
  keys.

Any command-manifest drift, newly collected test, unexpected import, external
connect result other than `EPERM`, or attempt by Task -1/candidate bytes to
select the loopback profile is a bootstrap blocker. Loopback permission is
test infrastructure authority for the pinned original and candidate full
gates only; it exists only in the committed control-only full-gate runner and
is never part of the generic release-control launcher, candidate runtime
authority or quarantine candidate contract. Exact trusted-wrapper/candidate-
subcommand/probe/tree/test/import/runtime manifests and external candidate
authorization prevent arbitrary
candidate command selection; they do not turn `localhost:*` into an
invocation-owned port boundary. Record
`LOOPBACK_PORT_OWNERSHIP_NOT_OS_ISOLATED` and
`DETACHED_DESCENDANT_NOT_OS_ISOLATED` as typed promotion limitations.

The bootstrap trusted computing base is a digest-pinned two-class host/runtime
closure, not the current repository venv:

1. `copied_application_runtime` contains the Codex-owned Python 3.12, copied
   dependency bytes, copied Codex Node tree plus npm compatibility facade,
   runner-embedded trusted wrapper/mktemp/Python facade scripts and only
   explicitly reviewed non-platform portable tools such as the already proven
   copied CLT Git/git-core topology and exact CLT `lipo`/`otool` binaries. A Mach-O with non-zero Apple platform
   identifier, an SSV `restricted` source, or `CS_PLATFORM_PATH` dependence is
   forbidden in this archive and must never be copy-executed. Every allowed
   portable tool must have platform identifier zero, a closed copied load/exec
   topology and a successful bounded copied-path behavioral probe.
2. `canonical_host_tools` contains the exact absolute Apple platform/SSV
   executables required by the reviewed gate/probe closure.
   These use a two-stage admission: first manifest-bound static identity,
   signing and embedded-parser load-closure validation; then exactly one fixed
   bounded behavior probe at the canonical path. Only a GREEN probe admits the
   path for later gate execution. The minimum reviewed roles include
   `sandbox-exec`, `codesign`, `env`, `bash`, `sh`, `mkdir`, `chmod`,
   `grep`, `xargs`, `sed`, `tail`, `head`, `find`, `cat`, `true`, `false`,
   `file`, `ps`, `echo` and `dirname`. The exact copied CLT Git/git-core plus
   `lipo`/`otool` closure remains in class 1; `/usr/bin/git`, `/usr/bin/lipo`
   and `/usr/bin/otool` xcode-select shims are never executed. Static
   script/Python subprocess review
   may add an executable only by adding an exact manifest row and review test;
   an unlisted exec is denied by the Seatbelt `process-exec` allowlist.

This classification is a scope correction backed by the macOS boundary:
byte-identical temp copies of `/usr/bin/sandbox-exec` and `/usr/bin/env` both
hung without output in uninterruptible `UE` state, while the copied non-platform
Codex Python executed successfully. Every previously proposed `/bin` or
`/usr/bin` utility inspected here carries Apple `Platform identifier=16` and
the SSV `restricted` flag; the local XNU SDK separately defines
`CS_PLATFORM_BINARY` and path-derived `CS_PLATFORM_PATH`. The circuit breaker
therefore prohibits any further copied Apple-system-binary execution probe.

The first staged Task -1 run cannot trust the parser that Task -1 is creating.
Before any Task -1 bytes exist or execute, the pre-existing Task -2 external
controller therefore materializes its own canonical
`host-tool-identity-parser.v1` from controller-embedded source bytes outside the
repository and candidate-readable roots. The Task -2 receipt binds that source
SHA-256, materialized content/mode/interpreter identity, supported Mach-O/code-
directory schema, per-file/aggregate/depth/load-command limits, exact input
descriptor identities and canonical output digest. It never imports or executes
Task -1. During staged validation, only this external parser is authority; the
staged runner parser processes the same adversarial corpus and must produce
byte-identical canonical results but cannot issue PASS. After the autosquashed
five-file control commit exists, the committed runner parser blob/digest is
re-pinned and may become authority only after another exact comparison against
the external Task -2 parser. Any parser byte, limit, corpus or result mismatch
blocks trust promotion.

Paths, file identities, filesystem flags, Mach-O/library closure, code-signing
results and SHA-256 digests are recorded before use. The copied Python must be a real
Mach-O Python whose runtime-reported major/minor is exactly `3.12`;
shell/trivial `exit 0` stubs are rejected. The invocation manifest binds the
exact patch version, architecture, Mach-O slices, executable/content hashes,
`otool` load commands and `@rpath` resolution of the selected runtime. Its
non-system load closure must stay inside the copied runtime, while immutable
system dylibs use an explicit allowlist. An incompatible copied runtime fails
before Seatbelt with typed `UNSUPPORTED_HERMETIC_RUNTIME`; an incomplete,
mutable, differently signed or unsupported canonical host toolchain fails with
typed `UNSUPPORTED_CANONICAL_TOOLCHAIN`. No candidate or newly created Task -1
Python module is imported by the bootstrap.

Every `canonical_host_tools` row binds a fixed role, absolute path, root
ownership, exact mode/link count/size/filesystem flags, read-only-filesystem
status, device/inode identity, SHA-256, Mach-O
slices/load closure, Apple anchor, signing identifier, platform identifier,
designated requirement/CDHash, exact behavior probe and stable pre/post held-
descriptor/path identity. Every row requires the canonical restricted read-only
SSV path and non-zero Apple platform identifier. Exact link counts are manifest values rather than a
global `nlink == 1` rule because Apple intentionally hardlinks some tools.

PATH lookup never selects unbound authority. Retain the exact Task -2 order
`tools/facade/bin`, `tools/usr/bin`, copied `node/bin`, `/usr/bin`, `/bin`,
`/usr/sbin`, `/sbin`. The first three roots are read-only invocation-owned
closures containing the trusted Python/mktemp wrappers, copied CLT Git/git-core
plus `lipo`/`otool`, copied Node/pnpm and the exact npm compatibility facade;
every facade execs only its manifest-bound invocation-root or canonical-host
target. Seatbelt permits `process-exec` only for the trusted wrapper, every
exact executable in those copied/facade closures and ordered canonical host-
tool paths. A
copied Apple binary, alternate spelling, `xcrun`/shim fallback, unlisted exec or
identity drift is `UNSUPPORTED_CANONICAL_TOOLCHAIN` before target PASS.

Code-signing evidence is produced only by canonical absolute
`/usr/bin/codesign`, classified separately as
`apple_platform_identity_verifier`. The runner itself bounded-reads and hashes
that verifier before execution and the manifest fixes its root ownership, mode,
exact link count, filesystem flags, Mach-O slices, SHA-256 and stable pre/post descriptor/path
identity. It is invoked with exact argv only for `--verify --strict` plus the
manifest-row Apple-anchor/identifier requirement and `-d --verbose=4`; PATH lookup,
another spelling/tool, environment-selected requirements and copied fallback
are forbidden. A strict bounded parser requires exit 0 and the exact expected
identifier, format/slices, platform identifier, designated-requirement result
and CDHash, rejects duplicate/missing/unknown security fields, and binds the
verifier identity plus parsed result digest into the bootstrap/full-gate
receipt. The verifier is not used to bootstrap its own identity: its exact
manifest-bound bytes and canonical root-owned system path are the platform TCB.
Its row enters distinct `PLATFORM_VERIFIER_PINNED` state from the external
Task -2 parser's held bytes/path/SSV/code-directory evidence and never requires
codesign to verify its own signing identity. Self display/verify output, if
collected, is bounded non-authoritative diagnostic only. Successful exact
verification of the first non-codesign canonical row is the verifier behavior
probe; only then may it verify the remaining rows.
Before `codesign`, `file`, `lipo` or `otool` is executed, the current authority
parser—external Task -2 before the control commit, committed runner only after
re-pinning—independently validates magic, slices,
load-command bounds, platform identifier and CodeDirectory/CDHash inputs for
their held bytes. This creates `STATIC_ADMITTED` evidence only. The external
tool may then run exactly its bounded behavior/cross-check probe; only probe
GREEN creates final `ACCEPTED_ROW` authority for later gate execution. No tool
bootstraps itself or an earlier authority layer from its own stdout.

For every ordered canonical host-tool row except the separately pinned
`codesign` verifier row, the two codesign invocations and
channels are exactly, with `<IDENTIFIER>` and `<ABS_TOOL>` taken only from that
already schema-validated row:

```text
argv[0] /usr/bin/codesign
argv[1] --verify
argv[2] --strict
argv[3] --verbose=2
argv[4] -R=anchor apple and identifier "<IDENTIFIER>"
argv[5] <ABS_TOOL>
```

The verify call requires exit `0`, empty stdout, and parses only bounded stderr
for the three non-duplicated success statements `valid on disk`, `satisfies its
Designated Requirement`, and `explicit requirement satisfied`, all naming the
exact target where applicable. Then run exactly:

```text
argv[0] /usr/bin/codesign
argv[1] -d
argv[2] --verbose=4
argv[3] -r-
argv[4] <ABS_TOOL>
```

The display call requires exit `0`; bounded stdout contains exactly one
canonical designated-requirement line, while bounded stderr alone supplies the
strict metadata fields above. No shell, combined verify/display call, alternate
option order, additional argument or channel substitution is accepted.

The repository's ignored `mcp/.venv/bin/python` is never executed: its
interpreter resolves outside the repository and its editable `.pth` points at a
mutable worktree. Instead, copy the Codex workspace Python runtime and required
site-package bytes into the invocation temp root, reject escaping symlinks,
hardlinks, `.pth`, `sitecustomize`, `usercustomize` and external
`direct_url.json`, then import `samvil_mcp` only from the exact archived Git
snapshot. Before any target import, the trusted wrapper pins its bootstrap and
audit primitives and records the exact module inventory. The independent
probes require `sys.executable`, `sys.prefix`, `sys.base_prefix`, every
`sys.path` entry and every imported module path/hash to stay within the
hermetic runtime or exact temp snapshot, with user-site disabled.
Candidate-authored observation files, stdout, stderr and environment values
never satisfy this contract.

Because the unmodified original gate invokes the fixed relative path
`mcp/.venv/bin/python`, the bootstrap creates an invocation-owned facade at
`<temp-snapshot>/mcp/.venv` after the Git archive is materialized. Its
`bin/python`, `bin/python3`, `bin/python3.12`, `pyvenv.cfg` and site-packages
resolve only to regular copied files or internal symlinks inside the same temp
root and hermetic copied runtime. The outer probe rejects any external symlink,
editable `.pth`, user-site, original-worktree import or path escaping the temp
root. The live ignored repository `.venv` is neither read nor executed.

- [ ] Start with `env -i` and an explicit safe `PATH`; set temporary `HOME`,
  `CODEX_HOME`, `CLAUDE_CONFIG_DIR`, `GNUPGHOME`, `TMPDIR`, `XDG_*`, isolated
  Git global config, disabled credential helpers/askpass and disabled Git
  network protocols.
- [ ] Invoke `/usr/bin/sandbox-exec` directly with one inline profile rendered
  from this plan's fixed profile class: `(deny default)`, allow only required
  process/mach/system-library reads, allow file reads for the exact pinned
  control worktree, hermetic temp runtime and archived temp snapshot,
  explicitly deny the source repository checkout and every other linked
  worktree. The control class may allow read/write only for its exact Task -1
  temporary root and explicitly reviewed control files; the full-gate class
  further partitions that root into read-only snapshot/runtime/wrapper/tool
  closures and exact writable scratch/log/output leaves.
  The network-zero class includes no network allow rule; the pinned full-gate
  class includes only the two exact loopback TCP rules above.
- [ ] Copy only the pinned Python/runtime/dependency and runner-derived facade
  closure plus the separately reviewed non-platform portable-tool closure into
  the invocation temp root before sandboxed execution. Reject any Apple
  platform/SSV executable in those archives, plus every external
  symlink, editable-install, dynamic-library or import-path dependency. An
  incomplete closure is a bootstrap blocker, not permission to read the live
  venv or user runtime during gates.
  Execute every reviewed Apple platform shell/core/inspection tool only at its ordered
  `canonical_host_tools` absolute path after exact metadata/hash/codesign/load/
  behavior and pre/post identity validation. Bind `/usr/bin/codesign`
  separately as the platform identity verifier, and include the complete
  canonical-tool manifest, verifier identity and per-tool result digests in the
  receipt. No copied Apple binary may be launched even as a diagnostic probe.
- [ ] Materialize the temp-only `snapshot/mcp/.venv` facade from that copied
  closure before invoking the unmodified baseline gate. Verify all interpreter,
  configuration and package paths are internal to the invocation root, then
  prove the gate actually executed this facade by matching executable and
  import-manifest digests in the outer receipt.
- [ ] Original/candidate snapshots consumed by gates are materialized from
  pinned Git tree objects using `git archive`/`git cat-file` into the temporary
  root. The bootstrap and trusted verifier never recursively read the source
  working tree, so untracked entries—including the literal user-owned
  `$CODEX_HOME/` entry—are outside the readable input set.
- [ ] The existing normal gate writes five fixed files:
  `/tmp/samvil-pretest.log`, `/tmp/samvil-mdrefs.log`,
  `/tmp/samvil-hostparity.log`, `/tmp/samvil-forward.log`, and
  `/tmp/samvil-agent-inventory.log`. Acquire one exclusive bootstrap lock,
  require all five paths to be absent, allow only those exact files, capture
  their digests/output into the temporary receipt, then move them into the
  invocation temp root. A pre-existing file or lock contention is a blocker;
  broad `/tmp` write access is forbidden.
- [ ] Before Task -1 code exists, run bootstrap probes proving: system runtime
  and exact control inputs are readable; the temporary root is writable; a
  real-home sentinel and `$CODEX_HOME` candidate are unreadable/unwritable;
  the network-zero loopback bind/connect probes fail with `EPERM`; the
  pinned-full-gate loopback probe succeeds while its TEST-NET connect fails;
  an inherited trusted-control child-creation attempt is kernel-denied by the
  pinned `RLIMIT_NPROC=(1,1)` wrapper before a descendant exists; and a direct
  candidate child-creation attempt is Seatbelt-denied before a child exists.
- [ ] Record the expanded sandbox profile, its digest, environment-key list,
  executable digests, probe commands, denial log and result in a path-free
  bootstrap receipt.
- [ ] Add RED/GREEN acceptance cases proving: a forged inherited-mode request
  outside a sandbox fails; nonce/profile/digest/receipt mismatch fails; the
  correct outer sandbox succeeds; the candidate receives no bootstrap
  context; a context/receipt pinned to the loopback-only class is rejected
  before probes, Task -1 import or candidate execution; normal direct mode
  applies `release-candidate-network-zero`; inherited mode remains fixed to
  `release-control-network-zero`; their shared network/file/environment
  decisions and environment key sets agree; and the direct class alone has
  immutable process-fork/signal denial. Compare class-specific trusted
  source-template and sentinel-rendered normalized-policy digests without
  requiring raw expanded `profile_sha256` equality. Also prove all
  launcher commands/tests use the receipt-pinned `<PINNED_PYTHON>` with no
  system/user/PATH/live-venv fallback; the exact remaining direct/inherited CLI
  grammar; duplicate or
  misplaced inherited flags, environment-only, CLI-only and environment/CLI
  mismatch requests return their typed failures; unknown/missing schema fields
  fail; aliased/symlinked/non-canonical parents and pre-existing regular,
  directory, symlink or other non-regular receipt/denial-log targets fail;
  invalid output paths emit only stderr/nonzero exit and no output file; valid
  targets are exclusive regular `nlink == 1` files;
  receipt/denial-log collisions with each other, `temp_probe_path` or either
  protected write path fail before any file/probe/writable directory creation;
  nonexistent, file, symlink, `..`/`.`-aliased or otherwise non-canonical roots
  fail before writable action, and inherited CLI/context root mismatch fails;
  missing, non-canonical, non-directory, invocation-root-escaping or
  execution-root-contained `TMPDIR` fails before any probe or writable
  directory is created; all `SAMVIL_BOOTSTRAP_*` keys are absent from the child
  environment; and a nested-root case where `execution_root` is below
  `invocation_root` produces different raw expanded profile hashes across two
  invocations but the same trusted sentinel-rendered normalized-policy digest.
- [ ] Run pure/control/inherited Task -1 tests and staged-tree review inside one
  `release-control-network-zero` outer sandbox invocation whose trusted
  manifest excludes every direct-mode real-profile test. Before the control
  commit exists, do not execute the untrusted staged launcher outside that
  boundary. Instead, have the pre-existing Task -2 external controller render
  the independently pinned `release-candidate-network-zero` reference profile
  and apply `sandbox-exec` exactly once to the staged adversarial probe corpus;
  compare the staged launcher's pure rendered bytes/digests to that independent
  reference inside the outer control test. While no reviewed Task -2 quota
  adapter exists, invoke the staged full-gate entry only to prove that it returns
  `UNSUPPORTED_INVOCATION_STORAGE_QUOTA` before profile application, wrapper,
  probe, candidate or materialization. Portable tests may patch the capability
  check to exercise downstream orchestration, but those results are explicitly
  non-authoritative and must not be named actual-host end-to-end evidence. Once
  the adapter exists, run the exact staged canonical gate inside a third
  `pinned-full-gate-loopback-only` outer sandbox invocation after the trusted
  storage/command/test/import manifests are verified. That full-gate manifest
  must prove no Task -1 module is imported or executed. No path may nest or
  switch Seatbelt profiles. This pre-commit external-controller run is only
  bootstrap evidence for the uncommitted runner; an ephemeral controller or
  `/private/tmp` helper is never reusable Task 0 PASS authority.
- [ ] Before trust promotion, compare the direct candidate and inherited
  control evidence. Require distinct exact profile classes and class-specific
  trusted source-template/normalized-policy digests; require their shared
  real-home/network denials, allowed exact-root/temp decisions and environment
  key set to agree; and require only the direct candidate class to prove OS
  `process-fork`/spawn/signal denial. Retain each invocation's raw expanded
  `profile_sha256` only as its own exact-byte receipt evidence; do not require
  cross-invocation equality. After the one control commit is created, run the
  exact committed launcher/verifier direct integration manifest. The committed
  full-gate runner remains fail closed at the storage admission check until a
  reviewed quota adapter exists; only then may it run outside any existing
  Seatbelt and apply its fixed profile exactly once. Any weaker or divergent
  result requires an amend and a complete review/gate replay.
- [ ] Do not broaden permissions to the real `HOME`/`CODEX_HOME`, writes below
  `/private/var/folders`, external network in either mode, or loopback
  bind/connect and packet/endpoint authority in release-control network-zero
  mode. Unbound socket object creation alone is not authority and may succeed.
- [ ] Run the exact staged snapshot through one digest-pinned trusted wrapper
  inside one outer sandbox. The wrapper uses the copied Codex bundled Python
  3.12, runs the fixed independent runtime/import/test probes, and then runs
  the candidate subcommand `/bin/bash scripts/pre-commit-check.sh` with disjoint
  non-authoritative stdout/stderr. Use the digest-pinned local package artifact
  allowlist, `env -i`, invocation-owned
  `HOME`/`CODEX_HOME`/`GNUPGHOME`/`TMPDIR`/`XDG_*`, real-profile denials,
  loopback-only/external-denial probes, trusted wrapper/subcommand/probe/test/
  import manifests and the fixed-log lock/absence protocol. Never use the live
  `mcp/.venv` or external network.
- [ ] Commit safety is part of Task -2. Because repository
  `.githooks/post-commit` invokes `scripts/sync-cache.sh`, commit with
  `git -c core.hooksPath=<invocation-owned-hooks> commit`. Install only an
  invocation-owned pre-commit hook that re-runs the complete portable/control
  foundation suite and verifies the deterministic storage-admission blocker;
  install no post-commit hook. This may freeze PR #14's fail-closed foundation
  but is not canonical full-gate PASS or F0 green. After the quota adapter is
  reviewed, the hook must instead re-run and verify the exact canonical
  hermetic full gate. `--no-verify` is forbidden.

No untrusted working-tree helper may wrap, replace, parameterize or interpret
the outer bootstrap command/profile before the Task -1 control commit is
created and pinned. Verified inherited mode does not transfer PASS authority
to Task -1 or candidate code; it only prevents the impossible second Seatbelt
application while preserving the same denial boundary.

---

## 6. Task -1 — Build and pin the trusted release-control verifier

> **Current bridge run:** PR #14 already freezes this five-file fail-closed
> foundation. Do not run the `f6d50644...` fixup/autosquash procedure below.
> Audit and extend the preserved foundation only through current P0/P1/P3
> descendant commits as fixed by section 1.1.

This task runs on `codex/v433-safe-upgrade-design` before the implementation
worktree is created. It is a control-plane commit, not a fuse implementation
commit.

**Files:**

- Create: `tools/release-control/inherited_context.py`
- Create: `tools/release-control/run-isolated.py`
- Create: `tools/release-control/run-full-gate-isolated.py`
- Create: `tools/release-control/verify-quarantine-candidate.py`
- Create: `tools/release-control/tests/test_release_control.py`

- [ ] **A — pure protocol RED/GREEN:** write failing table/property tests, then
  implement `inherited_context.py` schema, canonical JSON/hash, exact-field,
  path-containment, regular-file/`nlink`, protected-root digest and sanitized
  environment-key validation. Cover env-only, CLI-only, mismatch, unknown and
  missing fields, wrong lowercase-hex widths, path aliases/escapes, wrong
  execution root, wrong cardinalities, missing/non-canonical/non-directory,
  invocation-root-escaping or execution-root-contained `TMPDIR`, escaping
  `temp_probe_path`, unsafe/non-immediate protected write basenames, output/probe
  path collisions, and altered receipt/context/profile digests. Cover existing
  canonical roots plus nonexistent, non-directory, symlink, `..`/`.` alias and
  CLI/context root mismatch. Every invalid root, `TMPDIR` or collision case must
  fail before creating any file, probe or writable directory.
- [ ] **B — real boundary probe RED/GREEN:** under the Task -2
  `release-control-network-zero` outer sandbox, prove each existing canonical
  protected directory is validated without content enumeration, then prove
  exact `os.listdir(root)` and
  `os.open(root, os.O_RDONLY | os.O_DIRECTORY)` operations each raise `EPERM`.
  Treat `EISDIR`, `ENOENT`, `EACCES`, other errno values or success as failure;
  close the descriptor only if open unexpectedly succeeds. Separately prove
  the outer controller sees `os.lstat(path) -> ENOENT` immediately before
  sandbox entry; the inherited probe's exact
  `os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)` returns `EPERM`;
  `ENOENT`, `EACCES`, `EISDIR`, other errno values and success fail. On
  unexpected success close immediately, return typed failure and execute no
  candidate. After sandbox exit the outer controller must again see `lstat ->
  ENOENT`; an artifact is reported with evidence and is not silently removed
  first. The inherited probe never claims the post-check. Also prove temp
  write/read/delete succeeds, exact execution-root read succeeds, and AF_INET
  loopback bind/connect return `EPERM`. Unbound socket creation need not fail.
  A loopback-only context/receipt is rejected before this probe phase; do not
  execute or import Task -1 under `pinned-full-gate-loopback-only`.
- [ ] **C — launcher RED/GREEN:** integrate exact
  full direct/inherited grammar after the receipt-pinned `<PINNED_PYTHON>`,
  including the inherited flag exactly once in its fixed position,
  CLI/context/environment root and nonce bindings, and trusted-caller timeout
  ownership. Reject system/user/PATH/live-venv interpreter fallback. In direct
  mode validate the caller's
  existing canonical absolute `TMPDIR` outside execution root before creating
  the direct invocation root strictly below it; reject bootstrap variables
  without the inherited flag. Validate absent receipt/denial-log targets and
  their existing canonical, non-aliased, non-symlink parents before any write;
  reject pre-existing regular, directory, symlink and other non-regular targets.
  Reject output/output, output/temp-probe and output/protected-write canonical
  collisions before creating any file or probe.
  On invalid output use stderr/nonzero exit only, otherwise create both
  exclusively and verify regular `nlink == 1`. Integrate direct-mode
  `sandbox-exec`, inherited-mode
  validator/probe calls without nested `sandbox-exec`, the inherited
  `RLIMIT_NPROC=(1,1)` no-shell exec wrapper, child supervision,
  denial-log capture, sanitized environment construction and complete
  `SAMVIL_BOOTSTRAP_*` stripping. Prove direct mode is fixed to
  `release-candidate-network-zero`, inherited mode is fixed to
  `release-control-network-zero`, and their shared network/file/environment
  decisions agree while the direct class carries the additional immutable
  process-fork/signal denials. Compare each class's fixed trusted
  source-template digest, trusted sentinel-rendered normalized-policy digest,
  decisions and environment keys without comparing raw expanded
  `profile_sha256`. Each normalized digest must be rendered from its trusted
  ordered slot manifest with fixed sentinels, never produced by global
  replacement/search of expanded bytes.
  Reject missing, extra, duplicated, reordered, overlapping or unexpected
  path-bearing slots/occurrences, and prove candidate bytes cannot define the
  template, slot manifest/spans, sentinels or literals. Add a RED/GREEN case
  where `execution_root` is nested below `invocation_root`: two invocations have
  different raw expanded profile hashes but the same trusted sentinel-rendered
  normalized-policy digest.
  A loopback-only class remains rejected before probes or candidate execution.
- [ ] **D — verifier integration/adversarial suite:** implement the outer
  verifier's independent Git tree/path/mode/blob, authorization and signature
  calculations and final verdict. RED/GREEN cases include forged PASS,
  self-replaced verifier, candidate-local authorization, changed authorized
  digest, Git replace refs, loose-object content substitution under an
  authorized OID, real-repository ref target, protected-profile read, socket attempt,
  direct and inherited detached-child creation attempts, and omitted expected
  test. Candidate output and candidate
  receipts remain untrusted bytes. The verifier must reject an inherited
  candidate request: untrusted candidate execution is direct-only through the
  fixed `release-candidate-network-zero` profile. Real-profile adversarial tests
  must prove protected read, socket bind/connect, `fork`, native-FFI fork,
  `posix_spawn` and parent signal all fail with `EPERM`. No candidate-side
  Python audit hook, stderr marker or candidate-owned denial receipt is PASS
  authority. A candidate may catch the returned `EPERM`; the trusted receipt
  claims containment and exact OS boundary behavior, not absence of attempted
  syscalls. A later attempt-free claim requires a separate external OS audit
  channel that candidate code cannot close or mutate.
  Candidate stdout, stderr and denial-log bytes are non-authoritative diagnostic
  artifacts and their hashes are omitted from the promotable final verifier
  receipt; pytest timing or candidate diagnostics therefore cannot break the
  repeat-twice byte-identity contract. Only trusted command identity, exit
  status, profile/boundary/resource evidence and independently calculated tree
  bindings enter that receipt.
  Before the first candidate Git plumbing call, require an isolated clone with
  a canonical `.git` directory; reject `.git` files, worktree/common-directory
  indirection, symlinks, hardlink ambiguity, special files, alternates,
  shallow/graft/replace state and escaping topology. The trusted controller
  descriptor-relatively snapshots the complete required `.git` closure into
  its invocation-owned `TMPDIR` with no-follow, identity, depth, file-count and
  total-byte bounds. It audits the copied config bytes, and every later Git
  command uses only that immutable copied `--git-dir`; candidate `.git` is never
  reopened. Every plumbing call fixes `GIT_NO_REPLACE_OBJECTS=1`, rejects
  unsupported object formats and treats `ls-tree` object IDs only as claims.
  The trusted controller bounded-reads every blob,
  independently recomputes the exact Git object hash over
  `blob <length>\0<bytes>`, requires equality with the inventory OID, and stores
  one immutable verified-byte map. Snapshot materialization consumes only that
  map; it must not call candidate Git or reopen candidate object bytes after
  verification. Before the first snapshot directory or file write, it also
  sums bytes per inventory path, not only per unique blob, and rejects a
  duplicate-blob multi-path expansion above the fixed total materialization
  limit. It reserves the trusted root marker and trusted pytest-config leaves
  before any write using the same APFS-conservative NFD-plus-casefold alias
  key, so ASCII-case, Unicode-normalization and casefold aliases cannot replace
  signed candidate bytes during materialization.
- The verifier's final receipt uses one exclusive held descriptor. It binds
  descriptor and pathname device/inode/type/`nlink` identity before and after
  each write and final `fsync`; rename/replacement is a typed blocker and a
  forged replacement path can never be returned as PASS. Every bounded input
  open uses `O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC`, validates the held descriptor,
  and rejects regular-to-FIFO replacement without blocking. Authorization and
  launch-receipt JSON use duplicate-key, depth, integer and Unicode bounds and
  convert parser resource failures to path-free typed receipts. Authorization,
  public-key and signature CLI inputs must retain their caller spelling through
  validation and are rejected when symlinked, hardlinked, non-canonical or
  replaced; resolving a symlink before the no-follow check is forbidden. JSON
  schema versions require the exact integer type and value; booleans, floats
  and strings that compare equal after language coercion are invalid. Both the
  verifier CLI nonce and authorization nonce require exactly 64 lowercase
  hexadecimal characters before signature, Git or candidate work; malformed
  values are `INVALID_NONCE`, while two valid unequal values are
  `NONCE_MISMATCH`.
- [ ] Every writable `TemporaryDirectory` created by Task -1 control code or
  tests—including `inherited_context.py`, `run-isolated.py`,
  `run-full-gate-isolated.py`, `verify-quarantine-candidate.py` and
  `test_release_control.py` as applicable—uses the validated invocation-owned
  `TMPDIR` as its explicit parent. This is not limited to test fixtures.
  Direct `/private/tmp` writes are forbidden, and missing, non-canonical,
  non-directory, invocation-root-escaping or execution-root-contained `TMPDIR`
  must be rejected before creating any probe or writable directory.
- [ ] **E — fail-closed control foundation RED/GREEN:** implement the exact
  no-command-tail CLI and `samvil.full-gate-manifest.v1` foundation contract
  above. On a real host without the Task -2 quota adapter, the only accepted
  production result is `UNSUPPORTED_INVOCATION_STORAGE_QUOTA` before execution;
  downstream PASS construction exercised with patched capability checks is
  portable contract/orchestration coverage only. Add
  table/property/adversarial cases proving candidate bytes, environment keys,
  a generic launcher tail and any CLI/manifest `profile_class` selection are
  rejected; a forged manifest, forged PASS, altered semantic counter or
  candidate-authored receipt is rejected; and control commit/file, target
  tree, gate, collected-test, import, Python/runtime, facade or tool-closure
  drift fails before the target command. Exercise all three identity variants:
  reject an original without its exact commit/tree; accept precommit tree/blob
  closure with canonical `final_commit: null` and reject any fabricated final
  commit requirement; reject a postcommit commit/parent/tree or authorization
  that does not match the precommit receipt. Require `--prior-receipt` exactly
  once in the fixed postcommit position and reject it for other target kinds.
  Missing, mismatched, forged, non-PASS, replaced or descriptor-drifted prior
  receipts, including wrong nonce/control commit/tree/authorization,
  `expected_precommit_manifest_sha256` or receipt digest, fail before
  materialization or command execution.
  Before executing staged runner bytes, have the independently pinned Task -2
  `host-tool-identity-parser.v1` process valid and adversarial Mach-O/code-
  directory fixtures at every size/depth/load-command boundary. Bind its parser
  bytes/limits/input identities/result digest in the bootstrap receipt, then
  require the staged runner parser to produce byte-identical outputs while
  remaining non-authoritative. Repeat after commit and permit runner authority
  only when the committed parser blob/digest and exact corpus comparison match.
  A Linux/mock parser test is portable protocol coverage and cannot satisfy this
  real external-parser evidence requirement.
  The one Seatbelt final argv is the exact copied Python plus digest-pinned
  trusted wrapper; the manifest separately binds that wrapper command, every
  ordered fixed probe command/digest and the candidate subcommand
  `/bin/bash scripts/pre-commit-check.sh`. Candidate children receive no authority
  path, descriptor or observation environment key. Bind the wrapper source and
  materialized content digests, mode, interpreter, PID/start identity and
  canonical bounded length-prefixed authority frames. Add adversarial child FD
  enumeration, inherited-FD write/spoof, malformed/duplicate/reordered/
  oversized/post-exit frame and candidate stdout imitation cases. Do not claim
  per-frame writer authentication from the anonymous pipe; prove exclusive
  write-endpoint delivery and zero child inheritance instead. Prove that candidate code
  directly writing former observation strings/files cannot satisfy PASS. The
  trusted wrapper redirects candidate stdout/stderr away from its held
  authority channel and directly runs the fixed runtime identity, exact
  verified-test inventory/pytest and server-import containment probes.
  Independently require a real copied Mach-O Python with exact major/minor
  `3.12` and manifest-bound patch version/architecture/slices/hashes, contained
  `sys.executable`/prefix/base-prefix/sys.path/module paths and hashes, closed
  dylib/rpath and site-package inventories, reviewed tool behavior and
  pre/post runtime/facade identity. Reject shell/trivial exit-zero runtime or
  tool stubs and emit `UNSUPPORTED_HERMETIC_RUNTIME` for an incompatible
  runtime/host combination before Seatbelt.
  Reject every copied Apple platform/SSV tool before materialization or
  execution. Permit a copied portable tool only when platform identifier is
  zero, its copied load/exec topology is closed and its bounded copied-path
  behavioral probe is green; retain the existing exact CLT Git/git-core
  topology tests and add exact copied CLT `lipo`/`otool` identity, topology and
  behavior tests. Prove `/usr/bin/git`, `/usr/bin/lipo`, `/usr/bin/otool`,
  `/usr/bin/mktemp`, `xcrun` and xcode-select shim fallback are unreachable.
  Retain the Task -2 mktemp facade but require direct `os.mkdir(0o700)`, bounded
  `EEXIST`-only retry, no reservation/unlink/check gap, and prove it executes no
  helper. Retain the copied
  Node/pnpm/npm-compatibility closure, exact PATH
  order and facade allowlist probes. The Seatbelt literal exec allowlist must
  contain every exact wrapper/facade, copied Python, copied Git/git-core,
  copied CLT lipo/otool, copied Node/pnpm/npm facade and canonical platform tool
  executable—and no directory wildcard or extra executable. For the complete
  ordered `canonical_host_tools` closure, bind each
  role/path/root ownership/mode/exact link count/size/filesystem flags/read-only
  status/device-inode/hash/Mach-O slices/load closure/Apple signing requirement/
  identifier/platform identifier/CDHash, behavior and pre/post identity. Prove
  all rows remain restricted/read-only, every actual
  exec is in the Seatbelt literal allowlist, and unknown/PATH/shim/xcrun/copied
  fallback execution fails before target PASS.
  Bind canonical `/usr/bin/codesign` as the separate manifest-pinned
  `apple_platform_identity_verifier`; prove its root/mode/link/hash/slices and
  pre/post identity are checked directly, its exact verify/display argv and
  bounded strict output parser reject path/PATH/env substitution, malformed,
  duplicate, missing or unexpected security fields, and its identity/result
  digest enters the receipt. Never treat codesign output from an unpinned tool
  as authority. Prove the codesign row reaches only
  `PLATFORM_VERIFIER_PINNED` from external-parser bytes/path/SSV evidence and
  never self-verifies; self output is diagnostic. Its first non-self exact
  verification is the behavior probe. Apply the exact two-call verify/display
  grammar and strict channel parser to every other canonical tool row, not only
  `sandbox-exec`.
  Make snapshot/wrapper/runtime/dependency/facade/tool roots read-only and give
  probes/candidate disjoint bounded scratch roots. Add chmod/rename/replace/new-
  file attempts against tracked tests, entrypoint, facade and probe bytes; each
  must be denied, and complete target/runtime identity must be revalidated after
  candidate exit before PASS. Add adversarial CPU/wall/RSS/address-space,
  FSIZE/NOFILE, descendant-count, per-file logical bytes, entry/depth,
  stdout/stderr and authority-frame count/size overflow cases. Each observable
  overflow must be concurrently drained, terminate supervision, leave no PASS
  and return the exact typed resource blocker.
  For the future supported quota adapter, add actual-host adversarial allocation
  cases for ordinary writes, raw-libc mmap-unlink-close, `F_PREALLOCATE`, file
  and directory xattrs, metadata/inode growth, sparse/clone allocation and fast
  exit. Each must remain charged to the same invocation-exclusive hard capacity;
  quota exhaustion returns `GATE_INVOCATION_STORAGE_QUOTA_EXCEEDED`. Until those
  tests run against the attested adapter, path/FD/map scans are telemetry and no
  canonical PASS is possible.
  Prove the postcommit receipt binds the accepted prior receipt digest. Prove
  the runner materializes only
  verified Git-object-pack bytes and never recursively reads the real
  repository or any linked worktree, so untracked content—including the
  literal user-owned `$CODEX_HOME/` entry—is excluded. Prove the fixed profile
  permits the IPv4 `localhost:*` TCP endpoint class required by Phase 6 and
  returns `EPERM` for TEST-NET/external TCP while DNS, UDP and Unix sockets and
  real `HOME`/`CODEX_HOME` metadata/read/write remain denied. Assert that the
  receipt contains no attempt-free, exact-port-ownership or complete detached-
  descendant-absence claim and records
  `LOOPBACK_PORT_OWNERSHIP_NOT_OS_ISOLATED` and
  `DETACHED_DESCENDANT_NOT_OS_ISOLATED`. Prove pre-existing
  receipt/denial-log/fixed-log paths, lock contention, missing/extra log,
  log-move or identity failure and temp/invocation cleanup failure all fail
  closed. Repeat the same manifest and nonce and require a byte-identical,
  path-free receipt whose semantic counters and command/content/profile/import/
  identity/tree/runtime digests are independently derived. The exact-original
  fixture and synthetic/adversarial candidate-precommit and
  candidate-postcommit fixtures must use this runner; candidate focused and
  adversarial checks must remain on
  `verify-quarantine-candidate.py` plus `run-isolated.py` under
  `release-candidate-network-zero`, with every network-zero assertion unchanged.
  Add full-gate lingering-child and `setsid`/double-fork adversarial cases.
  Every detected descendant or nominal-completion cleanup requirement must
  fail with `GATE_DESCENDANT_CLEANUP_REQUIRED`; where an identity-bound OS
  handle exists, terminate and prove absence, and otherwise fail closed with
  `DETACHED_PROCESS_SIGNAL_UNAVAILABLE` without sending a PID-only signal. The tests and receipt must preserve the
  explicit macOS polling limitation and never claim complete detached-
  descendant absence.
- [ ] **F — foundation freeze; canonical trust promotion deferred:** run staged
  spec review and staged quality review,
  then use three disjoint pre-commit command manifests because macOS rejects
  nested `sandbox-exec`. Run pure/control/inherited focused tests inside one
  `release-control-network-zero` outer sandbox with a manifest proving they do
  not invoke direct mode. Separately, with no outer Seatbelt already applied,
  have the pre-existing Task -2 external controller apply its independently
  pinned `release-candidate-network-zero` reference profile exactly once to
  every staged real-profile candidate/adversarial probe; do not execute the
  uncommitted launcher or verifier outside the outer control boundary. Run the
  staged full-gate entry in a third, separate invocation whose manifest proves
  it imports no Task -1 module, but require the current real-host outcome to be
  the deterministic pre-execution `UNSUPPORTED_INVOCATION_STORAGE_QUOTA`
  blocker. This validates fail-closed admission only; it is not a full gate and
  does not make an ephemeral wrapper trusted. Bind all three manifests, profile
  digests, staged blob identities and foundation/blocker receipts before
  creating the one Task -1 control-foundation commit. Then run the exact
  committed launcher/verifier direct integration manifest and repeat the exact
  storage blocker. Synthetic/adversarial downstream fixtures may patch the
  capability check only to validate portable orchestration and receipt
  invariants; they are not real original-tree or candidate gate evidence.
  Task -1 has no implementation candidate tree or authorization and therefore
  must not require or claim a real `candidate_precommit` or
  `candidate_postcommit` full-gate execution. The actual candidate-precommit
  gate moves to Task 4 after the candidate tree and authorization exist; the
  actual candidate-postcommit replay moves to Tasks 4-6 after the exact fuse
  commit exists. Candidate bytes may neither invoke nor choose that runner as
  PASS authority. These local portable experiments may be green as tests, but
  no canonical gate receipt or `F0_LOCAL_IMPLEMENTATION_GREEN` exists until the
  reviewed quota adapter is present. After that adapter is implemented, rerun
  this entire section on the attested boundary; any resulting PASS must retain
  `LOOPBACK_PORT_OWNERSHIP_NOT_OS_ISOLATED` and
  `DETACHED_DESCENDANT_NOT_OS_ISOLATED` and cannot satisfy
  `STAGE_A_PROMOTION_READY` until a supported-host verifier supplies a stronger
  isolated network and process namespace, VM or equivalent reviewed OS
  boundary.
  Any failure requires amending that one commit and repeating every review,
  manifest and gate from scratch.
- [ ] Because this plan scope-correction commit is a descendant of existing
  control commit `f6d50644a01c925b7910c494e2160bbac504dbd8`, amend history by
  this exact local procedure. First implement and stage the runner/tests on the
  current branch. Using invocation-owned hooks, the complete portable/control
  foundation suite and the required deterministic storage-admission blocker,
  create one `git commit --fixup=f6d50644a01c925b7910c494e2160bbac504dbd8`
  commit; `--no-verify` is forbidden. Before rewriting, bind the reviewed plan
  file's Git blob ID and content SHA-256. Then autosquash-rebase from
  `f6d50644a01c925b7910c494e2160bbac504dbd8^` so final history contains exactly
  one amended five-file control commit followed by this plan scope-correction
  commit. Do not force-push, push, fetch or mutate any remote.
- [ ] The autosquash rewrites both the control commit SHA and descendant plan
  commit SHA. After rewrite, require the plan file content and Git blob to be
  byte-identical to the pre-rewrite bindings, then repeat plan spec review,
  quality review, `git diff --check`, the portable/control foundation suite and
  the storage-admission blocker. Pin both new commit SHAs,
  the plan blob/content SHA-256 and inherited-validator/verifier/generic-
  launcher/full-gate-runner/test digests plus approved public-key identity in
  the plan execution receipt. Any byte, blob, review, digest or gate mismatch
  aborts the rewrite result and repeats the complete procedure.
- [ ] All later baseline, candidate, commit-hook and rehearsal subprocesses
  must be launched through that exact control commit and, for any canonical
  gate, through the separately reviewed Task -2 quota adapter. Drift,
  replacement or missing storage evidence is a blocker.

Expected result: no candidate tree can select, weaken, replace or falsely
report its own quarantine validation.

---

## 7. Task 0 — Freeze original evidence

**Files:**

- Create on control branch: `release/quarantine/v4322-original-receipt.json`
- Prepare historical rows for final control-branch
  `release/legacy-v4322-distributions.json`
- Create on control branch:
  `release/quarantine/v4322-historical-surface-ledger.json`
- Test: read-only Git and version assertions

- [ ] Verify the implementation worktree starts from exact commit
  `81c0c3468ed8757513fc4bf76b028736197bc556`.
- [ ] Record the commit SHA, tree SHA, `.claude-plugin/plugin.json` digest,
  `.claude-plugin/marketplace.json` digest, `.mcp.json` digest, tracked file
  mode/path/blob inventory digest, and the three synchronized version values.
- [ ] Before any repository command, create temporary `HOME`, `CODEX_HOME`,
  `CLAUDE_CONFIG_DIR`, `GNUPGHOME`, Git global config, cache and project roots.
- [ ] Prove the isolation wrapper itself RED/GREEN: a probe that attempts to
  read or write a sentinel under the real user profile must be denied, while
  exact repository/worktree and temporary fixture paths remain available.
- [ ] Before any candidate surface edit, invoke the original-tree entry only
  through the exact amended-control-commit
  `run-full-gate-isolated.py`. Without the Task -2 quota adapter, record the
  deterministic `UNSUPPORTED_INVOCATION_STORAGE_QUOTA` blocker and do not claim
  semantic counters or baseline PASS. After the adapter exists, rerun on its
  attested boundary and record the independently verified exit status, storage
  identity and semantic counters. A prior ephemeral Stage E controller or ad-
  hoc wrapper is stale, untrusted evidence and cannot satisfy this step.
- [ ] Store command names and content digests, not local absolute paths,
  usernames, environment values, or secrets.
- [ ] Record the existing version policy explicitly: plugin, MCP `__init__`,
  and README expose `4.32.2`; `mcp/pyproject.toml` remains package ABI version
  `1.0.0` and is not promoted to plugin release SSOT in F0.
- [ ] Recompute the receipt immediately before candidate commit and reject any
  drift.
- [ ] Create the historical distribution rows from pinned commit/tree,
  manifest/catalog and official artifact identities. Do not publish or sign the
  canonical final catalog at this stage because the exactly-one fuse row does
  not exist yet.
- [ ] Enumerate every retrievable official artifact from marketplace/plugin
  introduction through the switch cutoff using pinned Git objects, tags,
  release receipts and package identities. Record source identity, digest,
  platform/host class and every discoverable skill, alias, hook, setup, update,
  MCP and auto-loaded instruction path.
- [ ] Derive the policy surface union from that ledger. Never infer historical
  completeness from the current original tree alone.
- [ ] Record unavailable or unverifiable official artifacts as typed missing
  rows. They do not block local implementation experiments, but they hard-block
  `STAGE_A_PROMOTION_READY`.
- [ ] Machine-check that every known official identity at or before the cutoff
  is represented once, every row binds its snapshot/manifest and discovered-
  surface-set digest, and the aggregate surface ledger digest is ready to be
  bound by the final signed catalog.

Expected result: original baseline is independently reproducible and does not
depend on the mutable `origin/main` name after capture.

---

## 8. Task 1 — Policy and validator, RED first

**Files:**

- Create: `release/quarantine/v4322-policy.json`
- Create: `release/quarantine/v4322-passive-surface-manifest.json`
- Create: `release/quarantine/v4322-topology-guard-policy.json`
- Create: `release/quarantine/v4322-workflow-actions.lock.json`
- Create: `scripts/quarantine-fuse.py`
- Create: `scripts/check-release-topology.py`
- Create: `tools/__init__.py` if absent
- Create: `tools/release_topology_guard/__init__.py`
- Create: `tools/release_topology_guard/guard.py`
- Create: `tools/release_topology_guard/tests/__init__.py`
- Create: `tools/release_topology_guard/tests/test_guard.py`
- Create: `mcp/tests/test_quarantine_fuse.py`
- Create: `mcp/tests/test_release_topology_guard.py`
- Create: `.github/workflows/legacy-feed-monitor.yml`
- Create: `.github/workflows/release-topology-guard.yml`

- [ ] Write focused tests that fail against the untouched original tree for:
  installable marketplace row, registered plugin hooks/MCP, active updater,
  active setup/cache scripts, active root/host instructions, active historical
  skills, implicit-default workflows, and absent Stage R contract.
- [ ] Write topology RED tests that reject wrong GitHub App/check producer,
  wrong protected workflow source SHA, a PR-modified same-name workflow or
  evaluator, implicit/default refs, wrong default-main fuse, wrong stable
  base/head/synthetic tree, wrong ruleset or bypass actor, and any candidate
  field that attempts to select/configure topology authority.
- [ ] Run only the focused tests and verify each failure names the forbidden
  active surface rather than failing from import, fixture, or syntax errors.
- [ ] Add a strict policy schema with explicit original identity, surface
  classes, passive content template, required file modes, forbidden tokens,
  allowed read-only commands, and maximum output size.
- [ ] Require the verifier caller to supply the external candidate-tree
  authorization path, expected trusted-control commit and detached-signature
  policy. Candidate bytes must not self-authorize their quarantine identity.
- [ ] Quarantine-mode selection must compare candidate tree, policy, manifest,
  passive-surface and gate-script digests against that external authorization.
  Missing, unsigned-when-required, candidate-local, wrong-control-commit or
  mismatched authorization must fail before any normal gate is skipped.
- [ ] Implement verification only. Do not implement rendering until validator
  tests are RED for the correct reason.
- [ ] Reject symlinks, hardlink ambiguity, device files, unclassified
  executable files, path traversal, duplicate normalized paths, non-UTF-8
  auto-loaded documents, and unexpected executable bits.
- [ ] Verify policy paths using Git index/tree identity, not filesystem display
  names or caller-provided labels.
- [ ] Implement `verify_release_freeze()`, `verify_check_run_identity()`, and
  `scan_implicit_default_refs()` only in
  `tools.release_topology_guard.guard`. The CLI and workflow import that exact
  module; neither duplicates policy. The workflow has no default-main
  push/schedule/manual trigger, no secret/write permission, uses only the
  exact full-SHA action lock, checks out/executes protected-base bytes, and
  accepts only an explicit pull request whose base is `release/v4-stable`.

Focused command:

```bash
<PINNED_PYTHON> \
  <PINNED_CONTROL>/tools/release-control/run-isolated.py \
  --root <ABS_CANDIDATE_TREE> \
  --nonce <HEX64> \
  --timeout <POSITIVE_SECONDS> \
  --receipt <ABS_TMPDIR>/task1-focused-receipt.json \
  --denial-log <ABS_TMPDIR>/task1-focused-denial.log \
  -- <PINNED_PYTHON> -I -m pytest \
  -p no:cacheprovider --noconftest -c <TRUSTED_PYTEST_CONFIG> \
  --rootdir=. --import-mode=importlib \
  mcp/tests/test_quarantine_fuse.py \
  mcp/tests/test_release_topology_guard.py \
  tools/release_topology_guard/tests/test_guard.py -q
```

Every placeholder above resolves before launch to an absolute, canonical,
digest-pinned trusted path. `<TRUSTED_PYTEST_CONFIG>` is an exclusive regular
file created inside the invocation-owned snapshot from fixed verifier-owned
bytes, fsynced and identity-checked before launch; it is not part of candidate
inventory or candidate semantic digests. This is normal direct mode: the exact committed
launcher applies `release-candidate-network-zero` once and no outer Seatbelt is
already active. The receipt and denial log are absent, pairwise-distinct
children of the invocation-owned validated `<ABS_TMPDIR>` and are also distinct
from the direct temp probe and both protected write paths.

Expected RED: the original tree is correctly diagnosed as active and not a
quarantine fuse.

The authorization's direct candidate command manifest is fixed before Task 1
implementation and contains exactly these argv tails after the absolute pinned
Python executable:

```text
quarantine-tests: -I -m pytest -p no:cacheprovider --noconftest -c __SAMVIL_TRUSTED_PYTEST_CONFIG__ --rootdir=. --import-mode=importlib mcp/tests/test_quarantine_fuse.py mcp/tests/test_release_topology_guard.py tools/release_topology_guard/tests/test_guard.py -q
quarantine-gate: -I scripts/quarantine-fuse.py verify --policy release/quarantine/v4322-policy.json
```

`verify` binds its read-only root to the launcher's canonical current working
directory, performs no subprocess or temporary write, and is distinct from the
renderer subcommand whose output root must be explicit. The subprocess-heavy
`/bin/bash scripts/pre-commit-check.sh` is not a direct candidate command; after
Task -2 storage admission, both the original-tree and candidate-tree canonical
full gates belong only to the separately pinned full-gate manifest consumed by
the exact committed `run-full-gate-isolated.py`. The current
`samvil.full-gate-manifest.v1` foundation instead stops with
`UNSUPPORTED_INVOCATION_STORAGE_QUOTA`. Candidate focused/adversarial commands remain on
`verify-quarantine-candidate.py` plus `run-isolated.py` under
`release-candidate-network-zero`. Candidate bytes cannot invoke, configure,
select or replace the full-gate runner as PASS authority.
The sentinel above is authorization data, never a filesystem path supplied by
the candidate. The pinned verifier requires it exactly once and substitutes
only the descriptor-validated trusted config path immediately before launch.

The external authorization also binds these exact semantic roles to candidate
inventory paths and SHA-256 values: `policy`, `plugin_manifest`,
`marketplace_manifest`, `mcp_manifest`, `passive_surface_manifest`, `gate`,
`validator`, `focused_test`, `topology_policy`, `workflow_action_lock`,
`tools_package_marker`, `topology_package_marker`, `topology_wrapper`,
`topology_evaluator`, `topology_test_package_marker`, `topology_unit_test`,
`topology_integration_test`, `topology_workflow`, and `legacy_monitor`. Their
paths are respectively:
`release/quarantine/v4322-policy.json`, `.claude-plugin/plugin.json`,
`.claude-plugin/marketplace.json`, `.mcp.json`,
`release/quarantine/v4322-passive-surface-manifest.json`,
`scripts/pre-commit-check.sh`, `scripts/quarantine-fuse.py`,
`mcp/tests/test_quarantine_fuse.py`,
`release/quarantine/v4322-topology-guard-policy.json`,
`release/quarantine/v4322-workflow-actions.lock.json`,
`tools/__init__.py`,
`tools/release_topology_guard/__init__.py`,
`scripts/check-release-topology.py`,
`tools/release_topology_guard/guard.py`,
`tools/release_topology_guard/tests/__init__.py`,
`tools/release_topology_guard/tests/test_guard.py`,
`mcp/tests/test_release_topology_guard.py`,
`.github/workflows/release-topology-guard.yml`, and
`.github/workflows/legacy-feed-monitor.yml`. Whole-tree identity cannot
substitute for an omitted or misbound semantic role.

---

## 9. Task 2 — Deterministic passive overlay

**Files:**

- Modify the runtime/discovery surfaces listed in section 3.
- Modify: `scripts/pre-commit-check.sh`

- [ ] Implement renderer refusal rules first: output root must be explicit,
  empty or exact expected candidate worktree, inside the isolated worktree
  boundary, and outside all supplied `HOME`, `CODEX_HOME`, Claude config,
  project fixture, repository common-dir, and original checkout paths.
- [ ] Renderer must never operate on `.` by default and must support
  `--check` with mutation zero.
- [ ] Render every policy-classified surface from canonical templates.
- [ ] For every historical artifact or proven identical semantic class, build
  a residue fixture, apply the fuse with the old updater's real no-delete copy
  semantics, and verify every current or historical discoverable path resolves
  to passive content. Missing overlay, mixed active/passive bytes or an unknown
  residue path is a blocker.
- [ ] Make `skills/samvil-update/SKILL.md` and its legacy body passive at their
  historical paths; the current default-branch Contents API, clone, in-place
  rsync, rename, sibling deletion, and manual rsync fallback must all disappear
  from executable/user-followable candidate content.
- [ ] Make `scripts/sync-cache.sh` and `.githooks/post-commit` passive without
  selecting either the current unversioned cache-root topology or the updater's
  version-child topology.
- [ ] Preserve file modes deterministically and remove active symlinks.
- [ ] Keep `4.32.2` synchronized in plugin/package/README-visible quarantine
  metadata without claiming the candidate is the original tree.
- [ ] Every passive skill/command/script prints one stable machine-readable
  receipt and one Korean explanation containing only:
  `DEFERRED_TO_V433`, current quarantine identity, and
  `https://github.com/insamkwon/samvil/releases/tag/v4.33.0`.
- [ ] Passive execution may read its own immutable file/manifest identity but
  must not use network, temporary files, package managers, Git fetch/clone,
  profile/cache/settings access, project writes, process signaling, or child
  background execution.
- [ ] Quarantine-mode pre-commit must fail if the original baseline receipt is
  missing/mismatched or if any normal production check is merely relabeled as
  executed.
- [ ] Re-run focused tests and obtain GREEN.
- [ ] Keep publisher/remote mutation files unreachable from passive root
  instructions and workflows, but do not refactor them in F0. The sole
  exception is the newly added read-only protected topology guard defined by
  Task 1; it has no mutation authority and is dormant on default main. Focused
  tests must prove the rehearsal and topology paths never invoke the existing
  publisher.

---

## 10. Task 3 — Dynamic no-write proof

**Files:**

- Extend: `mcp/tests/test_quarantine_fuse.py`

- [ ] Create isolated temporary HOME/CODEX_HOME/Claude config/project/cache
  roots with sentinel files and full before digests.
- [ ] Every subprocess, including pytest, pre-commit, Git plumbing, shell
  probes and commit hooks, runs with an allowlisted environment created from
  `env -i`: explicit safe `PATH`, temporary `HOME`, `CODEX_HOME`,
  `CLAUDE_CONFIG_DIR`, `GNUPGHOME`, `TMPDIR`, `XDG_*`,
  `GIT_CONFIG_NOSYSTEM=1`, isolated `GIT_CONFIG_GLOBAL`, disabled credential
  helpers/askpass, disabled Git network protocols and fixed
  `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`. Pytest commands also disable the cache
  provider so a read-only candidate root never attempts `.pytest_cache` writes.
- [ ] Run all subprocesses under `/usr/bin/sandbox-exec` with a generated
  profile that permits only the exact isolated worktree/clone, system runtime
  libraries and temporary fixture roots, and denies reads/writes to every
  other user-home path. First prove the deny rule using read and write probes;
  unavailable or ineffective sandboxing is a blocker.
- [ ] Enforce network zero with the sandbox network deny rule, disabled Git
  protocols and child-process supervision. Proxy variables alone are not
  accepted as network isolation evidence.
- [ ] Audit sandbox denial logs and command manifests. A real-profile access
  attempt is a failure even when the target's before/after digest is unchanged.
- [ ] Invoke every passive executable and render every passive skill/host
  instruction through the supported fixture adapters.
- [ ] Exercise the existing updater and sync-cache test modules in quarantine
  mode so shell behavior is automated rather than delegated to interactive
  real-install testing.
- [ ] Run with missing `gh`, missing `uv`, missing Python package environment,
  no TTY, network-deny proxy variables, read-only protected roots, spaces and
  Unicode in paths, and display label different from canonical path.
- [ ] Verify protected directory entry list, bytes, mode, xattrs where
  available, symlink targets, settings, selection, cache, project state, Git
  refs, and process list have mutation cardinality zero.
- [ ] Repeat every invocation twice with distinct signed run envelopes,
  nonces, run IDs, and observer identities. Require equality only for the
  policy-defined normalized deterministic projection; separately require
  byte-identical whole receipts for same-nonce response-loss replay.
- [ ] Inject SIGTERM and timeout around passive commands and require no partial
  artifact or background child.
- [ ] Scan passive text and scripts for destructive/update commands and shell
  expansion forms; allow terms only inside clearly non-executable policy/test
  fixtures.

Expected GREEN: all passive entry points are idempotent no-write operations.

---

## 11. Task 4 — Stage A and Stage R contract

**Files:**

- Create: `scripts/rehearse-quarantine-refs.py`
- Extend: `mcp/tests/test_quarantine_fuse.py`

- [ ] Write RED tests for wrong expected-old SHA, wrong ref, multi-ref update,
  non-fast-forward Stage A, Stage R parent mismatch, Stage R tree mismatch,
  dirty index, unsigned/unapproved metadata, and response-loss retry.
- [ ] After quarantine tests are green, compute the exact candidate tree with
  `git write-tree` and issue the separate external
  `v4322-candidate-authorization` sidecar for that tree and its
  policy/manifest/passive/gate digests. Never place this authorization in the
  canonical distribution catalog.
- [ ] Before creating a commit object, run spec-compliance review and code-
  quality review against the externally authorized staged tree. Findings must
  be fixed in the worktree, followed by a new tree SHA, new authorization and
  both reviews again.
- [ ] Only after Task -2 provides a valid invocation-exclusive kernel-quota
  storage attestation, run the externally authorized quarantine pre-commit
  canonical full gate through a
  `candidate_precommit` manifest whose final commit field is canonically
  `null`, then create the sole fuse implementation commit. Fixed parent, tree,
  message, author and committer inputs must be recorded so the exact commit
  object is reviewable. Without that evidence, require
  `UNSUPPORTED_INVOCATION_STORAGE_QUOTA`, leave mutation and commit count at 0,
  and stop as `BLOCKED_ENVIRONMENT`.
- [ ] Immediately replay the quota-backed canonical full gate through a
  `candidate_postcommit` manifest that binds the exact final commit and expected
  parent and proves its tree and authorization digest equal the accepted
  precommit receipt, supplied
  through the required fixed-position `--prior-receipt` option. A green
  precommit tree without this exact post-commit replay is incomplete evidence.
- [ ] Only after the exact fuse commit exists, create Stage R with Git plumbing
  so its parent is that exact fuse commit and its tree is the exact original
  tree. Do not update a ref while creating either commit object.
- [ ] Keep the Stage R state/receipt schema local to the release rehearsal;
  never route it through SAMVIL build-stage enums, chain markers, or project
  state.
- [ ] Finalize the external `quarantine_fuse` catalog row with exact
  commit/tree/manifest/passive/policy identities. The final canonical catalog
  must contain non-empty complete historical snapshot/manifest rows, exactly
  one `quarantine_fuse` cutoff exception, and the exact historical-surface-
  ledger digest. Extra authorization rows, missing official identities,
  duplicate fuse rows, cutoff drift or unbound ledger data fail the machine
  gate. Verify its detached release signature before treating the object as
  public-promotion eligible.
- [ ] Sign Stage R with the same approved release authority and verify the
  signature from an isolated trust store. If signing authority is unavailable,
  create an explicitly unsigned local rehearsal object only, mark the release
  status `BLOCKED_RELEASE_AUTHORIZATION`, and do not confuse its SHA with the
  future signed Stage R SHA.
- [ ] Verify Stage R tree/catalog/file-mode inventory is byte-identical to the
  immutable original commit.
- [ ] Stage A accepts only `refs/heads/main: original → exact fuse` as one
  expected-old fast-forward transaction.
- [ ] Stage R accepts only `refs/heads/main: exact fuse → exact restoration`
  as one expected-old fast-forward transaction.
- [ ] Exact retry after acknowledged or response-lost success returns the same
  ref/commit receipt without creating another commit or event.
- [ ] Any other local branch or tag before/after digest must remain unchanged.
- [ ] The rehearsal tool accepts only a freshly created bare repository below
  the current invocation's exact temporary root, containing a random marker
  nonce written by that invocation, with no configured remotes. Merely being a
  local repository is insufficient.
- [ ] Reject the source repository common-dir, original checkout, every linked
  worktree, repositories outside the exact temp root, missing/wrong nonce,
  non-bare repositories and any URL-like input before object/ref/event writes.
- [ ] Negative tests pass the real local repository and implementation
  worktree paths and prove ref/object/event mutation zero.
- [ ] Run with Git network protocols disabled and sandbox network deny active.

Expected GREEN: Stage A and R are single-ref, expected-old, replay-safe local
transactions.

---

## 12. Task 5 — Disposable mirror rehearsal

- [ ] Create a new temporary bare repository from the immutable original
  object database without configuring a network remote. Write a per-invocation
  random marker nonce and bind its canonical temp-root path into the rehearsal
  process before allowing any Git object or ref mutation.
- [ ] Pin `legacy/v4.32.2-original` to the original commit.
- [ ] Materialize the exact candidate fuse commit and pre-create Stage R.
- [ ] Snapshot every ref and object identity.
- [ ] Run all negative fixtures before the successful path and confirm no ref
  changes.
- [ ] Run successful Stage A and verify only `refs/heads/main` moves.
- [ ] Simulate response loss and exact retry; verify identical receipt and no
  additional ref/event.
- [ ] Run successful Stage R and verify only `refs/heads/main` moves again.
- [ ] Clone no-ref and explicit-main worktrees after each phase and verify the
  expected original/fuse/restored trees.
- [ ] Run the passive command no-write fixture against the fuse checkout.
- [ ] Delete the temporary mirror after preserving a path-free JSON receipt.

This rehearsal proves Git transaction mechanics and candidate semantics. It
does not claim GitHub ruleset, CDN propagation, historical Claude package, or
actual public updater coverage.

Passing this rehearsal proves only its Git transaction and candidate-semantic
scope. It contributes to `F0_LOCAL_IMPLEMENTATION_GREEN` only when the exact
candidate receipts were produced by the attested quota-backed canonical gate.
Before then it is supporting evidence, the terminal remains
`BLOCKED_ENVIRONMENT`, and actual Codex/Claude/OpenCode/Gemini first-open,
existing global MCP, selection/cache, stale process/catalog and official
historical-host execution remain mandatory inputs to the separate
`STAGE_A_PROMOTION_READY` decision.

---

## 13. Task 6 — Gates, commit, and reviews

- [ ] Focused quarantine tests GREEN.
- [ ] On a Task -2-attested invocation-exclusive kernel-quota filesystem,
  quarantine-mode `/bin/bash scripts/pre-commit-check.sh` GREEN for both the
  authorized `candidate_precommit` tree and exact `candidate_postcommit`
  commit replay. Without it, the expected gate result is
  `UNSUPPORTED_INVOCATION_STORAGE_QUOTA`, not GREEN.
- [ ] Original, candidate-precommit and candidate-postcommit gate commands were
  executed only through the verified isolation runner and bound the same
  `storage_boundary_class` and `storage_boundary_sha256`; bare invocation is
  forbidden. Portable/test-double executions are reported separately as
  contract/orchestration checks.
- [ ] Before commit, `git diff --cached --check` is GREEN and staged files
  exactly equal the policy-derived F0 file set.
- [ ] Before commit, staged-tree spec-compliance and code-quality reviews are
  CLEAN for the exact externally authorized tree SHA.
- [ ] Commit message is one friendly Korean line explaining the actual work.
- [ ] After commit, verify `parent == original`,
  `git rev-list --count original..implementation == 1`, committed tree equals
  the reviewed/authorized tree, `git diff-tree --check original implementation`
  is GREEN, and committed file set equals the policy-derived F0 file set.
- [ ] Recovery review independently reconstructs original → fuse → Stage R
  using only pinned receipts and reports exact hashes.
- [ ] Final whole-object review checks exact commit, external catalog/signature,
  Stage R and mirror receipts. Any P1/P2 finding marks the exact bad fuse,
  catalog authorization and Stage R as `REJECTED` in the append-only control
  ledger and invalidates every receipt/signature for promotion.
- [ ] A rejected object is never amended or reused. Render a fresh replacement
  tree from the immutable original, issue a fresh authorization, create a fresh
  sole-parent commit object, and compare-and-swap the unpushed local feature ref
  from rejected SHA to replacement SHA. Then regenerate catalog, Stage R,
  signatures, rehearsal and all reviews. The final branch must still satisfy
  parent==original and exactly one reachable implementation commit.

Do not push after the commit. Stop and report:

- implementation commit SHA and tree SHA;
- signed Stage R commit SHA and tree equality proof, or an explicit unsigned
  rehearsal SHA plus `BLOCKED_RELEASE_AUTHORIZATION`;
- original and quarantine gate receipts;
- quota storage-boundary class/digest/capacity evidence, or the exact
  `UNSUPPORTED_INVOCATION_STORAGE_QUOTA` blocker;
- mirror rehearsal receipt;
- exact remaining untested public/historical surfaces;
- exact terminal status: currently `BLOCKED_ENVIRONMENT`; only after the
  quota-backed canonical gates exist may it become
  `F0_LOCAL_IMPLEMENTATION_GREEN`, `BLOCKED_RELEASE_AUTHORIZATION`, or another
  typed blocker; never
  `STAGE_A_PROMOTION_READY` without the actual-host and complete-ledger gate;
- proposed GitHub ref/ruleset mutations for a separate approval.

---

## 14. Hard stop conditions

### 14.1 Implementation commit blockers

Stop without creating the implementation commit if any of the following occurs
before commit:

- original identity/version/tree drift;
- any fixture touches a real user profile/cache/config/project path;
- a focused test never demonstrates a meaningful RED state;
- candidate contains an unclassified auto-loaded or executable path;
- passive invocation changes any protected state;
- normal production checks are hidden or reported as run in quarantine mode;
- Task -2 cannot provide fresh invocation-exclusive kernel-quota storage
  evidence, or its class/capacity/filesystem/mount/adapter identity drifts;
- a repeated same-root failure occurs twice;
- implementation attempts public GitHub mutation or credentials;

If a candidate defect is found only after the exact implementation commit—for
example Stage A/R changes more than one ref, Stage R tree differs from original,
or final review finds a P1/P2—the commit/catalog/Stage R are marked `REJECTED`
and the fresh replacement cycle in Task 6 is mandatory. The rejected object is
not promotion eligible.

### 14.2 Runtime-admission blocker

`INVOCATION_STORAGE_QUOTA_NOT_OS_ENFORCED` is not promotion-only. It means the
runner cannot prove an aggregate storage bound against preallocation, xattrs,
metadata, sparse/clone allocation or mmap-unlink-close allocation. It must
produce `UNSUPPORTED_INVOCATION_STORAGE_QUOTA`, verdict `BLOCKED`, exit 2 and
terminal `BLOCKED_ENVIRONMENT` before candidate/materialization work. Logical
byte scans, FD/map inventory and `RLIMIT_FSIZE × RLIMIT_NOFILE` cannot weaken
this blocker, and it must not appear in a PASS receipt's
`promotion_limitations`.

### 14.3 Promotion-only blockers

After quota-backed canonical original/candidate gates have passed, the
following conditions allow a verified local implementation commit and an honest
`F0_LOCAL_IMPLEMENTATION_GREEN`, but prohibit
`STAGE_A_PROMOTION_READY` and every public mutation:

- historical official-artifact ledger is incomplete or has an unverifiable
  official identity;
- approved catalog/Stage R signing authority is unavailable;
- required historical or actual host artifacts are unavailable;
- actual supported-host cold/stale-disk/stale-process/no-ref/custom-main matrix
  is incomplete or has a blocking result;
- GitHub ruleset, App identity, public propagation or release-control evidence
  required by the parent design is missing.
- `LOOPBACK_PORT_OWNERSHIP_NOT_OS_ISOLATED`: the macOS Seatbelt full-gate
  profile permits the fixed IPv4 `localhost:*` TCP endpoint class but cannot
  prove exact ephemeral-port ownership. Local original, candidate-precommit
  and candidate-postcommit full-gate experiments may remain green only on a
  future supported-host boundary that independently provides both the admitted
  kernel-quota filesystem and atomic identity-bound descendant signaling. The
  current macOS foundation cannot reach this promotion-only limitation because
  it is blocked before execution, but
  promotion stays blocked until a supported-host verifier supplies a stronger
  isolated network namespace, VM or equivalent reviewed OS boundary.
- `DETACHED_DESCENDANT_NOT_OS_ISOLATED`: the trusted wrapper detects and fails
  every descendant identity it observes. Linux may clean through identity-bound
  `pidfd`; macOS deliberately refuses PID-only detached signaling, because
  `proc_bsdinfo` recheck followed by `kill(pid)` would retain a PID-reuse TOCTOU.
  Consequently this foundation blocks macOS before execution with
  `DETACHED_PROCESS_SIGNAL_UNAVAILABLE`; it does not report a green local full
  gate. On a host with atomic identity-bound signaling, disposable local Stage
  A transaction rehearsal may remain green, but public Stage A mutation and
  `STAGE_A_PROMOTION_READY` stay blocked until a supported-host verifier
  supplies a reviewed process namespace, VM or equivalent OS boundary.

Both typed limitations must be removed by, or explicitly replaced with,
reviewed stronger OS-boundary evidence before promotion-ready can be true.

These conditions must produce a typed promotion blocker. They must not be used
to fabricate signed evidence, claim Stage A readiness, or weaken local tests.

Both categories are blockers at their stated boundary, not reasons to weaken
an assertion or expand the F0 scope.
