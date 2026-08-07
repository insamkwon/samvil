# Task -2 Quota and Admission Environment Preparation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the trusted-control-side static admission contract and fail-closed parser for Task -2, then produce the exact external-authority acceptance packet required before any live quota/admission integration can begin.

**Architecture:** The repository may parse and pin static evidence but it may not manufacture a kernel quota, controller liveness, a Darwin process handle, or a canonical PASS. The disposable macOS VM, per-invocation APFS boundary, root-owned controller, native client, signer keys, and independent observer remain an external trusted computing base. A later, separately reviewed Task -2B plan can attach that authority to the full gate only after its native protocol is concrete.

**Tech Stack:** Python 3.9-compatible standard library and `/usr/bin/python3 -I -m unittest` for the preparation parser; receipt-pinned Python 3.12 only after R0; macOS APFS plus a root-owned LaunchDaemon/native helper supplied by an external provisioner; existing release-control unittest patterns.

---

## 1. Non-negotiable boundary

This plan is a descendant-only trusted-control preparation task. It is not a replay of historical Task -2 branch/bootstrap mechanics and it is not bridge feature work.

- Preserve PR #14 head `141da457a98b552047f0388b9967664e11aff8b1` and current plan commit `ac386f7ad696b56228c0994b0247ebd5b92d69ae`.
- Do not create or amend the Unit 0 candidate branch. Unit 0 remains a single direct candidate commit above original `81c0c3468ed8757513fc4bf76b028736197bc556` only after every prerequisite has been reviewed.
- Do not create an APFS volume, mount or resize a filesystem, invoke sudo, install a LaunchDaemon, signal a real process, or touch a user HOME, CODEX_HOME, Claude profile, cache, settings, or project.
- Do not modify the existing full-gate success path. Its current quota blocker remains correct until Task -2B is reviewed.

This document-review worktree is not a Task 0 implementation worktree. After this plan is reviewed and merged, Task 0 starts only from a newly created, clean descendant worktree whose current control commit has the reviewed plan commit/tree as an ancestor pinned by sealed trusted control; an untracked or modified copy of the plan itself never satisfies or bypasses `task2_execution_entry_gate`. `task2_plan_review_entry_gate` below is only a local guard for this one review branch. `task2_execution_entry_gate` is the only entry gate for Tasks 0-4 and gets reviewed-plan ancestry from a root-owned trusted-control helper rather than from a branch name or candidate argument. No Task 0-4 command is authorized in a dirty plan-review worktree.

Before Task -2B exists, the current full gate can produce only this blocker:

~~~
terminal = BLOCKED_ENVIRONMENT
detail   = UNSUPPORTED_INVOCATION_STORAGE_QUOTA
~~~

If a quota lease were supplied but the reviewed opaque Darwin process authority were absent, the current full gate can produce only this blocker:

~~~
terminal = BLOCKED_ENVIRONMENT
detail   = DETACHED_PROCESS_SIGNAL_UNAVAILABLE
~~~

After Task -2B is separately reviewed, the outer terminal remains `BLOCKED_ENVIRONMENT` for every admission denial and its only approved details are `UNSUPPORTED_INVOCATION_STORAGE_QUOTA`, `DETACHED_PROCESS_SIGNAL_UNAVAILABLE`, and `ADMISSION_RECOVERY_REQUIRED`; the third applies only to a verified trusted-control admission validation or recovery failure (outer assertion, signature/keyset, channel, status, controller, or journal/recovery), never to a quota/FD identity or opaque-process-state failure. Logical byte/FD scanning, RLIMIT values, a user-owned temporary directory, a static JSON file, a raw PID, PID plus start time, process group cleanup, polling, signal-by-name, a CLI flag, or an environment variable never replaces any of those results.

## 2. Entry gate and isolated portable envelope

`env -i` is defense in depth, not an operating-system isolation boundary: it redirects ordinary HOME/XDG/Codex/Claude lookups, but cannot prove that a repository helper has no hard-coded host path or that the host kernel denies access to a real user profile. Therefore this wrapper is permitted only *inside* a disposable VM or OS sandbox provisioned by independent trusted control. That provisioner must produce a signed, time-bounded sandbox attestation for the invocation stating the VM image and boot identity, dedicated unprivileged UID, read-only control source identity, a private per-invocation `/tmp` mount, and that host user-profile roots are neither mounted nor readable/writable by the runner. The attestation is verified from a root-owned control path before `task2_full_precommit`; it is never an environment variable, candidate artifact, or self-assertion by the runner. A host that lacks that independently verified VM/OS boundary (including the present workstation) may use the wrapper only for non-authoritative document/static checks and must treat `task2_full_precommit` as unavailable.

Create this disposable envelope before **every** local command, including an entry check:

~~~
task2_plan_root="$(/usr/bin/mktemp -d /tmp/samvil-task2-plan.XXXXXX)"
/bin/mkdir -p \
  "$task2_plan_root/home" \
  "$task2_plan_root/codex" \
  "$task2_plan_root/claude" \
  "$task2_plan_root/tmp" \
  "$task2_plan_root/xdg/cache" \
  "$task2_plan_root/xdg/config" \
  "$task2_plan_root/xdg/data" \
  "$task2_plan_root/xdg/state" \
  "$task2_plan_root/hooks"
: > "$task2_plan_root/gitconfig"
env -i \
  PATH=/usr/bin:/bin \
  HOME="$task2_plan_root/home" \
  CODEX_HOME="$task2_plan_root/codex" \
  CLAUDE_CONFIG_DIR="$task2_plan_root/claude" \
  TMPDIR="$task2_plan_root/tmp" \
  XDG_CACHE_HOME="$task2_plan_root/xdg/cache" \
  XDG_CONFIG_HOME="$task2_plan_root/xdg/config" \
  XDG_DATA_HOME="$task2_plan_root/xdg/data" \
  XDG_STATE_HOME="$task2_plan_root/xdg/state" \
  GIT_CONFIG_GLOBAL=/dev/null \
  GIT_CONFIG_NOSYSTEM=1 \
  GIT_TERMINAL_PROMPT=0 \
  /usr/bin/git config --file "$task2_plan_root/gitconfig" user.name "SAMVIL Control"
env -i \
  PATH=/usr/bin:/bin \
  HOME="$task2_plan_root/home" \
  CODEX_HOME="$task2_plan_root/codex" \
  CLAUDE_CONFIG_DIR="$task2_plan_root/claude" \
  TMPDIR="$task2_plan_root/tmp" \
  XDG_CACHE_HOME="$task2_plan_root/xdg/cache" \
  XDG_CONFIG_HOME="$task2_plan_root/xdg/config" \
  XDG_DATA_HOME="$task2_plan_root/xdg/data" \
  XDG_STATE_HOME="$task2_plan_root/xdg/state" \
  GIT_CONFIG_GLOBAL=/dev/null \
  GIT_CONFIG_NOSYSTEM=1 \
  GIT_TERMINAL_PROMPT=0 \
  /usr/bin/git config --file "$task2_plan_root/gitconfig" user.email "samvil-control@example.invalid"
run_task2_portable() {
  env -i \
    PATH=/usr/bin:/bin \
    HOME="$task2_plan_root/home" \
    CODEX_HOME="$task2_plan_root/codex" \
    CLAUDE_CONFIG_DIR="$task2_plan_root/claude" \
    TMPDIR="$task2_plan_root/tmp" \
    XDG_CACHE_HOME="$task2_plan_root/xdg/cache" \
    XDG_CONFIG_HOME="$task2_plan_root/xdg/config" \
    XDG_DATA_HOME="$task2_plan_root/xdg/data" \
    XDG_STATE_HOME="$task2_plan_root/xdg/state" \
    GIT_CONFIG_GLOBAL="$task2_plan_root/gitconfig" \
    GIT_CONFIG_NOSYSTEM=1 \
    GIT_OPTIONAL_LOCKS=0 \
    GIT_CONFIG_COUNT=2 \
    GIT_CONFIG_KEY_0=core.hooksPath \
    GIT_CONFIG_VALUE_0="$task2_plan_root/hooks" \
    GIT_CONFIG_KEY_1=core.fsmonitor \
    GIT_CONFIG_VALUE_1=false \
    GIT_TERMINAL_PROMPT=0 \
    PYTHONNOUSERSITE=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_CONFIG_FILE=/dev/null \
    PIP_NO_INDEX=1 \
    "$@"
}

task2_git() {
  run_task2_portable git "$@"
}

# A non-consuming root-owned control-plane check. Its sealed descriptor pins
# the reviewed plan commit/tree and validates current control ancestry from
# the read-only control source; neither a branch name nor a candidate-provided
# commit/path can select the approved plan.
task2_control_lineage_gate() {
  task2_control_commit="$(task2_git rev-parse HEAD)" || return $?
  task2_control_tree="$(task2_git rev-parse 'HEAD^{tree}')" || return $?
  run_task2_portable /usr/local/libexec/samvil-task2-control-lineage verify \
    --schema samvil.task2-approved-plan-lineage.v1 \
    --expected-control-commit "$task2_control_commit" \
    --expected-control-tree "$task2_control_tree" \
    --require-sealed-reviewed-plan-ancestor \
    --require-readonly-control-source
}

verify_task2_commit() {
  if test "$#" -eq 0; then
    echo "TASK2_COMMIT_SCOPE_INVALID: expected staged-path allowlist is required" >&2
    return 78
  fi
  task2_git diff --check || return $?
  task2_git diff --cached --check || return $?
  if ! task2_git diff --quiet; then
    echo "TASK2_COMMIT_SCOPE_INVALID: unstaged tracked changes are forbidden" >&2
    return 78
  fi
  if task2_git diff --cached --quiet; then
    echo "TASK2_COMMIT_SCOPE_INVALID: no staged changes" >&2
    return 78
  fi
  task2_status_path="$task2_plan_root/tmp/staged-status"
  task2_git status --porcelain=v1 --untracked-files=all >"$task2_status_path" || return $?
  run_task2_portable /usr/bin/python3 -I - "$task2_status_path" "$@" <<'PY'
from pathlib import Path
import sys

status = Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
allow = sys.argv[2:]
if not allow:
    raise SystemExit(78)

def allowed(path: str) -> bool:
    return any(path == item or (item.endswith("/") and path.startswith(item)) for item in allow)

for line in status:
    if len(line) < 4:
        raise SystemExit(78)
    index, worktree, path = line[0], line[1], line[3:]
    if index not in {"A", "M"} or worktree != " " or not allowed(path):
        raise SystemExit(78)
PY
}

task2_plan_review_entry_gate() {
  test "$(task2_git branch --show-current)" = "codex/v4323-task2-admission-plan" \
    && task2_git merge-base --is-ancestor ac386f7ad696b56228c0994b0247ebd5b92d69ae HEAD \
    && task2_git merge-base --is-ancestor 141da457a98b552047f0388b9967664e11aff8b1 HEAD \
    && test -x /usr/bin/python3 \
    && run_task2_portable /usr/bin/python3 -I -c "import unittest" \
    && task2_git diff --check \
    && test -z "$(task2_git status --porcelain)"
}

task2_execution_entry_gate() {
  task2_control_lineage_gate \
    && test -x /usr/bin/python3 \
    && run_task2_portable /usr/bin/python3 -I -c "import unittest" \
    && task2_git diff --check \
    && test -z "$(task2_git status --porcelain)"
}

task2_candidate_snapshot_gate() {
  task2_control_commit="$(task2_git rev-parse HEAD)" || return $?
  task2_control_tree="$(task2_git rev-parse 'HEAD^{tree}')" || return $?
  run_task2_portable /usr/local/libexec/samvil-task2-candidate-snapshot run-full-precommit \
    --schema samvil.task2-candidate-snapshot.v1 \
    --gate-profile samvil.task2-full-precommit.v1 \
    --expected-control-commit "$task2_control_commit" \
    --expected-control-tree "$task2_control_tree" \
    --expected-candidate-index-tree "$task2_candidate_index_tree" \
    --expected-precommit-mode "$task2_precommit_mode" \
    --require-root-selected-fresh-sandbox-attestation \
    --require-atomic-attestation-snapshot-venv-gate-transaction \
    --require-approved-task2-plan-ancestor \
    --require-dedicated-uid-readonly-control-source-and-host-profile-deny \
    --require-staged-descriptor-exact-base-to-candidate-path-set \
    --require-no-unlisted-tree-diff \
    --require-root-owned-readonly-index-tree-snapshot \
    --require-directory-nodes-and-regular-leaves-only \
    --require-beneath-snapshot-nofollow-resolution \
    --require-no-worktree-or-ignored-inputs \
    --require-root-owned-snapshot-git-namespace \
    --require-snapshot-index-exactly-candidate-tree \
    --require-no-original-gitdir-index-config-or-excludes \
    --require-root-selected-signed-venv-provenance \
    --require-verify-then-materialize-snapshot-venv \
    --require-revalidate-materialized-venv-output \
    --require-explicit-pytest-asyncio-plugin \
    --require-canonical-repository-precommit \
    --require-private-invocation-tmp-root
}

task2_commit_snapshot_receipt() {
  run_task2_portable /usr/local/libexec/samvil-task2-commit-fence commit \
    --schema samvil.task2-candidate-snapshot-commit.v1 \
    --require-root-selected-current-snapshot-receipt \
    --require-signed-success-and-single-use-receipt-consumption \
    --require-receipt-bound-base-head-and-control-tree \
    --require-receipt-bound-candidate-index-tree \
    --require-sealed-task-descriptor-and-commit-message \
    --require-immutable-git-commit-tree \
    --require-atomic-ref-compare-and-swap \
    --require-no-caller-supplied-tree-ref-message-or-index-input \
    --require-durable-commit-intent-and-recovery \
    --require-refuse-if-execution-index-tree-differs \
    --require-clean-post-commit-state
}

task2_full_precommit() {
  case "${1:---staged}" in
    --clean) task2_precommit_mode=clean ;;
    --staged) task2_precommit_mode=staged ;;
    *)
      echo "TASK2_PORTABLE_FULL_GATE_UNAVAILABLE: expected --clean or --staged" >&2
      return 78
      ;;
  esac
  case "$task2_precommit_mode" in
    clean)
      task2_git diff --quiet || return $?
      task2_git diff --cached --quiet || return $?
      task2_candidate_index_tree="$(task2_git rev-parse 'HEAD^{tree}')" || return $?
      ;;
    staged)
      task2_git diff --quiet || return $?
      task2_git diff --cached --quiet
      task2_cached_diff_status=$?
      case "$task2_cached_diff_status" in
        0)
          echo "TASK2_PORTABLE_FULL_GATE_UNAVAILABLE: staged candidate is absent" >&2
          return 78
          ;;
        1) ;;
        *) return "$task2_cached_diff_status" ;;
      esac
      task2_candidate_index_tree="$(task2_git write-tree)" || return $?
      ;;
    *)
      echo "TASK2_PORTABLE_FULL_GATE_UNAVAILABLE: unknown precommit mode" >&2
      return 78
      ;;
  esac
  task2_status_before="$(task2_git status --porcelain)" || return $?
  if ! task2_candidate_snapshot_gate; then
    echo "TASK2_PORTABLE_FULL_GATE_UNAVAILABLE: root-owned attested snapshot gate failed" >&2
    return 78
  fi
  if test "$task2_status_before" = "$(task2_git status --porcelain)" \
    && test "$task2_candidate_index_tree" = "$(task2_git write-tree)"; then
    return 0
  fi
  run_task2_portable /usr/local/libexec/samvil-task2-candidate-snapshot invalidate-pending-receipt \
    --schema samvil.task2-candidate-snapshot-receipt.v1 \
    --require-root-selected-current-invocation-receipt \
    --reason execution-index-or-status-drift \
    || return $?
  echo "TASK2_PORTABLE_FULL_GATE_UNAVAILABLE: execution tree drift invalidated snapshot receipt" >&2
  return 78
}
~~~

The VM-image components are part of the external trusted-control packet, not repository dependencies or a claim that `env -i` has sandboxed the current host. `samvil-task2-candidate-snapshot` is their sole transaction coordinator: the shell never receives an attestation-consumption handle, receipt ID, snapshot path, task descriptor, or writable authority. In one root-owned transaction it selects the only fresh `samvil.task2-os-sandbox-attestation.v1` record from its private queue, verifies its schema/version, purpose `task2_full_precommit`, mode (`clean` or `staged`), VM-image digest, boot generation, dedicated/caller UID, base control commit/tree, candidate index tree, root-pinned reviewed-plan ancestry, read-only control-source mount/object identity, private-invocation-`/tmp` mount/object identity and cleanup proof, host-profile-deny proof digest, single-use challenge, issued/expiry timestamps, signer keyset/key ID/algorithm, canonical signed-preimage digest, and signature. In `clean` mode the candidate index tree is exactly `HEAD^{tree}` with no worktree/index diff. In `staged` mode it is exactly `git write-tree` after `verify_task2_commit` has rejected every unstaged/untracked/out-of-scope file, and the provisioner also queues one sealed task descriptor selected by that exact base tree/candidate tree/mode: it contains the exact base-to-candidate add/modify path-status set, target ref, commit subject/body, fixed author/committer identity, and expiry. Before consuming either record, the coordinator derives that path-status set directly from sealed Git objects and requires exact equality with the descriptor; an extra, missing, renamed, copied, deleted, or differently typed path is denied. Its `task_descriptor_sha256` is a signed attestation field and binds the descriptor to that exact base/candidate/mode/challenge. Only after all of those checks does the coordinator atomically change the attestation from pending to consumed. The resulting private consumption receipt is retained only by the coordinator and is bound to the command purpose, base commit/tree, candidate index tree, VM boot, caller, challenge, and, for staged mode, `task_descriptor_sha256` plus its exact path-status digest. A generic valid attestation cannot be replayed for another worktree, candidate tree, commit/tree, caller, boot, purpose, or invocation. The external provisioner—not the repository, runner, or candidate—must mint and queue one newly signed attestation immediately before **each** `task2_full_precommit`; a consumed, failed, expired, previous-task, or abandoned record is never retried or renewed in place. On every transaction failure the coordinator writes an abort/denial receipt and makes the attestation unreachable to a later snapshot or commit fence. Its executable and every ancestor on the VM image must be root-owned and neither group- nor world-writable; its code-signature/digest and attestation signer/keyset are pinned by the sealed VM-control root before it reads a record. Its implementation, queue state transition, exit status, and denial proof are reviewed with the external packet. A copied executable, environment variable, candidate-controlled attestation, or shared host `/tmp` cannot satisfy this transaction.

`task2_control_lineage_gate` is deliberately non-consuming: the sealed helper knows the merged plan commit/tree and rejects a current control source that is not its reviewed descendant. It is used at the start of Tasks 0-4 so a post-merge execution branch can be named freely without turning a branch name into authority. Within the snapshot transaction, the root-owned `samvil-task2-venv-provenance` verifier first validates a signed `samvil.task2-venv-provenance.v1` record and install *recipe* against sealed Git objects—base control commit/tree, unchanged `mcp/pyproject.toml` blob/digest, CPython 3.12 base-interpreter digest, signed offline wheelhouse and requirements-lock digests, exact `pytest`/`pytest-asyncio` distribution digests, expected snapshot-venv layout/output digest, issued/expiry time, signer keyset/key ID/algorithm, canonical preimage digest, and signature. No snapshot venv exists at this first validation point. Only after it succeeds does the coordinator create the root-owned snapshot-local venv and then revalidate its actual interpreter, distributions, layout, and output digest before any test. A new provenance record is required whenever the clean base `HEAD` changes after a task commit; it may not be carried from Task 1 into Task 2/3 under a new base tree.

After the attestation and provenance recipe have been verified in that same transaction, the root-owned coordinator resolves the attested index tree directly from the sealed Git object store and materializes a fresh `samvil.task2-candidate-snapshot.v1` source snapshot. It traverses Git `040000` tree nodes only through descriptor-relative no-follow directory access and accepts leaf blobs only with modes `100644` or `100755`; every symlink (`120000`), gitlink (`160000`), special/unknown leaf mode, unsafe path component, or materialization mismatch is denied before a file is opened. It materializes and subsequently resolves every source component below the snapshot root through descriptor-relative no-follow access; no path lookup can leave that root. It never reads the caller worktree, `.gitignore`/global-exclude contents, untracked or ignored files, a caller path, or a caller command. The source snapshot contains no inherited `.git` directory. Before the canonical pre-commit script runs, the coordinator creates a separate root-owned snapshot Git namespace: its private `HEAD` is the receipt-bound base commit, its private index is populated exactly from the receipt-bound candidate tree, and its only worktree is the read-only snapshot. It launches the script with only those namespace-local `GIT_DIR`, `GIT_INDEX_FILE`, `GIT_WORK_TREE`, and root-pinned no-system/no-global configuration values; the execution worktree Git directory/index, all Git environment inheritance, alternates, global excludes, and user/system config are unreachable. Thus `git diff --cached` sees exactly candidate-versus-base paths, while a clean candidate falls back to `git ls-files` for exactly the snapshot tree. The source tree is read-only; its private test-output overlay cannot shadow a source, script, module, test input, or snapshot Git namespace, and the helper supplies only that overlay, the newly validated snapshot-local `mcp/.venv`, and the attested private `/tmp`. Its sealed `samvil.task2-full-precommit.v1` profile runs exactly (first) `mcp/.venv/bin/python -I -B -m pytest -p pytest_asyncio.plugin -p no:cacheprovider tests/ -q --tb=no -rX`, failing on async-plugin warnings, and then (second) `/bin/bash scripts/pre-commit-check.sh` with its canonical pytest semantics inside that snapshot Git namespace. It must not set `PYTEST_DISABLE_PLUGIN_AUTOLOAD`, accept a candidate-supplied command, or mount a writable source path. The helper emits a signed `samvil.task2-candidate-snapshot-receipt.v1` binding the private attestation-consumption receipt digest, base control commit/tree, candidate index tree, materialized source-tree/object digest, snapshot-Git-namespace/index digest, snapshot venv-provenance receipt digest, sealed gate-profile digest, private-`/tmp` identity, exact command/output digests, and cleanup result. A `clean` receipt is terminal verification evidence with **no** commit authorization. A `staged` receipt additionally binds the selected `task_descriptor_sha256`, its exact base-to-candidate path-status digest, and a one-shot commit-authorization expiry; the descriptor's sealed contents include the exact target ref and commit message, and only that kind can become pending for the commit fence. The full gate accepts only that receipt's success; neither helper accepts an interpreter, wheelhouse, lock, receipt, source path, plan commit, candidate tree, task descriptor, or trust anchor selected by candidate data.

`samvil-task2-commit-fence` is the only permitted successor to a successful staged snapshot transaction. It root-selects the single current, unexpired pending snapshot receipt through the private ledger; no caller supplies a receipt, tree, ref, branch, message, task descriptor, or index path. It verifies the receipt signature and its attestation-consumption/base-control/candidate-tree/task-descriptor bindings, temporarily freezes the execution worktree/index, and refuses if a locked `git write-tree` differs from the receipt. It does **not** use that index to construct a commit: from a root-owned Git namespace it creates the commit only with the exact receipt-bound immutable tree and receipt-bound base parent, fixed identity and commit message from the receipt-bound sealed task descriptor, then publishes the descriptor's sealed target ref solely through an atomic compare-and-swap against that base parent. A durable commit intent is written before object/ref mutation; recovery may publish exactly the one receipt-bound result or fail closed, never create a second commit. The fence atomically consumes the snapshot receipt on success or invalidates it on any mismatch/failure, restores/rechecks a clean execution state before releasing its write freeze, and emits a signed `samvil.task2-candidate-snapshot-commit.v1` receipt binding the snapshot-receipt digest, descriptor digest, exact tree, parent, target ref, and created commit. Therefore an index change after the snapshot cannot cause a different tree to be committed, and a previously successful snapshot cannot be replayed as a later commit capability.

For this document PR only, use `task2_plan_review_entry_gate` before editing; after merge, use `task2_execution_entry_gate` before every Task 0-4 start. Both are fail-closed chains; a nonzero result authorizes neither editing nor a later commit:

~~~
task2_execution_entry_gate
~~~

Expected: the work is on the sealed reviewed-plan ancestry, no historical fixup/autosquash/rewrite command is being used, and the worktree is clean before the task begins. The wrapper disables global/system Git config, hooks, fsmonitor, optional index locks, prompts, user site packages, external package indexes, and all user-scoped Codex/Claude/XDG locations; the Git config is inherited by helper scripts launched through `run_task2_portable`. The repository pre-commit script currently has fixed `/tmp/samvil-*.log` paths, so the external VM attestation must prove that `/tmp` itself is a fresh private per-invocation mount before it runs; `TMPDIR` alone is not accepted as proof. This is a process-environment restriction, not a filesystem-safety proof; only the independently attested VM/OS boundary above establishes that proof. If any assertion fails, stop before editing.

Tasks 1-2 use only the present system `/usr/bin/python3` standard-library `unittest` runner under the disposable envelope. They do not bootstrap or use an untracked virtual environment, are not R0 proof, and cannot issue a P0 result. `run_task2_portable` deliberately does **not** set `PYTEST_DISABLE_PLUGIN_AUTOLOAD`: the repository's full pre-commit script is run with its canonical pytest semantics, and the reviewed isolated `mcp/.venv` must contain only its pinned test dependencies, including `pytest-asyncio`. This avoids turning asynchronous coverage into a skipped or altered run; the later R0/full-gate wrapper separately pins `-p pytest_asyncio.plugin`. Stage only the listed files, run the focused test command, pass that task's explicit staged-path allowlist to `verify_task2_commit`, and then use only `task2_commit_snapshot_receipt`; ordinary Git commits, hooks, and a caller-selected commit message are outside the authorized fence.

Every repository-side state-changing fence below is one literal `&&` chain. The explicit external attestation handoff sits only between the freeze fence and the snapshot/commit fence, makes no repository change, and is performed by trusted control rather than a candidate worker. The root-owned snapshot transaction and root-owned receipt-consuming commit fence are individually fail-closed; paste and run each repository chain as shown, and never invoke the commit fence after a failed prerequisite.

## 3. File map

| File | Responsibility |
| --- | --- |
| `docs/superpowers/control/2026-08-08-task2-admission-trust-root.md` | Trusted-control-only root descriptor source, ownership, and candidate-exclusion rule. |
| `docs/superpowers/specs/2026-08-08-samvil-task2-admission-contract.md` | Exact static schemas, trust ownership, typed terminals, and Task -2B inputs. |
| `tools/release-control/invocation_admission.py` | Python 3.9-compatible static parser and explicit no-live-authority blocker. |
| `tools/release-control/tests/test_invocation_admission.py` | Portable RED/GREEN tests; no fixture can produce a canonical capability. |
| `tools/release-control/tests/fixtures/task2-admission/` | Canonical JSON test vectors only; never a trusted root or authority source. |
| `docs/superpowers/operations/2026-08-08-task2-admission-provisioner-handoff.md` | Exact external VM/controller/signer/observer acceptance packet. |

No change is made in this plan to `tools/release-control/run-full-gate-isolated.py`, `tools/release-control/verify-quarantine-candidate.py`, a full-gate manifest, or a full-gate receipt. Those changes belong to Task -2B after the external protocol is independently reviewed.

## 4. Static schemas

The following records are static input descriptions. Their successful parsing is always portable-contract evidence, never a live admission capability. The trusted root is a distinct input owned by trusted control; policy, candidate code, public CLI arguments, environment variables, and a fixture may not select or replace it.

### 4.1 Trusted root descriptor

~~~
{
  "schema": "samvil.task2-admission-trust-root.v1",
  "root_id": "lowercase-hyphenated-id",
  "run_envelope_trust_anchor_sha256": "64 lowercase hex",
  "observer_trust_anchor_sha256": "64 lowercase hex",
  "controller_keyset_sha256": "64 lowercase hex",
  "outer_verifier_keyset_sha256": "64 lowercase hex",
  "controller_signature_algorithm": "ed25519"
}
~~~

`docs/superpowers/control/2026-08-08-task2-admission-trust-root.md` defines the trusted-control artifact source: a sealed outer-verifier descriptor pins the canonical descriptor digest before candidate resolution; it is not found by path, CLI flag, environment variable, candidate checkout, or policy. The two anchor values must be distinct. A JSON fixture only tests parser shape and is never that sealed descriptor.

### 4.2 Policy

~~~
{
  "schema": "samvil.task2-admission-policy.v1",
  "authority_id": "lowercase-hyphenated-id",
  "platform": "darwin-arm64",
  "os_build": "darwin-build-id",
  "dedicated_uid": 501,
  "controller_executable_sha256": "64 lowercase hex",
  "controller_client_sha256": "64 lowercase hex",
  "controller_peer_identity_sha256": "64 lowercase hex",
  "controller_policy_sha256": "64 lowercase hex",
  "controller_keyset_sha256": "64 lowercase hex",
  "controller_journal_schema": "lowercase-dot-schema-id",
  "run_envelope_trust_anchor_sha256": "64 lowercase hex",
  "observer_trust_anchor_sha256": "64 lowercase hex",
  "storage_boundary_class": "invocation_exclusive_kernel_quota",
  "minimum_quota_bytes": 1,
  "maximum_quota_bytes": 1,
  "maximum_file_count": 1,
  "signal_authority_schema": "samvil.task2-darwin-opaque-process-authority.v1",
  "normalized_projection_schema": "samvil.task2-normalized-projection.v1"
}
~~~

The static validator requires policy anchor and controller-keyset values to equal the separate trusted-root descriptor, and requires the two anchor values to differ. A policy that chooses its own signer, has an unknown key, uses a raw-PID-style provider, or has a non-canonical field set is invalid.

### 4.3 Lease

~~~
{
  "schema": "samvil.task2-admission-lease.v1",
  "lease_id": "lowercase-hyphenated-id",
  "run_id": "lowercase-hyphenated-id",
  "nonce": "64 lowercase hex",
  "control_commit": "40 lowercase hex",
  "control_tree": "40 lowercase hex",
  "manifest_schema": "samvil.full-gate-manifest.v2",
  "manifest_sha256": "64 lowercase hex",
  "trust_root_sha256": "64 lowercase hex",
  "policy_sha256": "64 lowercase hex",
  "boot_generation": "64 lowercase hex",
  "controller_instance": "64 lowercase hex",
  "controller_journal_sequence": 1,
  "dedicated_uid": 501,
  "run_envelope_sha256": "64 lowercase hex",
  "run_envelope_signer_sha256": "64 lowercase hex",
  "run_envelope_verification_transcript_sha256": "64 lowercase hex",
  "storage": {
    "class": "invocation_exclusive_kernel_quota",
    "mount_identity_sha256": "64 lowercase hex",
    "mount_fsid_sha256": "64 lowercase hex",
    "quota_bytes": 1,
    "file_count_limit": 1,
    "exclusive_writer_proof_sha256": "64 lowercase hex",
    "cleanup_unmount_contract_sha256": "64 lowercase hex"
  },
  "signal_authority": {
    "schema": "samvil.task2-darwin-opaque-process-authority.v1",
    "identity_handle_sha256": "64 lowercase hex",
    "controller_receipt_sha256": "64 lowercase hex"
  },
  "issued_unix_seconds": 1,
  "expires_unix_seconds": 2
}
~~~

### 4.4 Independent observer projection

~~~
{
  "schema": "samvil.task2-observer-projection.v1",
  "run_id": "lowercase-hyphenated-id",
  "nonce": "64 lowercase hex",
  "observer_id": "lowercase-hyphenated-id",
  "observer_evidence_sha256": "64 lowercase hex",
  "observer_signer_sha256": "64 lowercase hex",
  "observer_verification_transcript_sha256": "64 lowercase hex",
  "control_commit": "40 lowercase hex",
  "control_tree": "40 lowercase hex",
  "trust_root_sha256": "64 lowercase hex",
  "policy_sha256": "64 lowercase hex",
  "storage_boundary_sha256": "64 lowercase hex",
  "signal_authority_sha256": "64 lowercase hex",
  "normalized_projection_sha256": "64 lowercase hex"
}
~~~

Within a single run, lease and observer bind the same run ID and nonce. Across independent run A and run B, run ID, nonce, lease ID, issued time, observer ID, and signature bytes must differ. Only a same-run/same-nonce response-loss replay may compare authoritative receipt bytes.

### 4.5 Derived static digests

`canonical_json_bytes(value)` means UTF-8 `json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")` after the bounded parser has accepted the value. `LP(items...)` means the concatenation of each item as an unsigned 32-bit big-endian byte length followed by its bytes. `hex32(x)` is the raw 32 bytes obtained by decoding an exactly 64-lowercase-hex digest; `hex20(x)` is the raw 20 bytes obtained by decoding an exactly 40-lowercase-hex commit/tree; schema IDs and literal words are UTF-8 bytes. A 64-hex digest, anchor, keyset, nonce, or transcript is never fed to `LP` as its 64 ASCII characters unless a rule explicitly says `utf8(x)`. The following values are the only permitted definitions:

~~~
policy_sha256 = sha256(canonical_json_bytes(policy))
trust_root_sha256 = sha256(canonical_json_bytes(trust_root))
run_envelope_evidence_sha256 = sha256(canonical_json_bytes(run_envelope_evidence))
observer_evidence_sha256 = sha256(canonical_json_bytes(observer_evidence))
run_envelope_verification_transcript_sha256 = sha256(LP(
  b"samvil.task2-run-envelope-verification.v1",
  hex32(run_envelope_evidence_sha256),
  hex32(trusted_root["run_envelope_trust_anchor_sha256"]),
  hex32(run_envelope_evidence["verifier_keyset_sha256"]),
  b"verified"
))
observer_verification_transcript_sha256 = sha256(LP(
  b"samvil.task2-observer-verification.v1",
  hex32(observer_evidence_sha256),
  hex32(trusted_root["observer_trust_anchor_sha256"]),
  hex32(observer_evidence["verifier_keyset_sha256"]),
  b"verified"
))
storage_boundary_sha256 = sha256(canonical_json_bytes({
  "schema": "samvil.task2-storage-boundary-binding.v1",
  "lease_id": lease["lease_id"],
  "run_id": lease["run_id"],
  "storage": lease["storage"]
}))
signal_authority_sha256 = sha256(canonical_json_bytes({
  "schema": "samvil.task2-signal-authority-binding.v1",
  "lease_id": lease["lease_id"],
  "run_id": lease["run_id"],
  "signal_authority": lease["signal_authority"]
}))
normalized_projection_sha256 = sha256(canonical_json_bytes({
  "schema": policy["normalized_projection_schema"],
  "trust_root_sha256": trust_root_sha256,
  "policy_sha256": policy_sha256,
  "control_commit": lease["control_commit"],
  "control_tree": lease["control_tree"],
  "storage_class": lease["storage"]["class"],
  "quota_bytes": lease["storage"]["quota_bytes"],
  "file_count_limit": lease["storage"]["file_count_limit"],
  "signal_authority_schema": lease["signal_authority"]["schema"]
}))
~~~

`lease.policy_sha256`, `lease.trust_root_sha256`, `lease.run_envelope_sha256`, `lease.run_envelope_signer_sha256`, and `lease.run_envelope_verification_transcript_sha256` must equal respectively `policy_sha256`, `trust_root_sha256`, `run_envelope_evidence_sha256`, `run_envelope_evidence.signer_sha256`, and `run_envelope_verification_transcript_sha256`. The run-envelope's run ID, nonce, control commit/tree, manifest schema/digest, policy digest, and trust-root digest must equal the corresponding lease fields. `observer.observer_evidence_sha256`, `observer.observer_signer_sha256`, and `observer.observer_verification_transcript_sha256` must equal respectively `observer_evidence_sha256`, `observer_evidence.signer_sha256`, and `observer_verification_transcript_sha256`; the observer evidence's run ID, nonce, control commit/tree, policy/trust-root, storage-boundary, signal-authority, and normalized-projection fields must equal the observer/lease projections. `observer.policy_sha256`, `observer.trust_root_sha256`, `observer.storage_boundary_sha256`, `observer.signal_authority_sha256`, and `observer.normalized_projection_sha256` must match these exact values. The static parser checks exact canonical-record/digest/projection equality only; its `verification_result == "verified"` string is not a cryptographic verdict and cannot authorize anything. Task -2B must independently verify the original signatures, keysets, anchors, identities, expiry, and bindings before consuming these projections. The normalized projection deliberately excludes run ID, nonce, lease ID, issued/expiry time, observer ID, signatures, controller instance, boot generation, mount identity, and opaque-handle identity, so independent admissible runs under the same policy/control identity normalize equally. Fixtures carry the resulting values, and Task 2 tests recompute them; a different domain string, omitted `lease_id` or `run_id` where required, reserialized noncanonical bytes, an evidence/projection mismatch, or whole-document substitute is invalid.

## 5. Task sequence

### Task 0: Establish the isolated full pre-commit gate or stop

**Files:** no repository file changes are authorized in this task.

Start only from a clean post-merge execution worktree:

~~~
task2_execution_entry_gate
~~~

- [ ] **Step 1: Admit an isolated verification runtime**

The external provisioner first creates the sealed `samvil.task2-venv-provenance.v1` record and install recipe for this clean Task 0 base, then queues exactly one new `task2_full_precommit` sandbox attestation for the clean candidate tree; a previous review, Task, failure, expired challenge, or older base commit cannot be reused. Without the independently verified disposable VM/OS sandbox attestation, `task2_full_precommit` is unavailable and no implementation commit is authorized. Inside its one root-owned transaction, the snapshot coordinator's provenance verifier pins CPython 3.12.x base-interpreter digest, base source commit/tree and unchanged `mcp/pyproject.toml` blob, signed offline wheelhouse/requirements-lock digest, exact `pytest`/`pytest-asyncio` distribution digests, expected snapshot-local install layout/output digest, expiry, and signature; it verifies the recipe before creating any snapshot and revalidates the actual result afterward. The root-owned snapshot helper, not the execution worktree, creates its fresh `mcp/.venv` with that CPython using `python -m venv --copies`, installs only from the signed wheelhouse with no network or user index, and places it in the immutable candidate snapshot. That snapshot-local `.venv`, `.venv/bin/python`, and `pyvenv.cfg` must be non-symlinks; Python must report exactly that snapshot-local venv as `sys.prefix`, report Python `3.12.x`, import both `pytest` and `pytest_asyncio`, use a base prefix/executable only below `/System`, `/Library/Developer`, or `/usr/bin`, and have root-owned non-group/world-writable base-executable ancestors. `/opt`, a user-owned framework, HOME, CODEX_HOME, a Claude profile, cache, an execution-worktree venv, or any project outside the snapshot is rejected. Otherwise `task2_full_precommit` returns 78. The runtime is only a full-pre-commit prerequisite; it is not the R0 receipt-pinned Python 3.12 closure and cannot issue P0 evidence.

- [ ] **Step 2: Prove the complete repository gate before any Task 1-3 commit**

Run:

~~~
task2_full_precommit --clean
~~~

Expected: the helper atomically consumes this invocation's fresh sandbox attestation and records its signed consumption receipt; it then verifies the sealed 3.12 wheelhouse/install provenance, materializes the exact clean Git tree into a root-owned immutable snapshot, and records the signed snapshot-gate receipt. The explicit `pytest_asyncio.plugin` run exits 0 without an async-plugin warning, `bash scripts/pre-commit-check.sh` exits 0 only inside that snapshot under the private `/tmp` mount, and the original execution worktree's Git status/index tree is byte-for-byte unchanged. If the OS attestation/runtime provenance/snapshot receipt is absent, stale, already consumed, base/tree/purpose-mismatched, or otherwise invalid, `TASK2_PORTABLE_FULL_GATE_UNAVAILABLE` is returned, any command is nonzero, or worktree drift appears, stop: do not stage, commit, push, or substitute a focused test. The next authorized action is to provision/review the VM/OS boundary and isolated verification runtime, not to weaken the gate.

### Task 1: Define static contract and fail-closed parser

Start only after `task2_execution_entry_gate` passes in a clean worktree. Task 0's venv-provenance record remains valid because Task 1 begins at that same base commit/tree. The sandbox attestation cannot be queued yet: Step 5 first freezes the exact staged candidate index tree; only trusted control may then derive that tree independently and queue its single-use attestation.

**Files:**

- Create: `docs/superpowers/control/2026-08-08-task2-admission-trust-root.md`
- Create: `docs/superpowers/specs/2026-08-08-samvil-task2-admission-contract.md`
- Create: `tools/release-control/invocation_admission.py`
- Create: `tools/release-control/tests/test_invocation_admission.py`
- Modify: `.github/workflows/release-checks.yml`
- Create: `tools/release-control/tests/fixtures/task2-admission/valid-trust-root.json`
- Create: `tools/release-control/tests/fixtures/task2-admission/valid-policy.json`
- Create: `tools/release-control/tests/fixtures/task2-admission/valid-lease.json`
- Create: `tools/release-control/tests/fixtures/task2-admission/valid-observer.json`
- Create: `tools/release-control/tests/fixtures/task2-admission/valid-run-envelope-evidence.json`
- Create: `tools/release-control/tests/fixtures/task2-admission/valid-observer-evidence.json`
- Create: `tools/release-control/tests/fixtures/task2-admission/duplicate-policy.json`
- Create: `tools/release-control/tests/fixtures/task2-admission/raw-pid-lease.json`
- Create: `tools/release-control/tests/fixtures/task2-admission/oversized-policy.json`
- Create: `tools/release-control/tests/fixtures/task2-admission/deep-policy.json`
- Create: `tools/release-control/tests/fixtures/task2-admission/nan-policy.json`
- Create: `tools/release-control/tests/fixtures/task2-admission/lone-surrogate-policy.json`

- [ ] **Step 1: Write the failing tests**

~~~
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

TOOLS_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = TOOLS_ROOT / "tests" / "fixtures" / "task2-admission"
SPEC = importlib.util.spec_from_file_location(
    "samvil_invocation_admission",
    TOOLS_ROOT / "invocation_admission.py",
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("invocation admission module cannot be loaded")
admission = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = admission
SPEC.loader.exec_module(admission)


class StaticAdmissionTests(unittest.TestCase):
    def fixture(self, name: str) -> bytes:
        return (FIXTURE_ROOT / name).read_bytes()

    def test_valid_static_documents_parse_as_data_only(self) -> None:
        trust_root = admission.parse_trust_root_bytes(self.fixture("valid-trust-root.json"))
        policy = admission.parse_policy_bytes(self.fixture("valid-policy.json"))
        lease = admission.parse_lease_bytes(self.fixture("valid-lease.json"))
        observer = admission.parse_observer_bytes(self.fixture("valid-observer.json"))
        run_envelope_evidence = admission.parse_run_envelope_evidence_bytes(
            self.fixture("valid-run-envelope-evidence.json")
        )
        observer_evidence = admission.parse_observer_evidence_bytes(
            self.fixture("valid-observer-evidence.json")
        )
        self.assertEqual(policy["storage_boundary_class"], "invocation_exclusive_kernel_quota")
        self.assertEqual(lease["nonce"], observer["nonce"])
        self.assertEqual(run_envelope_evidence["run_id"], lease["run_id"])
        self.assertEqual(observer_evidence["observer_id"], observer["observer_id"])
        self.assertNotEqual(
            trust_root["run_envelope_trust_anchor_sha256"],
            trust_root["observer_trust_anchor_sha256"],
        )
        self.assertEqual(type(policy), dict)

    def test_duplicate_key_rejects_before_semantic_validation(self) -> None:
        with self.assertRaises(admission.AdmissionError) as raised:
            admission.parse_policy_bytes(self.fixture("duplicate-policy.json"))
        self.assertEqual(raised.exception.status, "ADMISSION_POLICY_JSON_INVALID")

    def test_raw_pid_provider_is_never_admitted(self) -> None:
        with self.assertRaises(admission.AdmissionError) as raised:
            admission.parse_lease_bytes(self.fixture("raw-pid-lease.json"))
        self.assertEqual(raised.exception.status, "DETACHED_PROCESS_SIGNAL_UNAVAILABLE")

    def test_resource_and_unicode_attacks_are_typed(self) -> None:
        for fixture in (
            "oversized-policy.json",
            "deep-policy.json",
            "nan-policy.json",
            "lone-surrogate-policy.json",
        ):
            with self.subTest(fixture=fixture), self.assertRaises(admission.AdmissionError) as raised:
                admission.parse_policy_bytes(self.fixture(fixture))
            self.assertEqual(raised.exception.status, "ADMISSION_POLICY_JSON_INVALID")
~~~

- [ ] **Step 2: Confirm RED**

Run:

~~~
run_task2_portable /usr/bin/python3 -I -m unittest discover -s tools/release-control/tests -p 'test_invocation_admission.py' -v
~~~

Expected: collection fails because `invocation_admission.py` does not exist.

- [ ] **Step 3: Implement the minimal static parser**

~~~
from __future__ import annotations

import json


MAX_STATIC_BYTES = 16 * 1024
MAX_STATIC_DEPTH = 16
MAX_INTEGER_DIGITS = 20


class AdmissionError(ValueError):
    def __init__(self, status: str) -> None:
        super().__init__(status)
        self.status = status


def _pairs_without_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate")
        result[key] = value
    return result


def _bounded_int(token: str) -> int:
    digits = token[1:] if token.startswith("-") else token
    if not digits or len(digits) > MAX_INTEGER_DIGITS:
        raise ValueError("integer")
    return int(token)


def _reject_non_integer(token: str) -> object:
    del token
    raise ValueError("non-integer")


def _validate_depth(value: object, depth: int = 0) -> None:
    if depth > MAX_STATIC_DEPTH:
        raise ValueError("depth")
    if type(value) is dict:
        for nested in value.values():
            _validate_depth(nested, depth + 1)
    elif type(value) is list:
        for nested in value:
            _validate_depth(nested, depth + 1)


def _parse_static(raw: bytes, schema: str, status: str) -> dict[str, object]:
    try:
        if type(raw) is not bytes or len(raw) > MAX_STATIC_BYTES:
            raise ValueError("size")
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs_without_duplicates,
            parse_int=_bounded_int,
            parse_float=_reject_non_integer,
            parse_constant=_reject_non_integer,
        )
        _validate_depth(value)
        canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        if type(value) is not dict or value.get("schema") != schema or canonical != raw:
            raise ValueError("schema")
    except (MemoryError, RecursionError, UnicodeError, ValueError, TypeError):
        raise AdmissionError(status)
    return value


def parse_trust_root_bytes(raw: bytes) -> dict[str, object]:
    return _parse_static(raw, "samvil.task2-admission-trust-root.v1", "ADMISSION_TRUST_ROOT_JSON_INVALID")


def parse_policy_bytes(raw: bytes) -> dict[str, object]:
    return _parse_static(raw, "samvil.task2-admission-policy.v1", "ADMISSION_POLICY_JSON_INVALID")


def parse_lease_bytes(raw: bytes) -> dict[str, object]:
    value = _parse_static(raw, "samvil.task2-admission-lease.v1", "ADMISSION_LEASE_JSON_INVALID")
    signal_authority = value.get("signal_authority")
    if type(signal_authority) is not dict or set(signal_authority) != {
        "schema", "identity_handle_sha256", "controller_receipt_sha256"
    } or signal_authority.get("schema") != "samvil.task2-darwin-opaque-process-authority.v1":
        raise AdmissionError("DETACHED_PROCESS_SIGNAL_UNAVAILABLE")
    return value


def parse_observer_bytes(raw: bytes) -> dict[str, object]:
    return _parse_static(raw, "samvil.task2-observer-projection.v1", "OBSERVER_PROJECTION_JSON_INVALID")


def parse_run_envelope_evidence_bytes(raw: bytes) -> dict[str, object]:
    return _parse_static(
        raw,
        "samvil.task2-run-envelope-evidence.v1",
        "RUN_ENVELOPE_EVIDENCE_JSON_INVALID",
    )


def parse_observer_evidence_bytes(raw: bytes) -> dict[str, object]:
    return _parse_static(
        raw,
        "samvil.task2-observer-evidence.v1",
        "OBSERVER_EVIDENCE_JSON_INVALID",
    )
~~~

The production implementation adds every remaining exact field-set, type, length, integer, and digest validation in Task 2. Task 1 already rejects duplicate keys, over-16-KiB documents, depth above 16, integer tokens above 20 digits, floats/constants, invalid Unicode, and all extra raw-PID-style fields inside `signal_authority`. It does not add an authority-acquisition function in this task.

- [ ] **Step 4: Confirm GREEN**

Run the Step 2 command.

Expected: every parser test passes. Label this `PORTABLE CONTRACTS` only.

In the same Task 1 commit, add a required `release-checks.yml` step before the release runner named `Run Task -2 portable admission contracts` that runs exactly `mcp/.venv/bin/python -I -B -m unittest discover -s tools/release-control/tests -p 'test_invocation_admission.py' -v`. It is a CI gate, not an informational artifact; a missing module, collection failure, or nonzero exit blocks the PR. Task 2 changes the same module, so the existing required CI step executes its cross-binding and negative cases without a workflow exception.

- [ ] **Step 5: Freeze the staged candidate**

~~~
task2_git add docs/superpowers/control/2026-08-08-task2-admission-trust-root.md docs/superpowers/specs/2026-08-08-samvil-task2-admission-contract.md tools/release-control/invocation_admission.py tools/release-control/tests/test_invocation_admission.py tools/release-control/tests/fixtures/task2-admission/valid-trust-root.json tools/release-control/tests/fixtures/task2-admission/valid-policy.json tools/release-control/tests/fixtures/task2-admission/valid-lease.json tools/release-control/tests/fixtures/task2-admission/valid-observer.json tools/release-control/tests/fixtures/task2-admission/valid-run-envelope-evidence.json tools/release-control/tests/fixtures/task2-admission/valid-observer-evidence.json tools/release-control/tests/fixtures/task2-admission/duplicate-policy.json tools/release-control/tests/fixtures/task2-admission/raw-pid-lease.json tools/release-control/tests/fixtures/task2-admission/oversized-policy.json tools/release-control/tests/fixtures/task2-admission/deep-policy.json tools/release-control/tests/fixtures/task2-admission/nan-policy.json tools/release-control/tests/fixtures/task2-admission/lone-surrogate-policy.json .github/workflows/release-checks.yml \
  && run_task2_portable /usr/bin/python3 -I -m unittest discover -s tools/release-control/tests -p 'test_invocation_admission.py' -v \
  && verify_task2_commit docs/superpowers/control/2026-08-08-task2-admission-trust-root.md docs/superpowers/specs/2026-08-08-samvil-task2-admission-contract.md tools/release-control/invocation_admission.py tools/release-control/tests/test_invocation_admission.py tools/release-control/tests/fixtures/task2-admission/valid-trust-root.json tools/release-control/tests/fixtures/task2-admission/valid-policy.json tools/release-control/tests/fixtures/task2-admission/valid-lease.json tools/release-control/tests/fixtures/task2-admission/valid-observer.json tools/release-control/tests/fixtures/task2-admission/valid-run-envelope-evidence.json tools/release-control/tests/fixtures/task2-admission/valid-observer-evidence.json tools/release-control/tests/fixtures/task2-admission/duplicate-policy.json tools/release-control/tests/fixtures/task2-admission/raw-pid-lease.json tools/release-control/tests/fixtures/task2-admission/oversized-policy.json tools/release-control/tests/fixtures/task2-admission/deep-policy.json tools/release-control/tests/fixtures/task2-admission/nan-policy.json tools/release-control/tests/fixtures/task2-admission/lone-surrogate-policy.json .github/workflows/release-checks.yml
~~~

Expected: the worktree contains only this exact staged allowlist and has one stable `git write-tree` candidate object. Do not edit, unstage, run another helper, or commit while waiting for trusted control.

- [ ] **Step 6: External attestation handoff**

Outside the repository and without a candidate-supplied tree ID, the external provisioner independently reads the frozen index from the sealed control source, resolves its `git write-tree`, derives its exact base-to-candidate add/modify path-status set, confirms it equals the exact Step 5 allowlist/state, and queues one signed `task2_full_precommit` attestation **and one sealed Task 1 descriptor** bound to the same base commit/tree, candidate index tree, mode `staged`, purpose, and single-use challenge. The descriptor fixes that exact path-status set, target ref, commit subject/body, author/committer identity, expiry, and `task_descriptor_sha256`; the attestation carries that digest. It records both issuance IDs/digests externally. A changed index, different tree, unlisted/missing/renamed/copied/deleted path, descriptor/attestation mismatch, stale provenance, missing private `/tmp`, or any queue ambiguity is a hard stop; the worker must not re-run `add` or ask the repository to mint either record.

- [ ] **Step 7: Snapshot gate and commit**

~~~
task2_full_precommit --staged \
  && task2_commit_snapshot_receipt
~~~

### Task 2: Harden static cross-binding and prove no fixture can authorize execution

Start only after `task2_execution_entry_gate` passes in the clean Task 1 descendant. Because Task 1 committed a new base `HEAD`, the external provisioner must first issue and seal a fresh `samvil.task2-venv-provenance.v1` record/install receipt for this new base commit/tree and unchanged `mcp/pyproject.toml`; a Task 0/1-base provenance record is invalid here. The sandbox attestation is issued only after Step 5 freezes this task's staged candidate tree.

**Files:**

- Modify: `tools/release-control/invocation_admission.py`
- Modify: `tools/release-control/tests/test_invocation_admission.py`

- [ ] **Step 1: Write the failing cross-binding tests**

Add these methods inside the existing `StaticAdmissionTests` class from Task 1:

~~~
    def valid_static_bundle(self) -> admission.StaticAdmissionBundle:
        return admission.validate_static_bundle(
            trusted_root=admission.parse_trust_root_bytes(self.fixture("valid-trust-root.json")),
            policy=admission.parse_policy_bytes(self.fixture("valid-policy.json")),
            lease=admission.parse_lease_bytes(self.fixture("valid-lease.json")),
            observer=admission.parse_observer_bytes(self.fixture("valid-observer.json")),
            run_envelope_evidence=admission.parse_run_envelope_evidence_bytes(
                self.fixture("valid-run-envelope-evidence.json")
            ),
            observer_evidence=admission.parse_observer_evidence_bytes(
                self.fixture("valid-observer-evidence.json")
            ),
            expected_nonce="a" * 64,
            expected_control_commit="b" * 40,
            expected_control_tree="c" * 40,
            expected_now_unix_seconds=1_700_000_001,
        )

    def test_static_bundle_binds_all_stable_identities(self) -> None:
        bundle = self.valid_static_bundle()
        self.assertEqual(bundle.run_id, "fixture-run-a")

    def test_static_bundle_never_becomes_live_authority(self) -> None:
        bundle = self.valid_static_bundle()
        with self.assertRaises(admission.AdmissionError) as raised:
            admission.require_live_authority(bundle)
        self.assertEqual(raised.exception.status, "UNSUPPORTED_INVOCATION_STORAGE_QUOTA")
~~~

Add failure cases for unknown/missing fields, booleans in integer fields, non-lowercase digests, quota below policy minimum or above policy maximum, file-count mismatch, lease expiry, control/nonce/manifest/trust-root mismatch, a policy anchor or controller keyset mismatching `trusted_root`, equal run-envelope/observer anchors, mismatched run-envelope or observer signer, evidence canonical digest mismatch, evidence verification-transcript mismatch, evidence-to-lease/observer projection mismatch, and raw PID/start-time/process-group/polling/signal-name/empty/unknown provider. A byte-identical root-shaped copy is intentionally indistinguishable to this pure static parser and may parse; it must still stop at `UNSUPPORTED_INVOCATION_STORAGE_QUOTA`. Trusted-root provenance and Ed25519 signature verification are tested only by the sealed-descriptor resolver in Task -2B. Same-nonce replay with a different digest is not a pure static validation case: it belongs to the controller-journal integration proof required in Task -2B.

Use these fixed test names, mutation sources, and typed outcomes; every cross-document failure below is `AdmissionError("ADMISSION_BINDING_INVALID")` rather than a live-admission terminal:

| Test method | Exact fixture/mutation | Required status |
| --- | --- | --- |
| `test_policy_parser_rejects_hostile_json` | `duplicate-policy.json`, `oversized-policy.json`, `deep-policy.json`, `nan-policy.json`, `lone-surrogate-policy.json` | `ADMISSION_POLICY_JSON_INVALID` |
| `test_lease_parser_rejects_raw_process_provider` | `raw-pid-lease.json` plus each raw `start_time`, `process_group`, `polling`, `signal_name`, empty, and unknown `signal_authority` provider mutation | `DETACHED_PROCESS_SIGNAL_UNAVAILABLE` |
| `test_bundle_rejects_schema_shape` | deep-copy valid bundle; remove/add one field, put `True` in each integer position, or change a lowercase hex digest to uppercase | `ADMISSION_BINDING_INVALID` |
| `test_bundle_rejects_policy_and_lease_bounds` | quota below/above policy, file-count mismatch, expired lease | `ADMISSION_BINDING_INVALID` |
| `test_bundle_rejects_identity_cross_binding` | nonce/control/manifest/trust-root mismatch, policy-anchor/controller-keyset mismatch, equal anchors, signer mismatch | `ADMISSION_BINDING_INVALID` |
| `test_bundle_rejects_evidence_projection_binding` | alter canonical evidence bytes/digest, verifier-keyset transcript, run-envelope-to-lease field, or observer-to-projection field | `ADMISSION_BINDING_INVALID` |
| `test_static_bundle_never_becomes_live_authority` | unmodified valid static bundle | `UNSUPPORTED_INVOCATION_STORAGE_QUOTA` |

- [ ] **Step 2: Confirm RED**

Run:

~~~
run_task2_portable /usr/bin/python3 -I -m unittest discover -s tools/release-control/tests -p 'test_invocation_admission.py' -v
~~~

Expected: `validate_static_bundle` and `require_live_authority` are missing.

- [ ] **Step 3: Implement exact static binding and a permanent preparation blocker**

Implement these exact names:

| Name | Exact signature or fields | Required result |
| --- | --- | --- |
| `StaticAdmissionBundle` | frozen fields `trust_root_sha256`, `policy_sha256`, `run_envelope_evidence_sha256`, `observer_evidence_sha256`, `run_envelope_verification_transcript_sha256`, `observer_verification_transcript_sha256`, `storage_boundary_sha256`, `signal_authority_sha256`, `normalized_projection_sha256`, `lease_id`, `run_id`, and `observer_id` | Holds only parsed/pinned static identities. |
| `validate_static_bundle` | `(*, trusted_root: dict[str, object], policy: dict[str, object], lease: dict[str, object], observer: dict[str, object], run_envelope_evidence: dict[str, object], observer_evidence: dict[str, object], expected_nonce: str, expected_control_commit: str, expected_control_tree: str, expected_now_unix_seconds: int) -> StaticAdmissionBundle` | Exact-validates the trusted-root-plus-static evidence/projection binding. |
| `require_live_authority` | `(bundle: StaticAdmissionBundle) -> None` | Always raises the current typed quota blocker in this preparation plan. |

`validate_static_bundle` must require exact field sets and canonical hash formats; recompute every Section 4.5 digest; bind policy/trust-root/manifest/control/run/nonce fields across lease, observer, and the two original static evidence records; bind the evidence canonical digests, signer digests, verifier-keyset transcript digests, storage boundary, signal authority, and normalized projection exactly; require the policy's two distinct anchor digests and controller keyset to equal `trusted_root`; compare controller, dedicated UID, quota, file-count, mount identity, boot generation, and opaque signal schema fields; verify the exact normalized projection definition; and reject expiry. Every such semantic/cross-document failure must raise `AdmissionError("ADMISSION_BINDING_INVALID")`. It may require literal `verification_result == "verified"`, but it must label that as untrusted static text and must not attempt to treat it as a signature verdict. The caller may parse a static fixture as `trusted_root` only for portable negative/shape tests. Task -2B accepts the root and original evidence only from sealed trusted-control descriptors and directly verifies their Ed25519 signatures, never from policy/candidate/CLI/environment/path. `require_live_authority` has this complete body:

~~~
def require_live_authority(bundle: StaticAdmissionBundle) -> None:
    del bundle
    raise AdmissionError("UNSUPPORTED_INVOCATION_STORAGE_QUOTA")
~~~

Neither function may open a path, create a directory, connect to a socket, call subprocess, inspect a process, or return a capability that the full gate could consume.

- [ ] **Step 4: Confirm GREEN**

Run the Step 2 command.

Expected: all vectors pass or return a typed blocker. The root-shaped fixture and every positive static fixture still stop at `UNSUPPORTED_INVOCATION_STORAGE_QUOTA`.

- [ ] **Step 5: Freeze the staged candidate**

~~~
task2_git add tools/release-control/invocation_admission.py tools/release-control/tests/test_invocation_admission.py \
  && run_task2_portable /usr/bin/python3 -I -m unittest discover -s tools/release-control/tests -p 'test_invocation_admission.py' -v \
  && verify_task2_commit tools/release-control/invocation_admission.py tools/release-control/tests/test_invocation_admission.py
~~~

Expected: only the two listed files are staged and the external provisioner can independently seal their resulting index tree. The worker leaves the worktree untouched after this point.

- [ ] **Step 6: External attestation handoff**

Outside the repository, trusted control independently resolves the frozen index tree, derives the exact base-to-candidate add/modify path-status set from sealed objects, requires exact equality with the Task 2 descriptor allowlist, and queues exactly one `task2_full_precommit` attestation and one sealed Task 2 descriptor for this same base/tree/mode/purpose/challenge. The descriptor fixes that exact path-status set, target ref, commit subject/body, author/committer identity, expiry, and signed `task_descriptor_sha256`; the attestation binds that digest. It must also verify the fresh Task 2-base venv-provenance record before queueing. Any mismatch, unlisted/missing/renamed/copied/deleted path, expiry, descriptor ambiguity, or inability to materialize the root-owned snapshot is a hard stop.

- [ ] **Step 7: Snapshot gate and commit**

~~~
task2_full_precommit --staged \
  && task2_commit_snapshot_receipt
~~~

### Task 3: Write the external-authority acceptance packet

Start only after `task2_execution_entry_gate` passes in the clean Task 2 descendant. Because Task 2 committed a new base `HEAD`, the external provisioner must first issue and seal a fresh `samvil.task2-venv-provenance.v1` record/install receipt for this new base commit/tree and unchanged `mcp/pyproject.toml`; any older-base record is invalid. The sandbox attestation is issued only after Step 7 freezes this task's staged candidate tree.

**Files:**

- Modify: `docs/superpowers/control/2026-08-08-task2-admission-trust-root.md`
- Create: `docs/superpowers/operations/2026-08-08-task2-admission-provisioner-handoff.md`
- Modify: `docs/superpowers/specs/2026-08-08-samvil-task2-admission-contract.md`
- Create: `tools/release-control/tests/fixtures/task2-admission/channel-contract.v1.json`
- Create: `tools/release-control/tests/test_task2_admission_contract.py`
- Modify: `.github/workflows/release-checks.yml`

- [ ] **Step 1: Write the failing machine-readable contract test**

Create `test_task2_admission_contract.py` using only `hashlib`, `json`, `Path`, and `unittest`. It loads `channel-contract.v1.json`, requires canonical UTF-8 bytes, and asserts these exact fields:

~~~
request_fields = {
  "schema", "request_id", "nonce", "control_commit", "control_tree",
  "manifest_schema", "manifest_sha256", "outer_verifier_assertion_sha256",
  "outer_verifier_assertion_canonical_base64",
  "minimum_quota_bytes", "requested_storage_class", "client_challenge",
  "channel_binding_sha256", "admission_idempotency_key", "semantic_request_sha256"
}
response_fields = {
  "schema", "request_id", "lease_id", "run_id", "nonce", "control_commit",
  "control_tree", "manifest_schema", "manifest_sha256",
  "outer_verifier_assertion_sha256", "policy_sha256", "controller_instance",
  "controller_journal_sequence", "boot_generation", "dedicated_uid", "quota_bytes",
  "file_count_limit", "mount_identity_sha256", "mount_fsid_sha256",
  "lease_root_object_identity_sha256", "storage_boundary_sha256",
  "process_authority_schema", "opaque_process_authority_sha256",
  "run_envelope_evidence_sha256", "run_envelope_signer_sha256",
  "run_envelope_verification_transcript_sha256", "observer_evidence_sha256",
  "observer_signer_sha256", "observer_verification_transcript_sha256",
  "signal_authority_sha256", "normalized_projection_sha256",
  "controller_liveness_nonce", "client_challenge", "channel_binding_sha256",
  "secret_delivery_nonce", "secret_delivery_frame_sha256", "secret_attachment_count",
  "admission_idempotency_key", "semantic_request_sha256", "lease_receipt_sha256",
  "lease_receipt_canonical_base64",
  "issued_unix_seconds", "expires_unix_seconds", "controller_keyset_sha256",
  "controller_signer_key_id", "controller_signature_algorithm",
  "signed_transcript_sha256", "signature_base64", "directory_fd_count"
}
replay_resume_request_fields = {
  "schema", "request_id", "lease_id", "run_id", "controller_instance", "boot_generation",
  "lease_receipt_sha256", "admission_idempotency_key", "semantic_request_sha256",
  "resume_proof", "client_challenge", "channel_binding_sha256"
}
replay_resume_response_fields = {
  "schema", "request_id", "lease_id", "run_id", "controller_instance", "boot_generation",
  "lease_receipt_sha256", "lease_receipt_canonical_base64", "admission_idempotency_key",
  "semantic_request_sha256", "client_challenge", "channel_binding_sha256",
  "issued_unix_seconds", "expires_unix_seconds", "controller_keyset_sha256",
  "controller_signer_key_id", "controller_signature_algorithm", "signed_transcript_sha256",
  "signature_base64", "directory_fd_count", "secret_attachment_count"
}
status_request_fields = {
  "schema", "request_id", "lease_id", "run_id", "controller_instance",
  "boot_generation", "previous_liveness_nonce", "client_challenge",
  "channel_binding_sha256"
}
status_response_fields = {
  "schema", "request_id", "lease_id", "run_id", "controller_instance",
  "boot_generation", "client_challenge", "channel_binding_sha256",
  "controller_liveness_nonce", "status", "issued_unix_seconds",
  "expires_unix_seconds", "controller_keyset_sha256", "controller_signer_key_id",
  "controller_signature_algorithm", "signed_transcript_sha256", "signature_base64"
}
process_request_fields = {
  "schema", "request_id", "operation_id", "lease_id", "run_id", "controller_instance",
  "boot_generation", "operation", "client_challenge", "channel_binding_sha256",
  "required_status_liveness_nonce", "status_response_transcript_sha256",
  "opaque_handle_proof"
}
process_response_fields = {
  "schema", "request_id", "operation_id", "lease_id", "run_id", "controller_instance",
  "boot_generation", "operation", "state", "controller_liveness_nonce",
  "client_challenge", "channel_binding_sha256", "required_status_liveness_nonce",
  "status_response_transcript_sha256", "issued_unix_seconds",
  "expires_unix_seconds", "controller_keyset_sha256", "controller_signer_key_id",
  "controller_signature_algorithm", "signed_transcript_sha256", "signature_base64"
}
secret_delivery_ack_fields = {
  "schema", "request_id", "lease_id", "run_id", "controller_instance", "boot_generation",
  "secret_delivery_nonce", "secret_delivery_frame_sha256", "client_challenge", "channel_binding_sha256"
}
secret_delivery_ack_response_fields = {
  "schema", "request_id", "lease_id", "run_id", "controller_instance", "boot_generation",
  "secret_delivery_nonce", "secret_delivery_frame_sha256", "client_challenge", "channel_binding_sha256",
  "acknowledged_unix_seconds", "expires_unix_seconds", "controller_keyset_sha256",
  "controller_signer_key_id", "controller_signature_algorithm", "signed_transcript_sha256", "signature_base64"
}
client_reject_fields = {
  "schema", "request_id", "lease_id", "run_id", "controller_instance", "boot_generation",
  "admission_response_transcript_sha256", "rejection_class", "client_challenge", "channel_binding_sha256"
}
terminal_response_fields = {
  "schema", "request_id", "request_kind", "outer_terminal", "detail", "controller_instance",
  "boot_generation", "client_challenge", "channel_binding_sha256",
  "directory_fd_count", "secret_attachment_count",
  "issued_unix_seconds", "expires_unix_seconds", "controller_keyset_sha256",
  "controller_signer_key_id", "controller_signature_algorithm",
  "signed_transcript_sha256", "signature_base64"
}
process_operations = {"spawn", "terminate", "reap", "complete"}
process_states = {"issued", "spawned", "termination_requested", "reaped", "completed", "invalidated"}
status_values = {"active"}
terminal_request_kinds = {"admission", "replay_resume", "status", "process", "secret_delivery_ack", "client_reject"}
client_reject_classes = {
  "received_directory_fd_identity_invalid",
  "secret_delivery_frame_missing_or_invalid",
  "unexpected_or_truncated_success_record"
}
outer_verifier_assertion_fields = {
  "schema", "assertion_id", "run_id", "nonce", "control_commit", "control_tree",
  "manifest_schema", "manifest_sha256", "trust_root_sha256", "client_identity_sha256",
  "policy_sha256",
  "issued_unix_seconds", "expires_unix_seconds", "outer_verifier_keyset_sha256",
  "outer_verifier_signer_key_id", "outer_verifier_signature_algorithm",
  "signed_preimage_sha256", "signature_base64"
}
lease_receipt_fields = {
  "schema", "admission_idempotency_key", "semantic_request_sha256", "lease_id",
  "run_id", "nonce", "control_commit", "control_tree", "manifest_schema",
  "manifest_sha256", "outer_verifier_assertion_sha256", "policy_sha256",
  "trust_root_sha256", "controller_instance", "controller_journal_sequence",
  "boot_generation", "dedicated_uid", "quota_bytes", "file_count_limit",
  "mount_identity_sha256", "mount_fsid_sha256", "lease_root_object_identity_sha256",
  "storage_boundary_sha256", "process_authority_schema",
  "opaque_process_authority_sha256", "issued_unix_seconds", "expires_unix_seconds",
  "run_envelope_evidence_sha256", "run_envelope_signer_sha256",
  "run_envelope_verification_transcript_sha256", "observer_evidence_sha256",
  "observer_signer_sha256", "observer_verification_transcript_sha256",
  "signal_authority_sha256", "normalized_projection_sha256",
  "controller_keyset_sha256", "controller_signer_key_id",
  "controller_signature_algorithm", "signed_preimage_sha256", "signature_base64"
}
run_envelope_evidence_fields = {
  "schema", "evidence_id", "run_id", "nonce", "control_commit", "control_tree",
  "manifest_schema", "manifest_sha256", "policy_sha256", "trust_root_sha256",
  "issued_unix_seconds", "expires_unix_seconds", "signer_key_id", "signer_sha256",
  "signature_algorithm", "signed_preimage_sha256", "signature_base64",
  "verifier_keyset_sha256", "verification_result"
}
observer_evidence_fields = {
  "schema", "evidence_id", "observer_id", "run_id", "nonce", "control_commit",
  "control_tree", "policy_sha256", "trust_root_sha256", "storage_boundary_sha256",
  "signal_authority_sha256", "normalized_projection_sha256", "issued_unix_seconds",
  "expires_unix_seconds", "signer_key_id", "signer_sha256", "signature_algorithm",
  "signed_preimage_sha256", "signature_base64", "verifier_keyset_sha256",
  "verification_result"
}
fd_identity_encoding = {
  "lease_root_object_identity_sha256": "sha256(LP(samvil.task2-lease-root-object.v1,u64be(st_dev),u64be(st_ino),u32be(st_mode&S_IFMT)))",
  "mount_fsid_sha256": "sha256(LP(samvil.task2-mount-fsid.v1,u32be(fsid0),u32be(fsid1)))",
  "mount_identity_sha256": "sha256(LP(samvil.task2-apfs-volume.v1,apfs_volume_uuid_raw_16))",
  "received_fd_identity_bytes": "LP(samvil.task2-received-directory-fd-identity.v1,hex32(lease_root_object_identity_sha256),hex32(mount_fsid_sha256),hex32(mount_identity_sha256))"
}
channel_record_framing = {
  "transport": "AF_UNIX_SOCK_SEQPACKET",
  "canonical_json_max_bytes": 16384,
  "initial_admission_success_sequence": "response-json-plus-exactly-one-SCM_RIGHTS-directory-fd-then-one-secret-delivery-binary-record-without-ancillary-then-client-ack-json-without-ancillary-then-signed-ack-response-json-without-ancillary",
  "replay_resume_success_sequence": "one-signed-replay-resume-response-json-record-with-zero-rights-fds-and-zero-secret-attachments",
  "success_ancillary": "exactly-one-SCM_RIGHTS-containing-one-directory-fd-in-response-record-only",
  "secret_delivery_ancillary": "none",
  "reject_flags": "MSG_CTRUNC-or-MSG_TRUNC",
  "reject_ancillary": "unknown-cmsg-or-not-exactly-one-rights-fd",
  "reject_action": "close-all-received-fds-close-channel-no-fd-no-secret",
  "unsupported_transport": "blocked_environment_admission_recovery_required"
}
secret_delivery_frame_encoding = {
  "record_type": "binary-lp-v1",
  "bytes": "LP(samvil.task2-admission-secret-delivery.v1,hex32(sha256(utf8(lease_id))),hex32(sha256(utf8(run_id))),hex32(controller_instance),hex32(boot_generation),hex32(secret_delivery_nonce),hex32(channel_binding_sha256),raw32(handle_secret))",
  "fixed_length_bytes": 297,
  "digest": "sha256(exact-frame-bytes)-equals-response-secret_delivery_frame_sha256",
  "sequence": "one-record-after-verified-response-before-ack-no-ancillary-no-json-no-extra-record"
}
denial_transport = {
  "preauthenticated_malformed_record": "close-channel-without-response-fd-or-secret",
  "authenticated_denial": "signed-terminal-response-with-zero-rights-fds-and-zero-secret-attachments",
  "nonactive_status": "authenticated_denial_admission_recovery_required",
  "client_reject": "correlated-client-reject-record-atomic-revoke-then-signed-terminal-or-local-close-and-deadline-revocation",
  "terminal_response_schema": "samvil.task2-admission-terminal-response.v1"
}
response_verification = {
  "admission": "sealed-keyset-signature-request-id-client-challenge-channel-lease-instance-boot-expiry-receipt-evidence-fd-secret-frame",
  "replay_resume": "sealed-keyset-signature-request-id-client-challenge-channel-lease-run-instance-boot-byte-identical-receipt-resume-proof-zero-fd-zero-secret-expiry",
  "status": "sealed-keyset-signature-request-id-client-challenge-channel-lease-run-instance-boot-status-expiry",
  "process": "sealed-keyset-signature-request-id-operation-id-client-challenge-channel-lease-run-instance-boot-state-status-proof-expiry",
  "secret_delivery_ack": "sealed-keyset-signature-request-id-secret-nonce-frame-digest-client-challenge-channel-lease-run-instance-boot-expiry",
  "terminal": "sealed-keyset-signature-request-id-request-kind-client-challenge-channel-instance-boot-expiry-zero-fd-zero-secret"
}
channel_binding_encoding = "sha256(LP(samvil.task2-controller-channel-binding.v1, client_identity, controller_peer_identity, controller_instance, boot_generation, server_connection_nonce, client_connection_nonce))"
process_status_binding = {
  "required_status_liveness_nonce": "latest-unexpired-single-use-same-lease-run-instance-boot-peer-channel",
  "status_response_transcript_sha256": "signed-status-response-for-required-nonce"
}
process_state_transitions = {
  "issued": "spawned", "spawned": "termination_requested",
  "termination_requested": "reaped", "reaped": "completed",
  "any_nonterminal_fault": "invalidated"
}
admission_idempotency = {
  "key": "sha256(LP(samvil.task2-admission-idempotency.v1,hex32(outer_assertion_sha256),native_client_identity_bytes,hex32(nonce),hex20(control_commit),hex20(control_tree),hex32(manifest_sha256)))",
  "semantic_request": "canonical-admission-request-minus-request_id-client_challenge-channel_binding_sha256-admission_idempotency_key-semantic_request_sha256",
  "first_attempt": "durable-intent-before-authority-side-effect-durable-result-before-response",
  "same_key_same_semantic": "initial-four-record-success-exactly-once-then-only-same-native-client-resume-proof-with-byte-identical-cached-lease-receipt-and-zero-fd-zero-secret",
  "recovery_or_delivery_failure": "durable-invalidate-idempotent-revoke-unmount-zeroize-no-fd-no-secret-admission_recovery_required",
  "same_nonce_or_key_changed_semantic": "admission_recovery_required-no-new-authority-event"
}
lease_receipt_binding = {
  "unsigned_fields": "full-fields-minus-signed_preimage_sha256-minus-signature_base64",
  "signature_preimage": "LP(samvil.task2-lease-receipt-signature.v1,canonical-unsigned-lease-receipt-bytes)",
  "signature_verification": "ed25519-sealed-controller-keyset-key-id-algorithm",
  "canonical_base64": "RFC4648-standard-alphabet-padding-required-reencode-equal",
  "response_digest": "response.lease_receipt_sha256-equals-sha256(decoded-canonical-base64)",
  "response_copy": "every-overlapping-response-and-receipt-field-exact-equal"
}
signature_encoding = {
  "canonical_json": "utf8-json-sort-keys-separators-comma-colon-ensure-ascii-false",
  "assertion_unsigned_fields": "full-fields-minus-signed_preimage_sha256-minus-signature_base64",
  "evidence_unsigned_fields": "full-fields-minus-signed_preimage_sha256-minus-signature_base64",
  "lease_receipt_unsigned_fields": "full-fields-minus-signed_preimage_sha256-minus-signature_base64",
  "response_unsigned_fields": "full-fields-minus-signed_transcript_sha256-minus-signature_base64",
  "outer_verifier_assertion_signature_domain": "samvil.task2-outer-verifier-assertion-signature.v1",
  "run_envelope_evidence_signature_domain": "samvil.task2-run-envelope-evidence-signature.v1",
  "observer_evidence_signature_domain": "samvil.task2-observer-evidence-signature.v1",
  "lease_receipt_signature_domain": "samvil.task2-lease-receipt-signature.v1",
  "response_signature_domain": "samvil.task2-admission-response-signature.v1",
  "replay_resume_response_signature_domain": "samvil.task2-admission-replay-resume-response-signature.v1",
  "secret_delivery_ack_response_signature_domain": "samvil.task2-admission-secret-delivery-ack-response-signature.v1",
  "terminal_response_signature_domain": "samvil.task2-admission-terminal-response-signature.v1",
  "status_response_signature_domain": "samvil.task2-status-response-signature.v1",
  "process_response_signature_domain": "samvil.task2-process-response-signature.v1",
  "base64": "RFC4648-standard-alphabet-padding-required-reencode-equal"
}
schema_values = {
  "request": "samvil.task2-admission-channel-request.v1",
  "response": "samvil.task2-admission-channel-response.v1",
  "replay_resume_request": "samvil.task2-admission-replay-resume-request.v1",
  "replay_resume_response": "samvil.task2-admission-replay-resume-response.v1",
  "secret_delivery_ack": "samvil.task2-admission-secret-delivery-ack.v1",
  "secret_delivery_ack_response": "samvil.task2-admission-secret-delivery-ack-response.v1",
  "client_reject": "samvil.task2-admission-client-reject.v1",
  "terminal_response": "samvil.task2-admission-terminal-response.v1",
  "status_request": "samvil.task2-admission-status-request.v1",
  "status_response": "samvil.task2-admission-status-response.v1",
  "process_request": "samvil.task2-admission-process-request.v1",
  "process_response": "samvil.task2-admission-process-response.v1",
  "outer_verifier_assertion": "samvil.task2-outer-verifier-assertion.v1",
  "lease_receipt": "samvil.task2-lease-receipt.v1",
  "run_envelope_evidence": "samvil.task2-run-envelope-evidence.v1",
  "observer_evidence": "samvil.task2-observer-evidence.v1"
}
terminal_detail_mapping = {
  "quota_or_fd_identity": "UNSUPPORTED_INVOCATION_STORAGE_QUOTA",
  "opaque_handle_or_process_state": "DETACHED_PROCESS_SIGNAL_UNAVAILABLE",
  "assertion_signature_channel_status_or_controller_recovery": "ADMISSION_RECOVERY_REQUIRED"
}
client_reject_detail_mapping = {
  "received_directory_fd_identity_invalid": "UNSUPPORTED_INVOCATION_STORAGE_QUOTA",
  "secret_delivery_frame_missing_or_invalid": "ADMISSION_RECOVERY_REQUIRED",
  "unexpected_or_truncated_success_record": "ADMISSION_RECOVERY_REQUIRED"
}
terminal_object_fields = {"fields", "schema", "outer_terminal", "details"}
terminal_details = {
  "UNSUPPORTED_INVOCATION_STORAGE_QUOTA",
  "DETACHED_PROCESS_SIGNAL_UNAVAILABLE",
  "ADMISSION_RECOVERY_REQUIRED"
}
~~~

The fixture's top level is exactly `schema`, `request_fields`, `response_fields`, `replay_resume_request_fields`, `replay_resume_response_fields`, `status_request_fields`, `status_response_fields`, `process_request_fields`, `process_response_fields`, `secret_delivery_ack_fields`, `secret_delivery_ack_response_fields`, `client_reject_fields`, `terminal_response_fields`, `process_operations`, `process_states`, `status_values`, `terminal_request_kinds`, `client_reject_classes`, `outer_verifier_assertion_fields`, `lease_receipt_fields`, `run_envelope_evidence_fields`, `observer_evidence_fields`, `fd_identity_encoding`, `channel_record_framing`, `secret_delivery_frame_encoding`, `denial_transport`, `response_verification`, `channel_binding_encoding`, `process_status_binding`, `process_state_transitions`, `admission_idempotency`, `lease_receipt_binding`, `signature_encoding`, `schema_values`, `terminal_detail_mapping`, `client_reject_detail_mapping`, and `terminal`. Its `terminal` object has exactly `terminal_object_fields`, `schema == "samvil.task2-admission-terminal.v1"`, `outer_terminal == "BLOCKED_ENVIRONMENT"`, and `details == terminal_details`; both terminal mappings must be exactly as above. The test also requires initial `directory_fd_count == 1` and `secret_attachment_count == 1`, replay `directory_fd_count == 0` and `secret_attachment_count == 0`, `manifest_schema == "samvil.full-gate-manifest.v2"`, and a literal `channel_contract_sha256 = <sha256 of canonical fixture bytes>` in the handoff document. It rejects any field name/value containing raw PID, start-time, process-group, polling, signal-name, or a path. It verifies the exact outer-verifier assertion, lease receipt and response-copy/digest/signature/evidence-projection bindings, run-envelope/observer evidence, FD-identity/channel-binding and received-FD-transcript encoding, the exact initial four-record success/ACK sequence and separate capability-proven replay-resume sequence, exact packet framing/ancillary rejection/FD-close behavior, all response-verification fields, signed zero-FD denial transport, signature encoding, admission idempotency and delivery-ack recovery, status-proof/process-state rules, process-command, and process-response field sets listed in Step 4. It must table-drive all three post-auth denial classes (`quota_or_fd_identity`, `opaque_handle_or_process_state`, and `assertion_signature_channel_status_or_controller_recovery`) plus every `client_reject_class`, prove each exact correlated request ID/kind/detail, signed terminal shape, zero FD, and zero secret fields, and prove that an unsent client rejection follows the deadline-revocation rule; native socket behavior itself remains a Task -2B integration proof. The trust-root document declares the fixture only a portable test vector.

- [ ] **Step 2: Confirm RED**

Run:

~~~
run_task2_portable /usr/bin/python3 -I -m unittest discover -s tools/release-control/tests -p 'test_task2_admission_contract.py' -v
~~~

Expected: collection fails because the contract fixture and handoff document do not exist.

- [ ] **Step 3: Record the immutable external requirements**

The handoff document requires all of these deliverables before Task -2B can be planned:

1. A disposable darwin-arm64 VM with recorded OS build and boot generation.
2. A dedicated non-admin canary UID with interactive login, user launchd domain, remote login, cron/at, unrelated launch agents, and background updater admission denied.
3. A root-owned persistent controller whose boot/recovery default is deny-all and whose durable journal records lease epoch, controller instance, boot generation, allowed executable identity, one verifier-supervised process tree, every request ID/schema/digest, secret-ACK outcome, and a root-owned trusted-clock deadline. Before any FD or secret leaves the controller, that deadline is durably armed. It expires the lease without a later client call by invalidating/revoking/zeroizing, quiescing the root-supervised native client through an opaque capability, obtaining its signed FD-close proof, and only then unmounting; if quiesce, FD-close proof, or unmount is ambiguous, it quarantines/destroys the disposable boundary and reports no PASS.
4. A per-invocation APFS volume or equivalent kernel-enforced filesystem boundary with fixed byte quota, fixed file-count quota, mount FSID/UUID, exclusive-writer proof, and cleanup/unmount contract.
5. A sealed outer-verifier descriptor that pins the canonical trusted-root digest before candidate resolution, an immutable root-owned controller keyset whose digest equals that root's `controller_keyset_sha256`, and an immutable outer-verifier keyset whose digest equals that root's `outer_verifier_keyset_sha256`. The run-envelope and observer anchors are distinct; policy names no key, selects no algorithm, and may only match the descriptor.
6. A canonical signed outer-verifier assertion binding run ID, nonce, control commit/tree, v2 manifest digest, trusted-root digest, policy digest, expiry, and authenticated native-client identity. The controller directly verifies its key ID, algorithm, canonical preimage, signature, keyset, bindings, and expiry before creating a lease; a client-supplied hash alone is never evidence.
7. Canonical signed run-envelope and independent-observer evidence records, each with artifact digest, run ID, nonce, control commit/tree, policy/trust-root digest, signer key ID, signer digest, signature algorithm, canonical signed-preimage digest, signature, issued/expiry time, verifier keyset digest, and `verification_result == "verified"`. The controller or independent verifier validates each original record against its sealed anchor before its projection is placed in a v2 receipt or sidecar; Task 2's static strings are projections only, never a signature verdict.
8. A reviewed native client protocol with authenticated controller peer identity, `AF_UNIX` `SOCK_SEQPACKET` availability proof, exact four-record admission success sequence (signed JSON plus one directory FD, one fixed binary secret frame with no ancillary, canonical client ACK, then signed ACK response), and a distinct same-capability replay-resume sequence (one signed zero-FD/zero-secret response only), with fresh globally unique request ID/challenge for every call. It must prove `MSG_CTRUNC`/`MSG_TRUNC`/unknown-or-extra ancillary rejection, all received-FD closure, secret-frame no-ancillary/length/digest/sequence rejection and zeroization, replay resume-proof verification/no-redelivery, correlated client-reject-to-terminal handling, and no stream/path fallback. The directory FD is held only by that root-supervised native client, never candidate code or a general Python process; candidate code receives neither `SCM_RIGHTS` nor a raw mount path.
9. A reviewed opaque process capability for spawn, terminate, reap, and complete. The darwin path may not call `subprocess.Popen`, `os.kill`, `os.killpg`, raw PID, PID/start time, process group, polling, or signal-by-name after authority acquisition.
10. Machine-verifiable fault evidence for quota exhaustion, file-count exhaustion, detached descendant, held descriptor, timeout, receipt-close failure, observer verification/expiry after allocation, controller death, parent death, IPC loss, replay, reboot recovery, and a client that stops immediately after receiving the FD or secret. The deadline owner must prove that last case reaches durable revocation, native-client quiesce/FD-close proof, unmount or VM quarantine, and zero FD/secret/PASS without relying on a later status/process call.
11. A native-client FD proof that exactly one `SCM_RIGHTS` directory FD is received in one verified record, has `FD_CLOEXEC`, is an `S_IFDIR`, and has signed lease-root object identity plus current mount UUID/FSID matching the response before use; it includes the exact three-hash aggregate transcript bytes and all rejection-close proofs.
12. A machine-verifiable denial proof that any foreign/stale/duplicate descriptor, signer, channel, controller instance, boot generation, handle, status challenge, process operation, secret frame/ACK, client rejection, or expired lease fails closed through the signed zero-FD/zero-secret terminal envelope (or the pre-auth silent-close rule) without a PID-bearing message or PASS.

- [ ] **Step 4: Define the required native request/response and capability lifecycle**

The native client sends exactly:

~~~
{
  "schema": "samvil.task2-admission-channel-request.v1",
  "request_id": "64 lowercase hex",
  "nonce": "64 lowercase hex",
  "control_commit": "40 lowercase hex",
  "control_tree": "40 lowercase hex",
  "manifest_schema": "samvil.full-gate-manifest.v2",
  "manifest_sha256": "64 lowercase hex",
  "outer_verifier_assertion_sha256": "64 lowercase hex",
  "outer_verifier_assertion_canonical_base64": "base64 canonical JSON bytes",
  "minimum_quota_bytes": 1,
  "requested_storage_class": "invocation_exclusive_kernel_quota",
  "client_challenge": "64 lowercase hex",
  "channel_binding_sha256": "64 lowercase hex",
  "admission_idempotency_key": "64 lowercase hex",
  "semantic_request_sha256": "64 lowercase hex"
}
~~~

`semantic_request_bytes` is the canonical JSON bytes of the exact admission request after removing only `request_id`, `client_challenge`, `channel_binding_sha256`, `admission_idempotency_key`, and `semantic_request_sha256`. `semantic_request_sha256` is `sha256(semantic_request_bytes)`. `admission_idempotency_key` is independently `sha256(LP("samvil.task2-admission-idempotency.v1", hex32(outer_verifier_assertion_sha256), authenticated native-client identity bytes, hex32(nonce), hex20(control_commit), hex20(control_tree), hex32(manifest_sha256)))`. The controller recomputes both values rather than trusting either client field; any mismatch is `BLOCKED_ENVIRONMENT / ADMISSION_RECOVERY_REQUIRED` before a lease mutation. Excluding both derived request fields prevents a self-referential hash while preserving request identity across a new transport request ID, client challenge, or connection binding.

Before requesting any quota, mount, lease, or handle authority, the controller durably writes one `ADMISSION_INTENT` keyed by `(admission_idempotency_key, nonce, semantic_request_sha256)` and supplies the idempotency key to the root authority controller. That external controller must enforce one authority event ID for the key. After it obtains the authority result, the admission controller durably writes one `ADMISSION_RESULT` containing that event ID, the issuing controller instance/boot generation, and the exact signed canonical lease-receipt bytes before emitting the one initial four-record transport sequence. If recovery finds an intent without a result, it may only ask the root authority controller for the existing result by the same idempotency key; it may not issue a second authority request. A missing, conflicting, or unverifiable recovery result is `BLOCKED_ENVIRONMENT / ADMISSION_RECOVERY_REQUIRED`, with no new event. A cached result may be observed again only through the separately defined replay-resume request from the same native client that proves possession of the original capability; it requires unchanged controller instance/boot, active unexpired lease, root authority verification of the same event ID/FD boundary, and the durable secret-delivery ACK, and it returns a zero-FD/zero-secret signed wrapper with the byte-identical stored receipt. On a crash/reboot, instance/boot mismatch, expired or unacked lease, secret-store loss, missing FD proof, uncertain root-authority lookup, or missing resume proof, the controller durably marks the result invalidated, idempotently revokes/quiesces the authority event and unmounts-or-quarantines its resources, zeroizes secrets, sends no FD or secret, and returns `BLOCKED_ENVIRONMENT / ADMISSION_RECOVERY_REQUIRED`. A different semantic digest under an existing nonce or key is rejected before authority allocation.

The embedded outer-verifier assertion is canonical UTF-8 JSON with exactly `schema == "samvil.task2-outer-verifier-assertion.v1"`, `assertion_id`, `run_id`, `nonce`, `control_commit`, `control_tree`, `manifest_schema == "samvil.full-gate-manifest.v2"`, `manifest_sha256`, `trust_root_sha256`, `client_identity_sha256`, `policy_sha256`, `issued_unix_seconds`, `expires_unix_seconds`, `outer_verifier_keyset_sha256`, `outer_verifier_signer_key_id`, `outer_verifier_signature_algorithm == "ed25519"`, `signed_preimage_sha256`, and `signature_base64`. Its canonical unsigned bytes are the exact full object minus `signed_preimage_sha256` and `signature_base64`; its unsigned preimage is `LP("samvil.task2-outer-verifier-assertion-signature.v1", canonical unsigned assertion bytes)` where `LP` is a concatenation of each item as an unsigned 32-bit big-endian byte length followed by the item bytes. `signed_preimage_sha256` is the digest of that preimage. Every `signature_base64` and `outer_verifier_assertion_canonical_base64` uses RFC 4648 standard alphabet with required padding and must equal its decode/re-encode canonical form. The controller recomputes the assertion digest and preimage, verifies the signature/key ID against the sealed outer-verifier keyset, compares its run ID/nonce/control/manifest/trust-root/policy/expiry values against the independently verified run envelope and sealed policy descriptor, compares `client_identity_sha256` against the authenticated native peer, and rejects before any lease mutation on any mismatch.

The original run-envelope evidence is canonical UTF-8 JSON with exactly `schema == "samvil.task2-run-envelope-evidence.v1"` and `run_envelope_evidence_fields`; its canonical unsigned bytes are full fields minus `signed_preimage_sha256` and `signature_base64`, and its unsigned preimage is `LP("samvil.task2-run-envelope-evidence-signature.v1", canonical unsigned evidence bytes)`. The original independent-observer evidence is canonical UTF-8 JSON with exactly `schema == "samvil.task2-observer-evidence.v1"` and `observer_evidence_fields`; its canonical unsigned bytes are full fields minus `signed_preimage_sha256` and `signature_base64`, and its unsigned preimage is `LP("samvil.task2-observer-evidence-signature.v1", canonical unsigned evidence bytes)`. For both, `signature_algorithm` is exactly `ed25519`, `verification_result` is exactly `verified`, `signed_preimage_sha256` is the digest of the stated preimage, and `signature_base64` uses the stated canonical RFC 4648 form. The controller or independent verifier recomputes canonical bytes/preimage, verifies signature/key ID/keyset/expiry against the corresponding sealed root anchor, and binds run envelope to the outer assertion's nonce/control/manifest/policy/trust-root fields and observer to lease run/nonce/control/policy/trust-root/storage/signal/normalized-projection fields. A projection hash that is not backed by this exact original evidence is rejected.

The controller computes `run_envelope_evidence_sha256 = sha256(canonical original run-envelope bytes)` and requires it to equal `lease.run_envelope_sha256`; it also requires `lease.run_envelope_signer_sha256 == run_envelope_evidence.signer_sha256` and `lease.run_envelope_verification_transcript_sha256 == sha256(LP("samvil.task2-run-envelope-verification.v1", hex32(run_envelope_evidence_sha256), hex32(sealed run-envelope anchor), hex32(run_envelope_evidence.verifier_keyset_sha256), b"verified"))`. Before authority allocation it directly compares the run envelope's run ID, nonce, control commit/tree, manifest schema/digest, policy digest, and trust-root digest to the outer assertion and sealed policy descriptor; after authority allocation it requires the issued lease to carry the exact same values. The independent verifier computes `observer_evidence_sha256 = sha256(canonical original observer bytes)` and requires it to equal `observer.observer_evidence_sha256`; it also requires the signer/transcript equations from Section 4.5 and exact equality of observer evidence run/nonce/control/policy/trust-root/storage/signal/normalized fields to the lease/observer projection before receipt or sidecar publication. The run-envelope proof must be valid before authority allocation; the observer proof must be valid before receipt/sidecar publication. A run-envelope mismatch before allocation prevents an authority event. An observer mismatch, expiry, or verification failure after allocation but before publication durably invalidates the result, idempotently revokes/quiesces the authority event, unmounts/closes every FD, zeroizes the secret, publishes no receipt/sidecar/FD/secret, and returns `BLOCKED_ENVIRONMENT / ADMISSION_RECOVERY_REQUIRED`. No digest, signer, keyset, transcript, signature, expiry, or projection mismatch can be repaired by a fixture or a client hash string.

`channel_binding_sha256` is never accepted as a client echo. During the root-owned native transport handshake, both peers independently derive it as `sha256(LP("samvil.task2-controller-channel-binding.v1", authenticated native-client identity bytes, controller peer-identity digest bytes, controller instance bytes, boot-generation bytes, server connection nonce bytes, client connection nonce bytes))`. The controller generates the server nonce, the client generates the client nonce, both are unique to one authenticated connection and never appear in candidate data, and the controller compares its own derivation on every admission, status, process, secret-ACK, and client-reject operation. Every `request_id` is 64 lowercase hex and globally unique for its controller instance/boot and authenticated client; the controller durably binds it to exactly one request schema and canonical request digest and rejects a duplicate or an ID reused with changed bytes. Any handshake, peer-identity, nonce, request-ID, or binding mismatch maps through `terminal_detail_mapping` without a lease mutation.

The native protocol uses only an authenticated `AF_UNIX` `SOCK_SEQPACKET` channel; the external packet must prove that exact transport is available, and there is no `SOCK_STREAM`, path, polling, or framing fallback. Every record is at most 16,384 bytes. The only successful admission sequence is exactly four records on one authenticated channel: (1) canonical signed response JSON with exactly one `SCM_RIGHTS` control message containing exactly one directory FD in that same record; (2) exactly one binary secret-delivery frame, without any ancillary data; (3) canonical client secret-ACK JSON, without ancillary data; (4) canonical signed ACK-response JSON, without ancillary data. No status/process request is accepted until record 4 verifies, and the channel closes before a second success sequence or a duplicate secret frame can arrive. `MSG_CTRUNC`, `MSG_TRUNC`, an unknown ancillary message, more/fewer than one received right, malformed/noncanonical/oversized JSON, an unexpected binary record, a secret-frame ancillary message, or a record-boundary/sequence violation is a rejection. Before returning from any client-side rejection, the native client enumerates every descriptor present in all received ancillary data and closes all of them, zeroizes any secret bytes, and either sends the correlated client-reject record below or closes the channel; it never retains or publishes a partially verified FD. The controller likewise sends no descriptor or secret on a rejection. A malformed record before transport authentication is a silent close with no response; an authenticated rejection uses the signed zero-FD terminal envelope below.

The controller returns the following canonical JSON response plus exactly one `SCM_RIGHTS` directory descriptor. `received-FD identity bytes` in its transcript are exactly `LP("samvil.task2-received-directory-fd-identity.v1", hex32(lease_root_object_identity_sha256), hex32(mount_fsid_sha256), hex32(mount_identity_sha256))`, with all three hashes recomputed from the held received FD as specified below. Its canonical unsigned response bytes are full response fields minus `signed_transcript_sha256` and `signature_base64`; `signed_transcript_sha256` is the digest of the exact `LP("samvil.task2-admission-response-signature.v1", canonical request bytes, authenticated peer identity bytes, channel binding bytes, canonical unsigned response bytes, received-FD identity bytes)`, and `signature_base64` is canonical RFC 4648. The client verifies the signer key ID/algorithm against the sealed root-owned keyset, the signature, request ID, challenge, channel binding, lease expiry, controller instance, boot generation, evidence commitments, every exact response/receipt overlap, `directory_fd_count == 1`, `secret_attachment_count == 1`, the signed `secret_delivery_frame_sha256`, and all three FD-derived hashes before it treats the descriptor as held-but-not-yet-usable.

~~~
{
  "schema": "samvil.task2-admission-channel-response.v1",
  "request_id": "64 lowercase hex",
  "lease_id": "lowercase-hyphenated-id",
  "run_id": "lowercase-hyphenated-id",
  "nonce": "64 lowercase hex",
  "control_commit": "40 lowercase hex",
  "control_tree": "40 lowercase hex",
  "manifest_schema": "samvil.full-gate-manifest.v2",
  "manifest_sha256": "64 lowercase hex",
  "outer_verifier_assertion_sha256": "64 lowercase hex",
  "policy_sha256": "64 lowercase hex",
  "controller_instance": "64 lowercase hex",
  "controller_journal_sequence": 1,
  "boot_generation": "64 lowercase hex",
  "dedicated_uid": 501,
  "quota_bytes": 1,
  "file_count_limit": 1,
  "mount_identity_sha256": "64 lowercase hex",
  "mount_fsid_sha256": "64 lowercase hex",
  "lease_root_object_identity_sha256": "64 lowercase hex",
  "storage_boundary_sha256": "64 lowercase hex",
  "process_authority_schema": "samvil.task2-darwin-opaque-process-authority.v1",
  "opaque_process_authority_sha256": "64 lowercase hex",
  "run_envelope_evidence_sha256": "64 lowercase hex",
  "run_envelope_signer_sha256": "64 lowercase hex",
  "run_envelope_verification_transcript_sha256": "64 lowercase hex",
  "observer_evidence_sha256": "64 lowercase hex",
  "observer_signer_sha256": "64 lowercase hex",
  "observer_verification_transcript_sha256": "64 lowercase hex",
  "signal_authority_sha256": "64 lowercase hex",
  "normalized_projection_sha256": "64 lowercase hex",
  "controller_liveness_nonce": "64 lowercase hex",
  "client_challenge": "64 lowercase hex",
  "channel_binding_sha256": "64 lowercase hex",
  "secret_delivery_nonce": "64 lowercase hex",
  "secret_delivery_frame_sha256": "64 lowercase hex",
  "secret_attachment_count": 1,
  "admission_idempotency_key": "64 lowercase hex",
  "semantic_request_sha256": "64 lowercase hex",
  "lease_receipt_sha256": "64 lowercase hex",
  "lease_receipt_canonical_base64": "base64 canonical JSON bytes",
  "issued_unix_seconds": 1,
  "expires_unix_seconds": 2,
  "controller_keyset_sha256": "64 lowercase hex",
  "controller_signer_key_id": "lowercase-hyphenated-id",
  "controller_signature_algorithm": "ed25519",
  "signed_transcript_sha256": "64 lowercase hex",
  "signature_base64": "base64",
  "directory_fd_count": 1
}
~~~

Every authenticated denial has exactly `schema == "samvil.task2-admission-terminal-response.v1"` and `terminal_response_fields`, with `request_id` and `request_kind` equal to the rejected durable request, `outer_terminal == "BLOCKED_ENVIRONMENT"`, `detail` one of `terminal_details`, `directory_fd_count == 0`, and `secret_attachment_count == 0`. Its canonical unsigned bytes are the full terminal object minus `signed_transcript_sha256` and `signature_base64`; `signed_transcript_sha256` is `sha256(LP("samvil.task2-admission-terminal-response-signature.v1", canonical rejected request bytes, authenticated peer identity bytes, channel binding bytes, canonical unsigned terminal bytes))`. The client verifies the sealed controller keyset/key ID/algorithm, signature, request ID/kind, client challenge, channel binding, controller instance/boot, expiry, outer terminal, detail, and the zero-FD/zero-secret counts. No admission, status, process, secret-ACK, client-reject, FD, evidence, or recovery rejection may serialize a different terminal shape. Pre-auth malformed records remain the single stated silent-close exception and never carry a descriptor or secret.

`lease_receipt_canonical_base64` must decode and canonical re-encode to exactly one `schema == "samvil.task2-lease-receipt.v1"` object with exactly `lease_receipt_fields`. Its canonical unsigned bytes are the full receipt object minus `signed_preimage_sha256` and `signature_base64`; `signed_preimage_sha256` is `sha256(LP("samvil.task2-lease-receipt-signature.v1", canonical unsigned lease-receipt bytes))`. `signature_base64` is a canonical RFC 4648 Ed25519 signature verified with the receipt's `controller_keyset_sha256`, `controller_signer_key_id`, and `controller_signature_algorithm` against the sealed root-owned controller keyset. The client computes `sha256(decoded canonical lease-receipt bytes)` and requires it to equal `lease_receipt_sha256`; every response field shared with the receipt (including idempotency/semantic digests, lease/run/nonce/control/manifest/outer-assertion/policy, controller/boot/quota/mount/process, issued/expiry, and controller signer fields) must be byte-for-byte equal. It verifies the receipt before accepting the initial response signature or descriptor. The durable `ADMISSION_RESULT` retains those exact signed receipt bytes, not a mutable decoded model, so only the separately defined zero-FD/zero-secret replay-resume response may return the authoritative receipt byte-identically under a new request ID/challenge/channel binding.

The initial admission request is never re-run as a second success sequence. Only after the initial four-record sequence has a durable verified ACK, the same root-supervised native client that still holds the already verified FD and secret may open a new authenticated channel and send exactly `schema == "samvil.task2-admission-replay-resume-request.v1"` with `replay_resume_request_fields`. Its `resume_proof` is lowercase-hex `HMAC-SHA256(handle_secret, LP("samvil.task2-admission-replay-resume-proof.v1", utf8(lease_id), utf8(run_id), hex32(controller_instance), hex32(boot_generation), hex32(lease_receipt_sha256), hex32(request_id), hex32(client_challenge), hex32(channel_binding_sha256)))`. The controller compares it in constant time and requires the same live controller instance/boot, active unexpired lease, original root authority event/FD proof, durable ACK, matching idempotency/semantic digests, and the native client's authenticated identity before replying. It sends exactly one canonical signed `schema == "samvil.task2-admission-replay-resume-response.v1"` record with `replay_resume_response_fields`, `directory_fd_count == 0`, and `secret_attachment_count == 0`, with no ancillary data; its transcript is `sha256(LP("samvil.task2-admission-replay-resume-response-signature.v1", canonical resume request bytes, authenticated peer identity bytes, channel binding bytes, canonical unsigned resume response bytes))`. The response's receipt bytes/digest must be byte-identical to the stored authoritative receipt, while only the wrapper request ID/challenge/channel binding/signature are new. The client verifies the new signature and that it still holds the matching pre-existing capability; it never expects a new FD, frame, ACK, or raw secret. Missing/invalid/foreign proof, lost local capability, stale instance/boot, expiry, ACK loss, root event/FD uncertainty, or a resume response with any FD/secret causes durable revoke/quiesce/unmount-or-quarantine/zeroization and the exact `ADMISSION_RECOVERY_REQUIRED` terminal for `request_kind == "replay_resume"`; it never falls back to a second admission or secret delivery.

The native status request has exactly `schema == "samvil.task2-admission-status-request.v1"`, `request_id`, `lease_id`, `run_id`, `controller_instance`, `boot_generation`, `previous_liveness_nonce`, `client_challenge`, and `channel_binding_sha256`; its status response has exactly `schema == "samvil.task2-admission-status-response.v1"`, `request_id`, `lease_id`, `run_id`, `controller_instance`, `boot_generation`, `client_challenge`, `channel_binding_sha256`, `controller_liveness_nonce`, `status`, `issued_unix_seconds`, `expires_unix_seconds`, `controller_keyset_sha256`, `controller_signer_key_id`, `controller_signature_algorithm`, `signed_transcript_sha256`, and `signature_base64`. `status` must be exactly `active`; any other value is a fail-closed admission detail. Its canonical unsigned response bytes are full status-response fields minus `signed_transcript_sha256` and `signature_base64`; its `signed_transcript_sha256` is the digest of `LP("samvil.task2-status-response-signature.v1", canonical status-request bytes, previous liveness nonce bytes, authenticated peer identity bytes, channel binding bytes, canonical unsigned status-response bytes)`, and `signature_base64` is canonical RFC 4648. Every status call uses a new client challenge and must produce a new signed liveness nonce before invocation-root creation, before snapshot/runtime materialization, before every process operation, and before final receipt publication. A process request must carry that latest unexpired `required_status_liveness_nonce` and `status_response_transcript_sha256`; the controller verifies both against its signed status journal for the same lease/run/instance/boot/peer/channel and atomically consumes the nonce with the process-operation intent. A missing, stale, foreign, altered, or previously consumed status proof is denied through `terminal_detail_mapping` before a process side effect.

Before emitting the admission response, the controller durably arms a root-owned trusted-clock deadline for the lease. The directory FD is held only by the root-supervised native client, which is itself revocable through a non-serializable controller capability; neither candidate code nor a general Python process receives it. At expiry the deadline owner acts without a status/process/client call: atomically invalidate and revoke the authority event, zeroize the secret, quiesce that native client, require its signed all-held-FD-close proof, and then unmount the lease boundary. If quiesce, FD-close proof, or unmount is missing or ambiguous, the root controller quarantines/destroys the disposable VM boundary and preserves deny-all; it publishes no new receipt, FD, secret, or PASS. Before issuing any status response and immediately before accepting every process operation, the controller repeats the durable secret-delivery-ACK, controller instance/boot, active-state, and expiry checks. Failure or expiry performs the same durable invalidation/revoke/quiesce/FD-close/unmount-or-quarantine/secret-zeroization transition and returns the signed zero-FD `ADMISSION_RECOVERY_REQUIRED` terminal. The client verifies every status and process response—not only the initial admission response—against the sealed controller keyset/key ID/algorithm and its signature domain, and requires its exact request/operation ID, lease/run, controller instance/boot, client challenge, channel binding, issued/expiry values, state/status, and status-proof linkage before using the result. A process response whose signed state conflicts with the durable state machine or whose expiry is reached is rejected locally and treated as the same fail-closed terminal; it cannot trigger a side effect.

Immediately after `recvmsg`, the native client rejects any ancillary data other than exactly one `SCM_RIGHTS` directory FD, applies `FD_CLOEXEC`, calls `fstat`, proves `S_IFDIR`, and compares the canonical identities against the signed response. The exact encodings are `lease_root_object_identity_sha256 = sha256(LP("samvil.task2-lease-root-object.v1", u64be(st_dev), u64be(st_ino), u32be(st_mode & S_IFMT)))`; `mount_fsid_sha256 = sha256(LP("samvil.task2-mount-fsid.v1", u32be(fsid0), u32be(fsid1)))`; and `mount_identity_sha256 = sha256(LP("samvil.task2-apfs-volume.v1", raw 16-byte APFS volume UUID))`. `st_dev`, `st_ino`, and `st_mode` come from `fstat` of the received root FD. `fstatfs(root_fd)` must report `f_fstypename == "apfs"` and supplies FSID; `fgetattrlist(root_fd, ATTR_VOL_UUID)` supplies the raw 16-byte APFS volume UUID from that same held FD. A path lookup, `getattrlist(path)`, UUID cache, or external volume name is forbidden. A response whose peer identity/signature/transcript cannot first verify is not a correlated rejection: the client closes all received FDs and the channel without response, zeroizes any bytes, and the missing-ACK/deadline path revokes it. Once that signed response is verified, `fgetattrlist`/`fstatfs` absence, malformed UUID, non-APFS filesystem, or any identity mismatch maps to `UNSUPPORTED_INVOCATION_STORAGE_QUOTA`. For any such authenticated client-side FD identity or framing rejection, the native client closes every received FD and zeroizes any secret, then sends exactly one canonical `samvil.task2-admission-client-reject.v1` record with a fresh `request_id`, the held lease/run/controller/boot values, the original signed admission-response transcript digest, one `client_reject_class`, fresh client challenge, and channel binding—never raw FD metadata, path, or secret. The controller validates that correlation, atomically invalidates/revokes/quiesces/unmounts-or-quarantines/zeroizes, and replies with the signed terminal whose `request_id` is the client-reject request, `request_kind == "client_reject"`, and detail is the exact `client_reject_detail_mapping`. If the client cannot transmit that record or receive its terminal, it still closes/zeroizes locally; the pre-armed deadline and missing-ACK path force durable revocation without waiting for another client call. Recompute all three FD identities from the held root FD immediately after receipt, before root creation, before snapshot/runtime materialization, before child spawn, and before final receipt publication; any mismatch follows this same flow. The invocation root is created only with `mkdirat` below that held FD. Every subsequent component is one nonempty name that rejects `/`, `.`, and `..`, and NUL; it is opened through the prior FD with `O_NOFOLLOW`, checked with `fstatat(..., AT_SYMLINK_NOFOLLOW)`, and retained as an FD chain. No direct path, `realpath`, `chdir`, `TMPDIR`, `tempfile.mkdtemp`, or rename/path re-resolution may enter the enabled Task -2B path.

The controller creates a non-serializable opaque process capability bound to one lease ID, run ID, controller instance, boot generation, verifier-supervised tree, signed manifest, allowed executable identity, and expiry. It is never a PID, start time, process group, or public JSON value. At lease admission, the controller creates a 32-byte `handle_secret`, retains the raw secret only in a root-owned controller secret store protected from the candidate and ordinary user processes, and durably journals only `sha256(handle_secret)` for audit/correlation. The response's signed `secret_delivery_frame_sha256` must equal `sha256(LP("samvil.task2-admission-secret-delivery.v1", hex32(sha256(utf8(lease_id))), hex32(sha256(utf8(run_id))), hex32(controller_instance), hex32(boot_generation), hex32(secret_delivery_nonce), hex32(channel_binding_sha256), raw32(handle_secret)))`. The controller emits those exact 297 bytes as record 2: one `SOCK_SEQPACKET` binary record of fixed length, no JSON, no `SCM_RIGHTS` or other ancillary data, and no following secret record. The native client receives it only after fully verifying record 1; it requires no truncation flags/ancillary data, exact 297-byte LP domain/order/lengths, its own derived lease/run hashes and controller/boot/nonce/channel fields, exactly 32 raw secret bytes, and the signed frame digest. It retains the raw secret only in its non-serializable controller-capability object, never logs, serializes, or exposes it to Python candidate code. A missing, duplicate, extra, truncated, malformed, out-of-sequence, foreign, or digest-mismatched frame closes every held FD, zeroizes all secret bytes, and follows the correlated `client_reject` path with `secret_delivery_frame_missing_or_invalid` or `unexpected_or_truncated_success_record`.

Only after that frame verifies, the native client sends exactly one canonical JSON `schema == "samvil.task2-admission-secret-delivery-ack.v1"` with `secret_delivery_ack_fields`: fresh `request_id`, lease/run/controller/boot, `secret_delivery_nonce`, `secret_delivery_frame_sha256`, fresh client challenge, and channel binding. The controller recomputes the channel binding and frame digest, consumes the nonce and request ID once, durably records the ACK, and returns exactly one signed `schema == "samvil.task2-admission-secret-delivery-ack-response.v1"` with `secret_delivery_ack_response_fields`; its transcript is `sha256(LP("samvil.task2-admission-secret-delivery-ack-response-signature.v1", canonical ACK request bytes, authenticated peer identity bytes, channel binding bytes, canonical unsigned ACK response bytes))`. The client verifies that signed response before status or process use. An absent/late/foreign/altered ACK, explicit delivery failure, ACK-response mismatch, or channel loss before the verified ACK response causes durable invalidation, idempotent authority-event revocation, native-client quiesce/FD-close/unmount-or-quarantine, and secret zeroization; the controller sends no second secret or FD and the client obtains a fresh signed outer assertion and nonce for a new admission. If an authenticated ACK or client-reject request is denied, its signed zero-FD terminal uses that exact request ID/kind; if the channel is lost, the pre-armed deadline applies instead.

`opaque_handle_proof` is lowercase-hex `HMAC-SHA256(handle_secret, LP("samvil.task2-opaque-handle-proof.v1", lease_id bytes, run_id bytes, controller_instance bytes, boot_generation bytes, operation_id bytes, operation bytes, required_status_liveness_nonce bytes, status_response_transcript_sha256 bytes, client_challenge bytes, channel_binding bytes))`; the controller recomputes it from the retained raw root-owned secret and compares it in constant time before every operation. Secret-store loss, a controller crash/reboot, IPC loss, boot change, or any terminal lease state invalidates the capability; both controller and native client zeroize their raw secret before releasing the capability, and no recovery path reconstructs it from the journal hash. Its authenticated native operation request has exactly `schema == "samvil.task2-admission-process-request.v1"`, `request_id`, `operation_id`, `lease_id`, `run_id`, `controller_instance`, `boot_generation`, `operation`, `client_challenge`, `channel_binding_sha256`, `required_status_liveness_nonce`, `status_response_transcript_sha256`, and `opaque_handle_proof`; its response has exactly `schema == "samvil.task2-admission-process-response.v1"`, `request_id`, `operation_id`, `lease_id`, `run_id`, `controller_instance`, `boot_generation`, `operation`, `state`, `controller_liveness_nonce`, `client_challenge`, `channel_binding_sha256`, `required_status_liveness_nonce`, `status_response_transcript_sha256`, `issued_unix_seconds`, `expires_unix_seconds`, `controller_keyset_sha256`, `controller_signer_key_id`, `controller_signature_algorithm`, `signed_transcript_sha256`, and `signature_base64`. Its canonical unsigned response bytes are full process-response fields minus `signed_transcript_sha256` and `signature_base64`; its `signed_transcript_sha256` is the digest of `LP("samvil.task2-process-response-signature.v1", canonical process-request bytes, authenticated peer identity bytes, channel binding bytes, canonical unsigned process-response bytes)`, and `signature_base64` is canonical RFC 4648. The `spawn` operation has no caller-supplied command or path: the controller starts only the lease-bound allowed executable from the signed manifest. `operation_id` is exactly a 64-lowercase-hex value unique per lease. Valid durable transitions are `issued --spawn--> spawned --terminate--> termination_requested --reap--> reaped --complete--> completed`; any nonterminal state may move only to `invalidated` after fault/recovery, and `completed`/`invalidated` are terminal. Before a side effect, the controller atomically journals `(lease_id, request_id, operation_id, canonical request digest, previous state, intended state)`; after the side effect it atomically journals the signed result before replying. A crash between those records invalidates the handle and returns `BLOCKED_ENVIRONMENT / ADMISSION_RECOVERY_REQUIRED`; it never retries a side effect after reboot. The same `(lease_id, operation_id, canonical request)` returns the durable byte-identical signed result, while an altered request with an existing operation ID, foreign handle, stale handle, or post-reboot/controller-instance change is rejected. A controller crash, IPC loss, or boot change invalidates every handle and preserves deny-all.

- [ ] **Step 5: Define Task -2B's required code changes**

Task -2B is a separate implementation plan and must contain all of these exact changes:

1. Add `samvil.full-gate-manifest.v2` and `samvil.full-gate-receipt.v2` exact field sets, including policy, controller, mount, quota, file-count, opaque process authority, lease, original run-envelope/observer evidence digests, signer/keyset transcript commitments, observer projections, and the signed lease-receipt binding.
2. Reject v1 manifests for any Task -2 canonical execution; update prior-receipt validation, factories, inventories, `CONTROL_PATHS`, and all exact receipt/manifest tests in the same commit.
3. Have the trusted outer verifier provide a sealed or cryptographically authenticated manifest. Candidate code and the public full-gate CLI cannot select the authority root, client, trust anchors, quota, lease, or observer.
4. Verify the complete Step 4 outer-verifier assertion and original run-envelope/observer evidence before a lease, status acceptance, receipt, or sidecar projection. A matching hash string, fixture, or client-selected signer is never a substitute for canonical signature/keyset/expiry/binding verification.
5. Use the received mount descriptor with the complete Step 4 `AF_UNIX SOCK_SEQPACKET`/four-record admission success sequence/one-directory-FD/one-fixed-secret-frame/signed-ACK/`recvmsg`/truncation-CMSG-rejection/all-FD-close/FD-identity/FD-chain/client-reject/zeroization protocol and `mkdirat`/`openat` only. The directory FD remains in the root-supervised native client, never candidate/Python code; the Task -2 invocation root may not come from `TMPDIR` or `tempfile.mkdtemp`; recheck held-FD object and mount identity at every boundary.
6. Replace the Darwin child lifecycle with the Step 4 opaque controller capability and operation state machine. Tests must prove the enabled Darwin path does not call `subprocess.Popen`, raw PID operations, `os.kill`, `os.killpg`, Linux pidfd code, or polling cleanup, and that no wire record leaks a PID-bearing value.
7. Map every Task -2 admission failure to outer terminal `BLOCKED_ENVIRONMENT` plus the exact machine-readable `terminal_detail_mapping` or `client_reject_detail_mapping` bucket: quota/FD identity failures use `UNSUPPORTED_INVOCATION_STORAGE_QUOTA`; opaque-handle/process-state failures use `DETACHED_PROCESS_SIGNAL_UNAVAILABLE`; assertion/signature/channel/status/secret-frame/controller-recovery failures use `ADMISSION_RECOVERY_REQUIRED`. Every post-auth denial carries the exact rejected `request_id`/`request_kind` in the signed zero-FD/zero-secret terminal-response schema; only malformed pre-auth records use the stated silent close. Update the v2 receipt, terminal mapper, fixture, and every consumer in the same commit; no admission failure writes PASS.
8. Prove candidate object packs and Unit 0 candidate ancestry exclude every control sidecar, authority receipt, and Task -2B module.
9. Run machine-verifiable two-independent-run proof and controller-journal same-run/same-nonce replay proof. The latter accepts only the same admission idempotency key and semantic request digest while the same controller instance/boot, active unexpired lease, root-authority FD/event proof, durable signed secret-delivery ACK, and same-native-client resume proof remain valid; it returns only the dedicated zero-FD/zero-secret replay-resume wrapper for a new request ID/challenge/channel binding, with a byte-identical authoritative lease-receipt payload, records controller authority event count one and duplicate event count zero, and rejects any different semantic digest for the same nonce or key before authority allocation. It must separately prove the initial FD/secret/ACK grammar, replay-resume no-redelivery contract, every client-reject terminal correlation, and that a crash/reboot/instance mismatch, ACK loss, expiry, missing FD proof, lost capability/resume proof, or recovery ambiguity invalidates/revokes/quiesces/unmounts-or-quarantines/zeroizes with zero FD/secret and `ADMISSION_RECOVERY_REQUIRED`.
10. Prove the root-owned trusted-clock deadline independently of client activity: after the native client receives the directory FD and then stops, expires without a status/process call, and the controller produces a durable revoke, native-client opaque-capability quiesce, signed all-held-FD-close proof, and unmount or boundary quarantine. A held client FD, failed close proof, or failed unmount cannot be treated as cleanup success, may not emit PASS, and may not leave candidate code able to use the mount.

- [ ] **Step 6: Confirm GREEN**

Run:

~~~
run_task2_portable /usr/bin/python3 -I -m unittest discover -s tools/release-control/tests -p 'test_task2_admission_contract.py' -v \
  && run_task2_portable /usr/bin/python3 -I -m unittest discover -s tools/release-control/tests -p 'test_invocation_admission.py' -v
~~~

Expected: the machine-readable field sets, document digest binding, terminal rule, static parser, and fixture-only trust-root boundary all pass as `PORTABLE CONTRACTS`; no test creates a live capability.

In the same Task 3 commit, extend that required `Run Task -2 portable admission contracts` CI step to run first `test_task2_admission_contract.py` and then `test_invocation_admission.py`, both through the same `mcp/.venv/bin/python -I -B -m unittest discover` form. Both commands are mandatory and remain portable-contract coverage only; a green CI run does not imply a Task -2B or P0 authority result.

- [ ] **Step 7: Freeze the staged acceptance packet**

~~~
task2_git add docs/superpowers/control/2026-08-08-task2-admission-trust-root.md docs/superpowers/specs/2026-08-08-samvil-task2-admission-contract.md docs/superpowers/operations/2026-08-08-task2-admission-provisioner-handoff.md tools/release-control/tests/fixtures/task2-admission/channel-contract.v1.json tools/release-control/tests/test_task2_admission_contract.py .github/workflows/release-checks.yml \
  && run_task2_portable /usr/bin/python3 -I -m unittest discover -s tools/release-control/tests -p 'test_task2_admission_contract.py' -v \
  && run_task2_portable /usr/bin/python3 -I -m unittest discover -s tools/release-control/tests -p 'test_invocation_admission.py' -v \
  && verify_task2_commit docs/superpowers/control/2026-08-08-task2-admission-trust-root.md docs/superpowers/specs/2026-08-08-samvil-task2-admission-contract.md docs/superpowers/operations/2026-08-08-task2-admission-provisioner-handoff.md tools/release-control/tests/fixtures/task2-admission/channel-contract.v1.json tools/release-control/tests/test_task2_admission_contract.py .github/workflows/release-checks.yml
~~~

Expected: the staged index is the sole candidate input. The provisioner independently seals that exact index tree together with the Task 3-base provenance and queues exactly one matching one-time attestation plus sealed Task 3 descriptor; the descriptor digest, exact base-to-candidate path-status set, target ref, fixed commit message, and candidate tree are bound together in root-controlled state.

- [ ] **Step 8: External attestation handoff**

The provisioner performs the same out-of-repository derivation as Task 1: resolve the frozen index object itself, derive its exact base-to-candidate add/modify path-status set from sealed objects, require exact equality with the Task 3 descriptor allowlist, verify the fresh base-specific venv provenance and private VM controls, queue exactly one signed attestation and one sealed Task 3 descriptor for `staged`/`task2_full_precommit` under the same base/tree/challenge, and record both issuances/digests externally. A candidate worker cannot choose a tree ID, queue name, receipt, snapshot path, target ref, task descriptor, or commit message; any unlisted/missing/renamed/copied/deleted path is a hard stop.

- [ ] **Step 9: Snapshot gate and commit**

~~~
task2_full_precommit --staged \
  && task2_commit_snapshot_receipt
~~~

### Task 4: Stop until the external authority is independently reviewed

**Files:** no repository file changes are authorized in this task.

- [ ] **Step 1: Collect the external packet without running a candidate**

Review the VM/UID/private-`/tmp` identity, sealed plan-lineage and venv-provenance verifier digests, atomic attestation→snapshot→commit-fence state machine, staged task-descriptor digest/target-ref/fixed-message binding, root-controller and native-client digest, authenticated peer method, initial-FD/secret/ACK and replay-resume descriptor contract, opaque-process-capability/deadline-owner design, root journal schema, independent signer/observer trust anchors, exact policy/lease/observer records, and fault-evidence index. Reject any artifact that names a developer HOME, CODEX_HOME, a real Claude profile, cache, settings file, or existing user installation.

- [ ] **Step 2: Decide the terminal**

| Condition | Required result |
| --- | --- |
| A verified live trusted-control validation or recovery failure: outer assertion/signature/keyset, channel, status, journal, controller crash/reboot/IPC loss | `BLOCKED_ENVIRONMENT / ADMISSION_RECOVERY_REQUIRED`, no FD/secret/mutation/PASS |
| Kernel quota is independently proven but opaque Darwin process authority is absent | `BLOCKED_ENVIRONMENT / DETACHED_PROCESS_SIGNAL_UNAVAILABLE` |
| Any prerequisite deliverable or fault proof is absent, ambiguous, stale, or unreviewed (including an *unproven* crash/reboot/IPC deny-all behavior) | `BLOCKED_ENVIRONMENT / UNSUPPORTED_INVOCATION_STORAGE_QUOTA` |
| All external artifacts independently reviewed | create a new Task -2B plan; do not enable a live full-gate path in this plan |

- [ ] **Step 3: Preserve the blocker without invoking a full gate**

Do not run the full gate from this preparation plan. Record these current source facts in the Task -2B entry review: `tools/release-control/run-full-gate-isolated.py:4783-4792` returns `False` for quota support; `:4830-4840` unconditionally blocks quota acquisition; `:5055-5075` acquires quota before invocation-root creation and blocks missing detached-process authority; and `:9951-9957` maps both statuses to `BLOCKED_ENVIRONMENT`. The portable parser suite may run, but no static-preparation command exercises a candidate or is reported as P0 PASS.

## 6. Canonical P0 is outside this plan

After Task -2B is implemented and independently reviewed, the external environment must run the exact committed PR #14 control suite twice under distinct externally signed run envelopes, run IDs, nonces, lease IDs, and observer IDs. The policy-defined normalized projection must be equal; whole receipt bytes must differ between runs.

A separate same-run/same-nonce response-loss replay is mandatory. It is permitted only while the same controller instance/boot remains live, the lease is active and unexpired, the root authority re-verifies the original event/FD boundary, the one-time secret-delivery ACK is durably present, and the same root-supervised native client proves possession of its original capability through the exact replay-resume HMAC; any crash/reboot/ack loss/lost capability instead proves durable invalidation, revoke/quiesce/unmount-or-quarantine/zeroization, zero FD/secret emission, and `ADMISSION_RECOVERY_REQUIRED`. The permitted replay must prove:

~~~
authoritative lease-receipt bytes = byte-identical
replay-resume wrapper = new request ID/challenge/channel binding, zero FD, zero secret, no ACK/frame
controller authority event count = one
duplicate event count = zero
candidate/profile mutation outside invocation mount = zero
~~~

The reviewed P0 sidecar must bind the two independent receipts, replay receipt, control commit/tree, R0 runtime closure and pytest config digests, policy/controller/mount/lease/observer/signer identities, receipt schema, and fault-matrix digest. It is trusted-control evidence only and must be proven absent from the Unit 0 candidate object pack and candidate ancestry.

## 7. Unit 0 no-go checklist

Do not begin Unit 0 until all of these are independently reviewed and pinned:

1. Task -2B live quota, opaque process authority, fault matrix, two-run receipts, and replay proof.
2. R0 receipt-pinned Python 3.12 runtime/test closure.
3. P1 focused isolated runner.
4. P2 exact pre-Unit-0 Action and runtime lock rows.
5. P3 external authorization, admission controller, and observer/monitor capabilities.
6. The control-side sidecar and candidate ancestry exclusion proof.

## 8. Verification and review

Before opening a preparation-code PR, run:

The Task 3 commit creates a new clean base, so trusted control must first issue one fresh base-specific venv-provenance record/install receipt and then queue one clean-mode sandbox attestation for its exact `HEAD^{tree}`. The following command consumes that record; it must not reuse the Task 3 staged-tree provenance or attestation.

~~~
task2_git diff --check \
  && run_task2_portable /usr/bin/python3 -I -m unittest discover -s tools/release-control/tests -p 'test_invocation_admission.py' -v \
  && run_task2_portable /usr/bin/python3 -I -m unittest discover -s tools/release-control/tests -p 'test_task2_admission_contract.py' -v \
  && task2_full_precommit --clean \
  && test -z "$(task2_git status --porcelain)"
~~~

Use one fresh implementation worker per task, then an independent spec-compliance reviewer and code-quality reviewer. Reviewers must prove:

1. no user HOME, CODEX_HOME, Claude profile, cache, settings, or real installation was read or written;
2. no static fixture, root-shaped copy, environment variable, CLI argument, or path produces a live capability;
3. no raw-PID-style provider survives parser validation;
4. all local commands, including Git checks and full pre-commit helpers, use the isolated envelope and disabled hooks;
5. the existing full-gate terminal remains fail-closed;
6. the external packet's machine-readable contract fixture, document digest binding, and terminal object are exact before a Task -2B plan is created;
7. the external packet is complete before a Task -2B plan is created.

## 9. Plan self-review

**Spec coverage:** The plan separates portable static preparation from canonical P0. It covers static schema/identity validation, no-fixture-authority behavior, external kernel quota, native opaque process authority, trust-anchor ownership, descriptor-bound mount requirements, two independent runs, same-nonce replay, R0, P1, P2, P3, and Unit 0 ancestry exclusion.

**Placeholder scan:** The plan contains no unresolved placeholder or implicit live-enable step. Task -2B is deliberately not started until its external inputs exist and are independently reviewed; the required inputs and resulting code changes are enumerated exactly.

**Type consistency:** Static parser functions return dictionaries and `StaticAdmissionBundle` only. Neither type is a live capability. Live manifest, receipt, controller client, mount descriptor, and opaque process capability types are deferred together to the separately scoped Task -2B plan.
