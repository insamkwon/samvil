# SAMVIL v4.32.2 Quarantine Fuse F0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use
> `superpowers:subagent-driven-development` or `superpowers:executing-plans`.
> Production behavior must follow test-first RED → GREEN. Do not push, open a
> PR, update a remote ref, or touch a user-owned `HOME`/`CODEX_HOME` while
> executing this plan.

**Goal:** Build and prove the exact v4.32.2-version passive quarantine fuse and
its pre-reviewed Stage R semantic restoration commit without changing the
public repository.

**Architecture:** Keep the current v4.32.2 tree as immutable input, render a
same-version passive overlay for every auto-loaded or historically
user-invokable surface, verify that overlay with a quarantine-specific gate,
and rehearse expected-old Stage A plus fuse-parent/original-tree Stage R in a
disposable local bare mirror. The fuse does not install v4.33 and is not the
v4.32.3 bridge.

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
- Design evidence branch:
  `codex/v433-safe-upgrade-design`
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

F0 has two distinct terminal states:

- `F0_LOCAL_IMPLEMENTATION_GREEN`: trusted control verifier, exact fuse commit,
  local Stage R object, no-write fixtures and disposable mirror are green.
- `STAGE_A_PROMOTION_READY`: additionally requires approved signatures,
  complete historical official-artifact ledger, actual supported-host
  cold/stale-disk/stale-process/no-ref/custom-main results and every design
  promotion receipt. F0 local success alone can never emit this verdict.

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

Therefore F0 has two independent full gates rather than pretending the normal
production wiring suite remains meaningful after production wiring is
intentionally removed:

1. **Original-tree baseline gate:** an isolated exact-original clone runs the
   unmodified `bash scripts/pre-commit-check.sh` and complete existing pytest
   suite through the mandatory isolation wrapper described below.
2. **Fuse-tree quarantine gate:** an isolated exact-candidate clone runs the
   same entry command through that wrapper. Quarantine mode is accepted only
   when an external candidate-tree authorization from the trusted control
   branch matches the candidate tree/policy/manifest/gate digests; candidate
   files cannot select the mode by themselves. The gate then runs
   the complete quarantine contract suite: exact tree identity, passive
   surface inventory, no-write dynamic execution, no installable catalog,
   empty MCP/hook registration, workflow containment, Stage A single-ref
   semantics, and Stage R byte-identical restoration.

The outer trusted verifier is the only authority that may issue PASS. Candidate
pre-commit/tests must print the original baseline receipt identity and the
quarantine receipt, but their output is auxiliary untrusted data. A forged
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
| `tools/release-control/verify-quarantine-candidate.py` | Create and pin on design control branch before candidate work | Independently verify authorization signature, control commit, candidate tree and every policy/manifest/passive/gate digest |
| `tools/release-control/tests/test_release_control.py` | Create on design control branch | RED/GREEN tests for candidate bypass, forged GREEN output, sandbox escape, real-repository target and signature/digest failures |

The canonical catalog schema fixes its cutoff, known-official completeness
rules, historical snapshot/manifest rows and exactly-one fuse invariant. Each
historical row binds its discovered-surface-set digest, and the signed catalog
binds the complete historical-surface-ledger digest. Candidate authorization
is a separate sidecar and can never satisfy a distribution-row schema.

The trusted inherited-validator/verifier/launcher commit SHA, file digests and
approved public-key identity are pinned before any candidate edit.
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
| `scripts/quarantine-fuse.py` | Create | Deterministically render or verify a candidate tree; render requires an explicit output root and refuses repository/profile roots |
| `scripts/rehearse-quarantine-refs.py` | Create | Create-only local Stage R commit and disposable-mirror Stage A/R rehearsal; never contacts a remote |
| `mcp/tests/test_quarantine_fuse.py` | Create | Policy, renderer, passive content, no-write, collision and Stage R contract tests |
| `mcp/tests/test_update_smoke.py` | Modify | In quarantine mode replace the documented interactive-only updater gap with passive/no-subprocess assertions |
| `mcp/tests/test_sync_cache_smoke.py` | Modify | Prove quarantine sync and post-commit paths are no-write and do not infer either conflicting cache topology |
| `mcp/tests/test_ci_workflow.py` | Modify | Prove default-main workflows are contained and only the approved monitor remains active |
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
| `.github/workflows/*` | no implicit development/release workflow on default `main`; only reviewed read-only legacy-feed monitor remains active |

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
commit:

- the original-tree baseline receipt is fixed;
- all focused tests have demonstrated the expected RED failure at least once;
- the candidate quarantine gate is green;
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

Task -1 cannot trust code that Task -1 is itself creating. Its first RED/GREEN,
full-gate, review and commit operations therefore run through a minimal
bootstrap boundary fixed by this already-reviewed plan commit.

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
- `verify-quarantine-candidate.py` remains the final outer verdict authority.
  It calculates trust evidence independently and never trusts candidate output.

This extra private module is a scope correction, not product expansion. It
introduces no public behavior or runtime API, candidate authority, loopback
permission, remote/user-profile access, or additional commit. All four Task -1
files remain one control-plane commit. The launcher mode, never candidate CLI,
environment or receipt bytes, selects one of two network-zero classes:
`release-control-network-zero` for the trusted inherited control process and
`release-candidate-network-zero` for a direct untrusted candidate process. The
existing `pinned-full-gate-loopback-only` class remains full-gate-only.

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
  fixed resource manifest covering CPU time, regular-file size and open
  descriptors. On macOS the TCB must first behaviorally probe whether a
  meaningful hard address-space limit is enforceable: `RLIMIT_AS` aliases the
  shared-region/RSS limit on supported hosts and may be impossible to lower
  below the runtime's large mapped region. If so, the external controller uses
  a fixed low RSS watchdog through the read-only kernel process API and records
  that measured policy instead of claiming a nonexistent hard limit. Direct
  mode also watches total non-followed bytes below its invocation root so many
  individually bounded files cannot exhaust the host disk. `RLIMIT_FSIZE`
  multiplied by usable `RLIMIT_NOFILE` must itself fit the aggregate disk
  budget, bounding unlinked-but-open files that a directory scan cannot see.
  Stdout/stderr are
  controller-owned bounded captures and are never loaded with an unbounded
  `.read()`. Limit signals, watchdog termination and bounded-capture overflow
  produce a path-free `RESOURCE_LIMIT_EXCEEDED` blocker with the exact fixed
  limit manifest; candidate output cannot downgrade it to PASS. All quota
  checks run once more after child exit, so a fast exit cannot bypass them.
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

The first plan-only full gate proved that the prior bootstrap executable
closure was incomplete. Completing that closure is part of the Task -2 trusted
computing base; it does not expand production behavior, product scope, or the
sandbox's authority.

- Before creating the facade, use `git grep` against tracked gate-reachable
  files to enumerate every supported `mktemp` argument shape. At this plan
  correction, the complete tracked allowlist is
  `scripts/dogfood-smoke.sh:60`:
  `mktemp -d -t samvil-dogfood-smoke-XXXXXX`.
- Create a bootstrap-owned, digest-pinned `tools/facade/bin/mktemp` facade. It
  accepts only the enumerated shape, rewrites it to an explicit template below
  the invocation-owned `TMPDIR`, and then invokes the pinned `/usr/bin/mktemp`.
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
- The tracked archive has no `.git`, but the full gate exercises
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
3. `pinned-full-gate-loopback-only` is used only for the exact staged snapshot
   entry command `bash scripts/pre-commit-check.sh` and the pinned original
   `mcp/tests` collection it invokes. It retains `(deny network*)` and adds
   only `(allow network-inbound (local tcp "localhost:*"))` plus
   `(allow network-outbound (remote tcp "localhost:*"))`. Broad rules such as
   `(allow network*)`, `(allow network* (local ip))`, wildcard remote IPs,
   UDP, Unix sockets, DNS/mDNS sockets and external TCP remain forbidden.

The loopback-only profile is not a candidate-selectable mode. The trusted
bootstrap must fail closed unless all of the following are true before
Seatbelt invocation:

- the requested profile class is derived by the trusted controller from a
  fixed command manifest, not from an environment variable, CLI flag,
  candidate receipt or candidate-controlled configuration;
- the executable entrypoint, `scripts/pre-commit-check.sh`, Phase 6 script,
  Phase 6 test and complete collected `mcp/tests` path/blob/mode inventory
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
- `pinned-full-gate-loopback-only` must successfully bind an ephemeral
  `127.0.0.1` TCP port and connect only to that invocation-owned listener;
- the loopback-only profile must reject a TCP connect to the TEST-NET address
  `192.0.2.1` with `EPERM` and must not resolve a hostname to perform the
  probe;
- all three profiles must retain the required real-profile read/write denials,
  invocation-root write authority, executable closure and sanitized
  environment keys.

Any command-manifest drift, newly collected test, unexpected import, external
connect result other than `EPERM`, or attempt by Task -1/candidate bytes to
select the loopback profile is a bootstrap blocker. Loopback permission is
test infrastructure authority for the pinned baseline only; it is never part
of the committed release-control launcher or quarantine candidate contract.

The bootstrap trusted computing base is a digest-pinned executable/runtime
closure, not the current repository venv. It includes absolute system tools
used by the normal gate (`sandbox-exec`, `env`, `git`, `bash`, `sh`, `mktemp`,
`mkdir`, `chmod`, `grep`, `xargs`, `sed`, `tail`, `head`, `find`, `cat` and
their required system libraries), plus a copied Codex-owned Python 3.12 runtime
and copied dependency bytes. Paths, file identities, Mach-O/library closure and
SHA-256 digests are recorded before use. No candidate or newly created Task -1
Python module is imported by the bootstrap.

The repository's ignored `mcp/.venv/bin/python` is never executed: its
interpreter resolves outside the repository and its editable `.pth` points at a
mutable worktree. Instead, copy the Codex workspace Python runtime and required
site-package bytes into the invocation temp root, reject escaping symlinks,
hardlinks, `.pth`, `sitecustomize`, `usercustomize` and external
`direct_url.json`, then import `samvil_mcp` only from the exact archived Git
snapshot. The outer probe requires `sys.executable`, every `sys.path` entry and
every imported module path to stay within the hermetic runtime or exact temp
snapshot, with user-site disabled.

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
  worktree, allow read/write only
  for the exact Task -1 temporary root and explicitly reviewed control files.
  The network-zero class includes no network allow rule; the pinned full-gate
  class includes only the two exact loopback TCP rules above.
- [ ] Copy the pinned Python/runtime/dependency and shell-tool closure into the
  invocation temp root before sandboxed execution. Verify there are no external
  symlink, editable-install, dynamic-library or import-path dependencies. An
  incomplete closure is a bootstrap blocker, not permission to read the live
  venv or user runtime during gates.
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
  reference inside the outer control test. Run the exact staged full gate
  inside a third
  `pinned-full-gate-loopback-only` outer sandbox invocation only after the
  trusted command/test/import manifests are verified. That full-gate manifest
  must prove no Task -1 module is imported or executed. No path may nest or
  switch Seatbelt profiles.
- [ ] Before trust promotion, compare the direct candidate and inherited
  control evidence. Require distinct exact profile classes and class-specific
  trusted source-template/normalized-policy digests; require their shared
  real-home/network denials, allowed exact-root/temp decisions and environment
  key set to agree; and require only the direct candidate class to prove OS
  `process-fork`/spawn/signal denial. Retain each invocation's raw expanded
  `profile_sha256` only as its own exact-byte receipt evidence; do not require
  cross-invocation equality. After the one control commit is created, run the
  exact committed launcher/verifier direct integration manifest outside any
  existing Seatbelt so that it applies the candidate profile exactly once. Any
  weaker or divergent result requires an amend and a complete review/gate
  replay.
- [ ] Do not broaden permissions to the real `HOME`/`CODEX_HOME`, writes below
  `/private/var/folders`, external network in either mode, or loopback
  bind/connect and packet/endpoint authority in release-control network-zero
  mode. Unbound socket object creation alone is not authority and may succeed.
- [ ] Run the exact staged snapshot's normal
  `bash scripts/pre-commit-check.sh` with the copied Codex bundled Python 3.12,
  digest-pinned local package artifact allowlist, `env -i`, invocation-owned
  `HOME`/`CODEX_HOME`/`GNUPGHOME`/`TMPDIR`/`XDG_*`, the one outer sandbox,
  real-profile denials, loopback-only/external-denial probes, trusted
  command/test/import manifests and the fixed-log lock/absence protocol. Never
  use the live `mcp/.venv` or external network.
- [ ] Commit safety is part of Task -2. Because repository
  `.githooks/post-commit` invokes `scripts/sync-cache.sh`, commit with
  `git -c core.hooksPath=<invocation-owned-hooks> commit`. Install only an
  invocation-owned pre-commit hook that re-runs and verifies the exact
  hermetic full gate; install no post-commit hook. `--no-verify` is forbidden.

No untrusted working-tree helper may wrap, replace, parameterize or interpret
the outer bootstrap command/profile before the Task -1 control commit is
created and pinned. Verified inherited mode does not transfer PASS authority
to Task -1 or candidate code; it only prevents the impossible second Seatbelt
application while preserving the same denial boundary.

---

## 6. Task -1 — Build and pin the trusted release-control verifier

This task runs on `codex/v433-safe-upgrade-design` before the implementation
worktree is created. It is a control-plane commit, not a fuse implementation
commit.

**Files:**

- Create: `tools/release-control/inherited_context.py`
- Create: `tools/release-control/run-isolated.py`
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
  `verify-quarantine-candidate.py` and `test_release_control.py` as
  applicable—uses the validated invocation-owned `TMPDIR` as its explicit
  parent. This is not limited to test fixtures. Direct `/private/tmp` writes
  are forbidden, and missing, non-canonical, non-directory,
  invocation-root-escaping or execution-root-contained `TMPDIR` must be
  rejected before creating any probe or writable directory.
- [ ] **E — trust promotion:** run staged spec review and staged quality review,
  then use three disjoint pre-commit command manifests because macOS rejects
  nested `sandbox-exec`. Run pure/control/inherited focused tests inside one
  `release-control-network-zero` outer sandbox with a manifest proving they do
  not invoke direct mode. Separately, with no outer Seatbelt already applied,
  have the pre-existing Task -2 external controller apply its independently
  pinned `release-candidate-network-zero` reference profile exactly once to
  every staged real-profile candidate/adversarial probe; do not execute the
  uncommitted launcher or verifier outside the outer control boundary. Run the
  exact staged full pre-commit gate in a third, separate
  `pinned-full-gate-loopback-only` invocation whose manifest proves it imports
  no Task -1 module. Bind all three manifests, profile digests, staged blob
  identities and receipts before creating the one Task -1 control commit. Then
  run the exact committed launcher/verifier direct integration manifest against
  that immutable control tree; any failure requires amending that one commit
  and repeating every review, manifest and gate from scratch. Resolve every
  finding and do not add a second commit for the module split.
- [ ] Commit these files on the design control branch and record the exact
  control commit SHA, inherited-validator/verifier/launcher/test digests and
  approved public-key identity in the plan execution receipt.
- [ ] All later baseline, candidate, commit-hook and rehearsal subprocesses
  must be launched through that exact control commit. Drift or replacement is a
  blocker.

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
- [ ] Run the original `bash scripts/pre-commit-check.sh` only through the
  verified isolation wrapper before any candidate surface edit and record its
  exit status and semantic counters.
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
- Create: `scripts/quarantine-fuse.py`
- Create: `mcp/tests/test_quarantine_fuse.py`

- [ ] Write focused tests that fail against the untouched original tree for:
  installable marketplace row, registered plugin hooks/MCP, active updater,
  active setup/cache scripts, active root/host instructions, active historical
  skills, implicit-default workflows, and absent Stage R contract.
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
  mcp/tests/test_quarantine_fuse.py -q
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
quarantine-tests: -I -m pytest -p no:cacheprovider --noconftest -c __SAMVIL_TRUSTED_PYTEST_CONFIG__ --rootdir=. --import-mode=importlib mcp/tests/test_quarantine_fuse.py -q
quarantine-gate: -I scripts/quarantine-fuse.py verify --policy release/quarantine/v4322-policy.json
```

`verify` binds its read-only root to the launcher's canonical current working
directory, performs no subprocess or temporary write, and is distinct from the
renderer subcommand whose output root must be explicit. The subprocess-heavy
`bash scripts/pre-commit-check.sh` is not a direct candidate command; it belongs
only to the separately pinned `pinned-full-gate-loopback-only` manifest.
The sentinel above is authorization data, never a filesystem path supplied by
the candidate. The pinned verifier requires it exactly once and substitutes
only the descriptor-validated trusted config path immediately before launch.

The external authorization also binds these exact semantic roles to candidate
inventory paths and SHA-256 values: `policy`, `plugin_manifest`,
`marketplace_manifest`, `mcp_manifest`, `passive_surface_manifest`, `gate`,
`validator` and `focused_test`. Their paths are respectively
`release/quarantine/v4322-policy.json`, `.claude-plugin/plugin.json`,
`.claude-plugin/marketplace.json`, `.mcp.json`,
`release/quarantine/v4322-passive-surface-manifest.json`,
`scripts/pre-commit-check.sh`, `scripts/quarantine-fuse.py` and
`mcp/tests/test_quarantine_fuse.py`. Whole-tree identity cannot substitute for
an omitted or misbound semantic role.

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
- [ ] Keep publisher/remote release-guard files unreachable from passive root
  instructions and workflows, but do not refactor them in F0. Focused tests
  must prove the rehearsal path never invokes the existing publisher.

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
- [ ] Repeat every invocation twice and require byte-identical receipts.
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
- [ ] Run the externally authorized quarantine pre-commit gate, then create
  the sole fuse implementation commit. Fixed parent, tree, message, author and
  committer inputs must be recorded so the exact commit object is reviewable.
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

Passing this task contributes to `F0_LOCAL_IMPLEMENTATION_GREEN` only. Actual
Codex/Claude/OpenCode/Gemini first-open, existing global MCP, selection/cache,
stale process/catalog and official historical-host execution remain mandatory
inputs to the separate `STAGE_A_PROMOTION_READY` decision.

---

## 13. Task 6 — Gates, commit, and reviews

- [ ] Focused quarantine tests GREEN.
- [ ] Quarantine-mode `bash scripts/pre-commit-check.sh` GREEN.
- [ ] Both baseline and quarantine gate commands were executed only through
  the verified isolation wrapper; bare invocation is forbidden.
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
- mirror rehearsal receipt;
- exact remaining untested public/historical surfaces;
- exact terminal status: `F0_LOCAL_IMPLEMENTATION_GREEN`,
  `BLOCKED_RELEASE_AUTHORIZATION`, or another typed blocker; never
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
- a repeated same-root failure occurs twice;
- implementation attempts public GitHub mutation or credentials;

If a candidate defect is found only after the exact implementation commit—for
example Stage A/R changes more than one ref, Stage R tree differs from original,
or final review finds a P1/P2—the commit/catalog/Stage R are marked `REJECTED`
and the fresh replacement cycle in Task 6 is mandatory. The rejected object is
not promotion eligible.

### 14.2 Promotion-only blockers

The following conditions allow a verified local implementation commit and an
honest `F0_LOCAL_IMPLEMENTATION_GREEN`, but prohibit
`STAGE_A_PROMOTION_READY` and every public mutation:

- historical official-artifact ledger is incomplete or has an unverifiable
  official identity;
- approved catalog/Stage R signing authority is unavailable;
- required historical or actual host artifacts are unavailable;
- actual supported-host cold/stale-disk/stale-process/no-ref/custom-main matrix
  is incomplete or has a blocking result;
- GitHub ruleset, App identity, public propagation or release-control evidence
  required by the parent design is missing.

These conditions must produce a typed promotion blocker. They must not be used
to fabricate signed evidence, claim Stage A readiness, or weaken local tests.

Both categories are blockers at their stated boundary, not reasons to weaken
an assertion or expand the F0 scope.
