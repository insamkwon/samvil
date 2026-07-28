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
| `tools/release-control/run-isolated.py` | Create and pin on design control branch before candidate work | Trusted `env -i`/sandbox/network-deny/child-supervision launcher |
| `tools/release-control/verify-quarantine-candidate.py` | Create and pin on design control branch before candidate work | Independently verify authorization signature, control commit, candidate tree and every policy/manifest/passive/gate digest |
| `tools/release-control/tests/test_release_control.py` | Create on design control branch | RED/GREEN tests for candidate bypass, forged GREEN output, sandbox escape, real-repository target and signature/digest failures |

The canonical catalog schema fixes its cutoff, known-official completeness
rules, historical snapshot/manifest rows and exactly-one fuse invariant. Each
historical row binds its discovered-surface-set digest, and the signed catalog
binds the complete historical-surface-ledger digest. Candidate authorization
is a separate sidecar and can never satisfy a distribution-row schema.

The trusted verifier/launcher commit SHA, file digests and approved public-key
identity are pinned before any candidate edit. Candidate-controlled code cannot
replace or configure them. The separate candidate-tree authorization is keyed
by tree SHA and content digests, so
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
- [ ] Invoke `/usr/bin/sandbox-exec` directly with an inline profile rendered
  from this plan's fixed template: `(deny default)`, allow only required
  process/mach/system-library reads, allow file reads for the exact pinned
  control worktree, hermetic temp runtime and archived temp snapshot,
  explicitly deny the source repository checkout and every other linked
  worktree, allow read/write only
  for the exact Task -1 temporary root and explicitly reviewed control files,
  and include no network allow rule.
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
  network socket creation fails; a surviving child is detected and killed.
- [ ] Record the expanded sandbox profile, its digest, environment-key list,
  executable digests, probe commands, denial log and result in a path-free
  bootstrap receipt.
- [ ] Run every Task -1 RED/GREEN test, normal full pre-commit gate, staged-tree
  review and `git commit` through this exact bootstrap boundary.
- [ ] Before trusting the committed launcher, make it reproduce the bootstrap
  probes and compare decisions/denials. Any weaker behavior blocks trust
  promotion.

No untrusted working-tree helper may wrap, replace, parameterize or interpret
the bootstrap command/profile before the Task -1 control commit is created and
pinned.

---

## 6. Task -1 — Build and pin the trusted release-control verifier

This task runs on `codex/v433-safe-upgrade-design` before the implementation
worktree is created. It is a control-plane commit, not a fuse implementation
commit.

**Files:**

- Create: `tools/release-control/run-isolated.py`
- Create: `tools/release-control/verify-quarantine-candidate.py`
- Create: `tools/release-control/tests/test_release_control.py`

- [ ] Write RED tests for a candidate that prints forged PASS, replaces its own
  verifier, supplies a candidate-local authorization, changes one authorized
  digest, requests the real repository as a ref target, reads the real profile,
  opens a network socket, spawns a surviving child, or omits an expected test.
- [ ] Implement the trusted isolation launcher with sanitized environment,
  macOS sandbox policy, hard network deny, child supervision and denial-log
  capture. It must run from the pinned control checkout, never import candidate
  Python modules, and treat candidate output as untrusted bytes.
- [ ] Implement the outer verifier to calculate Git tree/path/mode/blob
  identities itself, verify the external authorization and signature policy,
  execute candidate checks only inside the trusted sandbox, and independently
  calculate the final verdict.
- [ ] Run focused tests RED then GREEN, staged-tree reviews and the normal full
  pre-commit gate exclusively through the Task -2 bootstrap boundary.
- [ ] Commit these files on the design control branch and record the exact
  control commit SHA, verifier/launcher/test digests and approved public-key
  identity in the plan execution receipt.
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
<pinned-control>/run-isolated.py --snapshot <candidate-tree> -- \
  <hermetic-runtime>/bin/python3 -m pytest mcp/tests/test_quarantine_fuse.py -q
```

Expected RED: the original tree is correctly diagnosed as active and not a
quarantine fuse.

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
  helpers/askpass and disabled Git network protocols.
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
