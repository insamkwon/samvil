# SAMVIL v4.32.3 Release Bridge — Design Spec

**Date:** 2026-07-28

**Status:** Written for user review

**Parent program:** `2026-07-28-samvil-v433-safe-upgrade-program-design.md`

**Target branch:** `release/v4-stable`

**Implementation branch:** `codex/v4.32.3-release-bridge`

**Release:** v4.32.3 stable

---

## 1. Decision

v4.32.3은 기능 release가 아니라 distribution containment bridge다. 목적은 다음과
같다.

1. v4.33/future updater가 GitHub default branch와 mutable working tree를 설치 원본으로
   사용하지 않게 한다.
2. future update가 existing cache를 in-place 수정하거나 sibling versions를 자동
   삭제하지 않게 한다.
3. Codex setup의 `--check`가 실제로 network와 filesystem mutation이 없는 read-only
   command가 되게 한다.
4. Historical default `main`을 GitHub compatibility quarantine으로 고정하고,
   새 `release/v4-stable`을 explicit-ref stable Release branch로 만들어 v4.33 development를 integration
   branch로 격리한다.
5. Current v4.32.2 base → reviewed fuse의 `main` holdback과, 같은 fuse → bridge remainder의
   `release/v4-stable` linear lineage를 분리한다. Default branch 이름은 바꾸지 않으며 no-ref와
   explicit-main consumer는 holdback 전체에서 같은 passive tree만 받는다.

Bridge는 Codex native migration을 활성화하지 않는다. v4.33 one-command upgrade가
소비할 verified release channel과 safe bootstrap boundary만 만든다.

Bridge는 이미 배포된 v4.32.2 `/samvil:update`를 안전한 acquisition path로 재정의하지
않는다. 대신 old updater가 암묵적으로 조회하고 clone하는 GitHub default branch를
manifest version `4.32.2`의 reviewed quarantine-fuse commit에 고정해 정상 v4.32.2
사용자의 version check를 no-op으로 만든다. Discovery-failure clone이 받는 fuse의 updater
surface도 plugin mutation과 raw rsync fallback을 제거하고 `DEFERRED_TO_V433`만 안내한다.
Attested bridge acquisition runner는 `EMPTY_READY` clean-profile release canary에만 사용한다.
그 경로가 실제 Claude fixture에서 입증되지 않으면 bridge user rollout을 열지 않는다.

Legacy holdback 기간에는 default `main` fuse뿐 아니라 `release/v4-stable`과 holdback 시작 뒤 새로 만드는
v4.32.3/v4.33 allowlisted tag의 `.claude-plugin/marketplace.json`도 installable SAMVIL entry 0을
유지한다. 기존 immutable historical tag/commit은 변경하지 않는다. Release asset/bootstrap은
marketplace listing 없이 설치하므로, custom `source.ref: "main"`은 계속 fuse를 보고 explicit
`source.ref: "release/v4-stable"`도 remote catalog에서 새 SAMVIL payload를 발견하지 않게 한다. 다만 stale
disk catalog나 refresh 전 process-local memo는 원격에서 revoke할 수 없으므로 cold-process
PASS와 분리한 typed residual이다. Historical tag/commit, fork/local ref도 remote revoke가
불가능한 unsupported residual이다.

---

## 2. Why a bridge alone is insufficient

현재 `skills/samvil-update/SKILL.md`는 다음 순서로 동작한다.

- installed cache의 `.claude-plugin/plugin.json`에서 current version 조회
- GitHub Contents API의 default ref에서 latest version 조회
- version이 다르면 ref를 지정하지 않고 repository clone
- cloned default branch를 current cache에 in-place `rsync`
- cache directory rename
- 다른 version directories 삭제

따라서 v4.32.2 사용자가 bridge를 한 번도 실행하지 않은 상태에서 PR #13이 default
`main`에 들어가면, bridge manifest를 4.32.3으로 유지하더라도 다음 일이 발생한다.

```text
installed CURRENT = 4.32.2
default main LATEST = 4.32.3
CURRENT != LATEST
  → old updater clones the entire post-PR-13 main tree
```

Bridge adoption률을 safety boundary로 사용할 수 없다. 또한 `main`에 v4.32.3 manifest를
노출하면 정상 v4.32.2도 `CURRENT != LATEST`가 되어 destructive first hop을 실행한다.
실제 safety boundary는 다음 branch topology다.

```text
legacy/v4.32.2-original = immutable pre-promotion rollback anchor
main = GitHub default, immutable v4.32.2-version quarantine fuse
release/v4-stable = same fuse commit first, then non-default canonical v4.32.3/v4.33 stable Release branch
codex/v4.33-integration = all v4.33 development and RC work
```

PR #13이 stable 승인 전에 `release/v4-stable`에 들어가거나, default `main`이 quarantine
lineage를 벗어나면 bridge release는 실패한 것으로 간주한다.

---

## 3. Honest compatibility boundary

이미 배포된 old updater의 첫 실행을 소급해서 transactional하게 만들 수는 없다.
따라서 P0는 정상 exact v4.32.2 사용자가 old updater로 v4.32.3을 받는 경로 자체를 열지
않는다. GitHub default `main`은 version `4.32.2`를 유지하는 reviewed no-write fuse
commit/tree에 남기고 v4.32.3 이상은 explicit `release/v4-stable`/tag/Release ref로만 배포한다.

Bridge가 보장하는 것은 다음이다.

- exact v4.32.2 old updater가 default-feed version check에서 no-op임
- bridge 설치 뒤의 모든 future update는 stable Release asset 경로를 사용함
- v4.33/future updater contract는 current cache를 in-place 수정하거나 자동 삭제하지 않음
- v4.33 official bootstrap은 old updater 상태와 무관하게 version-independent entry를
  제공함

Bridge의 release-control gate는 parent program의 storage-boundary admission을 그대로
상속한다. Canonical PASS는 Task -2가 attested한 invocation-exclusive,
kernel-enforced hard-quota filesystem 안에서만 가능하다. 그 증거가 없거나
유효하지 않으면 `UNSUPPORTED_INVOCATION_STORAGE_QUOTA`로 실행 전에
차단하고 workstream terminal은 `BLOCKED_ENVIRONMENT`이다. Logical byte/FD
계수나 `RLIMIT_FSIZE × RLIMIT_NOFILE`는 이 경계를 대체하지 못한다. PR #14의
portable 실행은 fail-closed control foundation과 orchestration contract 증거이며,
actual-host full-gate PASS나 Stage A/bridge authorization이 아니다.
또한 canonical execution은 atomic identity-bound detached-process signal handle을
요구한다. Current Darwin foundation은 raw PID signal을 금지하므로 quota adapter가
존재하더라도 실행 전에 `DETACHED_PROCESS_SIGNAL_UNAVAILABLE` /
`BLOCKED_ENVIRONMENT`로 차단하며, Linux `pidfd` 또는 동등한 reviewed OS authority가
있어야 다음 경계로 진행한다.

실제 legacy update 순서는 current cache in-place `rsync`, 기존 venv editable refresh,
cache rename, sibling deletion이다. Rename 전 절대경로를 담은 editable metadata와 MCP
path는 rename 뒤 stale할 수 있고, 중단되면 hybrid cache가 남을 수 있다. 따라서 P0는
그 first hop을 trigger하지 않으며, 이미 존재하는 위험한 경로에
다음 bridge-owned 보장을 적용하지 않는다.

- current bytes mutation 0
- previous cache retention
- rollback source retention
- same-session recovery

### 3.1 Acquisition lanes

| Lane | Role | Safety contract |
|---|---|---|
| Installed legacy `/samvil:update` from exact v4.32.2 | best-effort default-feed containment | version discovery 성공 시 `CURRENT == LATEST` mutation 0; discovery failure path는 unsafe legacy limitation |
| Legacy discovery-failure clone of quarantine fuse | damage containment only | passive manifest/skills, empty marketplace catalog, no v4.33 bytes; old rename/delete risk remains |
| Attested bridge acquisition runner + verified Release installer | controlled clean bridge acquisition | signed single-transaction authorization의 single-tenant disposable-VM `EMPTY_READY` darwin-arm64 fixture에만 install/selection 수행 |
| v4.33 version-independent bootstrap | universal migration path | clean, legacy, hybrid, modified, foreign 상태를 P5 transaction contract로 처리 |

사용자는 raw `claude plugin update`를 직접 safe path로 실행하지 않는다. Release에서
download하고 attest한 stdlib-only acquisition runner는 topology와 registry를 먼저 분류한다.
P0에서 mutation 가능한 external topology는 official marketplace repository/id/source row의
`source.ref`가 exact absent이고 local marketplace catalog가 exact `REFRESHED_PAUSE_COLD`이며,
existing SAMVIL plugin selection, cache, `mcpServers.samvil-mcp` row가 모두 없는 exact `EMPTY`
profile뿐이다. 그 경우에만 verified Release core/runtime을 새 version directory에 no-replace
install하고 Claude-closed registry move-aside/no-replace transaction으로 next-restart selection을
전환한다.

P0 mutation lane은 일반 macOS account가 아니라 release-control이 소유한 single-tenant disposable
VM의 dedicated non-admin canary UID에서만 열린다. 그 UID에는 interactive login, unrelated launch
agent/background process, 다른 updater가 0이고 verifier-supervised process tree 외 새 same-UID process
creation을 control plane이 freeze한다. VM root/admin과 control-plane supervisor는 명시적 TCB다.
이 enclave identity와 process-admission freeze receipt가 없으면 runner는 diagnosis-only이며 registry
mutation은 0이다. 이는 public clean-user support가 아니라 exact canary safety boundary다.

이 freeze는 verifier child lifetime에 묶인 best-effort 감시가 아니다. VM boot 전부터 설치된
root-owned admission controller가 dedicated UID의 interactive login, user launchd domain, remote login,
cron/at과 controller 밖 process creation을 kernel/platform policy로 deny한 상태를 기본값으로 가진다.
Controller는 user-writable path 밖의 root-owned durable journal에 monotonically increasing lease epoch,
transaction id, allowed executable/code identity, parent/process-tree identity와 boot generation을 fsync한
뒤에만 exact verifier tree 하나를 spawn한다. Verifier 또는 runner의 parent death, controller IPC loss,
unexpected child, audit gap은 해당 tree를 종료하고 admission을 계속 deny한 채
`RECOVERY_REQUIRED`로 전환한다. Controller crash/reboot 뒤 launch-on-boot recovery도 deny-all에서
시작하며, exact durable lease와 bridge journal을 reconcile하기 전 Claude나 runner를 자동 spawn하지
않는다. 이 deny primitive와 reboot persistence를 machine-test할 수 없는 macOS/VM 조합은 P0 canary
대상이 아니다.

`PENDING_RESTART`는 admission lease 종료점이 아니다. Controller가 sealed target과 pending receipt를
다시 검증한 뒤 exact Claude executable/code identity, sanitized environment, config/profile root,
pending transaction id를 바인딩한 one-shot handoff capability를 durable하게 기록하고 새 Claude
process tree를 직접 spawn한다. 그 tree 밖 same-UID process는 계속 deny한다. New-session guard,
attestation-only MCP, finalizer와 first controlled tool response가 같은 lease epoch/process ancestry를
증명한 뒤 controller가 lease를 consume하고 admission policy를 원래의 canary baseline으로
복원·검증해 `ADMISSION_FREEZE_RELEASED`를 durable하게 기록해야만 `COMMITTED`가 된다. Serving
intent 전 exact rollback terminal도 같은 fail-closed release 절차를 요구한다. Serving intent 뒤
failure는 admission을 열지 않고 capability 0 `RECOVERY_REQUIRED`로 남긴다.

Signed catalog와 `STOCK_EXACT`/`KNOWN_HYBRID` 분류는 existing v4.32.2를 안전하게 자동
전환하기 위한 권한이 아니라 정확한 진단 증거다. Existing v4.32.2, legacy global MCP row,
old selected plugin, `USER_MODIFIED`, `FOREIGN`, directory source, ambiguous multiple cache는
모두 protected-scope mutation 0 `DEFERRED_TO_V433` 또는 `BLOCKED_USER_STATE`로 종료한다.
서로 다른 Claude selection/settings resource를 모든 crash point에서 동시에 보호할 universal
pre-exec boundary가 P0에 없기 때문이다.

따라서 v4.32.2 사용자는 bridge를 별도로 설치하지 않고 default-main quarantine 뒤에
그대로 남는다.
최종 v4.33 version-independent bootstrap이 legacy Claude를 보존한 채 Codex native profile을
한 번에 설치·전환한다. Bridge acquisition runner는 clean-install release machinery canary용이며
existing user migration command로 안내하지 않는다.

Existing-user discovery는 unsafe old updater에 의존하지 않는 별도 release surface다. Stage A 전에
immutable quarantine fuse의 root README와 every passive `/samvil`/`/samvil:update` alias는 실행 가능한
latest command 대신 exact landing page
`https://github.com/insamkwon/samvil/releases/tag/v4.33.0`만 출력하도록 고정한다. Stable publish 때
그 exact GitHub Release notes가 version-independent bootstrap 한 명령, pinned asset digest,
attestation verification과 legacy/modified-state 설명의 canonical copy가 된다. Same copy는 repository
pinned announcement와 canonical documentation landing page에 게시하되 redirect/latest URL이나 raw
marketplace install을 primary action으로 쓰지 않는다.

GA gate는 unauthenticated browser에서 exact release page와 assets가 보이고, clean/stock legacy/
modified fixture가 그 한 명령으로 각 expected terminal state에 도달하며, quarantine passive command가
network/profile/cache mutation 0으로 같은 page만 안내한다는 proof를 요구한다. GitHub Release watcher와
pinned announcement는 dormant v4.32.2 사용자에게 out-of-band 발견 경로를 제공한다. 이미 설치된
v4.32.2 bytes를 안전하게 바꿀 수 없으므로 모든 dormant 사용자가 자동 prompt를 본다고 주장하지
않으며, 발견 전까지 기존 runtime은 unchanged로 남는다.

따라서 bridge는 과거 동작을 미화하지 않고 위험한 update protocol을 끊는 forward-only
compatibility release다. Bridge adoption은 `main` containment의 전제도, v4.33 bootstrap의
전제도 아니다.

### 3.2 Default quarantine fuse

Default `main`의 fuse commit은 original v4.32.2 code를 그대로 user runtime으로
노출하는 branch가 아니다. Manifest version은 `4.32.2`로 유지해 already-installed stock
v4.32.2 old updater를 version equality에서 멈추되, discovery-failure default clone이 받는
automatic surface는 passive-only로 축소한다.

- `.claude-plugin/plugin.json`의 `skills`는 reviewed `quarantine-skills/`만 가리킨다. Fuse
  tracked tree는 production skill body를 보존하지 않는다. Signed legacy catalog가 열거한
  every historically discoverable `skills/*/SKILL.md`, hook/script/MCP entry path에는 network,
  temp, profile, cache, settings, project write 0의 passive overlay를 같은 path로 제공한다.
  이는 old updater의 no-delete rsync 뒤 기존 discoverable file이 살아남는 것을 막는다.
- Historical README/bookmark에서 직접 실행될 수 있는 `scripts/setup-codex.sh`, cache sync,
  direct setup/hook installer와 catalog가 열거한 모든 user-facing mutator path도 같은 passive
  guard로 덮는다. Default clone 뒤 어떤 legacy setup command를 실행해도 install을 시도하지 않고
  `DEFERRED_TO_V433`만 출력한다.
- Root `README*`, `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, OpenCode/Codex host instruction files와
  catalog가 열거한 every auto-loaded project instruction path도 passive pause allowlist로
  교체한다. Fuse checkout을 처음 여는 host가 chain marker, MCP setup, installer, package manager,
  project bootstrap을 시작하게 하는 instruction은 0이다. Contributor/build 안내는 fuse가 아니라
  explicit `release/v4-stable` ref 문서에서만 제공한다.
- Plugin manifest의 hooks와 `mcpServers` registration은 0이고 conventional root `.mcp.json`도
  exact empty server map이다. Actual legacy host/source-row matrix에서 discovered SAMVIL skill
  set은 quarantine-only이고 `/samvil`, `/samvil:update`와 모든 historical alias가 passive
  `DEFERRED_TO_V433`만 반환해야 한다. Pre-existing global `mcpServers.samvil-mcp` row는 fuse가
  제거하지 않으므로 그 process launch까지 0이라고 주장하지 않는다.
- `.claude-plugin/marketplace.json`은 marketplace metadata는 유지하지만 installable `samvil`
  plugin entry를 제거한 exact empty/pause catalog다. 모든 pre-refresh Claude process가 종료된
  뒤 시작한 cold process의 exact `REFRESHED_PAUSE_COLD`에서만 new marketplace install은
  not-found이고 installed SAMVIL plugin/selection/settings mutation 0으로 종료해야 한다.
  Marketplace source checkout의 expected refresh는 별도 digest로 기록한다.
- Quarantine `/samvil`과 `/samvil:update`는 network, temp, package manager, profile, cache,
  settings, project mutation 0으로 v4.33 bootstrap 대기 상태와 exact
  `https://github.com/insamkwon/samvil/releases/tag/v4.33.0` landing page만 출력한다.
- Clone/rsync/rename/sibling delete와 manual rsync fallback copy는 fuse skill에 존재하지 않는다.
- README/tutorial/marketplace-facing copy는 신규 설치 일시 중단과 v4.33 exact bootstrap만
  primary path로 안내한다.
- Literal version equality 외 path/mtime/folder fallback으로 existing state를 current라고
  주장하지 않는다.

Fuse는 same semantic version/different tree인 의도적 one-off distribution이다. Release core로
adopt하지 않고 signed catalog의 별도 `quarantine_fuse` row로 exact commit/tree/manifest/passive
surface digest를 바인딩한다. Existing v4.32.2는 fuse bytes를 받지 않으며, older/corrupt state의
destructive first hop은 unsupported limitation으로 남는다.

Marketplace entry removal은 existing install을 자동 uninstall하거나 selection/cache를 지울
권한이 아니다. Live `main` promotion 전에 exact fuse tree를 disposable mirror repository에서
characterize한다. Official `source.ref` absent와 custom `source.ref: "main"`에서는 existing 4.32.2와
higher 4.32.3 fixture의 auto-update on/off, direct update trigger, randomized 0~600초 scheduler의
deterministic equivalent 또는 실제 >600초 observation, 두 번의 complete restart를 수행한다.
모든 pre-refresh Claude process가 종료된 뒤 시작한 cold process의 exact
`REFRESHED_PAUSE_COLD`에서는 installed root/cache, selection, global settings/MCP row, running
legacy runtime이 유지되고 new install만 not-found여야 한다. Marketplace source
checkout/catalog의 expected target digest는 별도 기록한다. Same-version refresh, downgrade,
uninstall, selection rewrite가 하나라도 관찰되면 quarantine topology는 release blocker이며 live
main promotion 또는 `release/v4-stable` bridge merge를 하지 않는다.

Historical immutable tag/commit과 fork/local source는 같은 axes로 characterize하지만 empty-catalog
보존 PASS 대상이 아니다. Historical fixed ref가 cached install/update를 계속 제공하는 결과는
`PINNED_SOURCE_RISK_OBSERVED`, fork/local의 unknown behavior는 unsupported
`HOST_TOPOLOGY_RISK_OBSERVED`로 분리한다. Remote revoke나 자동 repair를 주장하지 않는다.

단, pre-promotion local marketplace cache에 old installable entry가 남아 있으면 install은 refresh를
건너뛰고 cached `source: "./"`를 사용할 수 있다. Update도 refresh failure 또는 recent-cache
skip 뒤 cached entry를 사용하며 semver guard 없이 higher v4.32.3을 cached v4.32.2로 downgrade할
수 있다. Auto-update도 같은 operation을 실행한다. 원격 catalog만으로 이 bytes를 revoke할 수
없으므로 cached-entry+plugin-absent install, refresh network failure, 30초 recent-cache skip,
auto-update >600초/two-restart fixture를 `STALE_CATALOG_RISK_OBSERVED`로 기록한다. 이 fixture는
new-install block/no-downgrade PASS에 포함하지 않고 final v4.33 bootstrap recovery input으로
넘긴다.

Disk catalog refresh는 이미 실행 중인 다른 Claude process의 process-local marketplace memo를
invalidate한다고 가정하지 않는다. Process A가 old installable entry를 UI/memo에 적재하고,
process B가 disk catalog를 approved pause bytes로 refresh한 뒤에도 A가 cached entry로 install을
시도할 수 있다. 이를 actual two-process fixture로 실행해 cached entry/source, resolved
installLocation의 pre/post inode/tree, installed tree digest, executable/auto-loaded surface와
settings/selection mutation을 inert original-tree control과 비교한다.

허용 가능한 residual은 exact control과 같은 `BASELINE_EQUIVALENT_OLD_ACTIVE` 또는 switch가 만든
추가 executable/auto-loaded surface가 0이고 mutation cardinality, settings와 selection이 control보다
나쁘지 않은 `PASSIVE_ONLY_NO_WORSE`뿐이다. Switch-attributable active surface, hybrid bytes,
downgrade/uninstall, 추가 settings/selection mutation 또는 분류 불명은
`SEMANTIC_FUSE_OR_UNKNOWN`이며 Stage A default-main promotion과 bridge merge를 차단한다. Live Stage A
뒤 발견되면 Stage R을 실행한다. 허용 residual도 `STALE_HOST_MEMORY_RISK_OBSERVED`로만 기록하며
holdback PASS가 아니라 final v4.33 bootstrap recovery input이다. 안전한 new-install not-found
주장은 all pre-refresh Claude process 0과 그 뒤 시작한 cold process에만 적용한다.

Default `main` fuse promotion은 installed SAMVIL version만이 아니라 v4.32.2가 실제 installable이었던 every
compatible Claude Code package identity의 updater/skill-discovery semantics와 README clone을
소비하는 supported Codex/Claude/OpenCode/Gemini host의 first-open semantics에 영향을 준다.
Compatible set은 declared minimum/compatibility floor부터 switch cutoff까지 retrievable exact
identity와 actual install/distribution receipt의 observed identity union이다. Declared floor나
receipt가 없으면 marketplace 기능 도입 뒤 switch cutoff까지 every retrievable identity를
포함하며, 완전성을 증명할 수 없으면 live switch blocker다. Reviewed
`legacy-host-matrix.json`은 `consumer_kind`, exact OS/architecture/libc-or-platform variant,
host package version/tarball digest, optional platform binary artifact digest, updater or
instruction-loader module digest, supported schema, source-row form을
pin한다. Marketplace rows는 v4.32.2 설치가 실제 가능했던
`user/project/local/managed` scope, default/non-empty `CLAUDE_CONFIG_DIR`, split
registry/cache/catalog-root lineage도 축으로 갖는다. Every marketplace row에서
`source.ref` absent/custom-main/historical-tag-or-commit/fork-local, refreshed/stale disk catalog,
pre-refresh process 0/running-old-memo/cold-process generation,
auto-update on/off, refresh success/failure,
actual `>600s`, two complete restarts, discovered skill set과 passive updater copy를 검증하고,
every clone-host row에서는 inert-control first-open differential과 published clone/setup command를
검증한다.

모든 artifact에 full Cartesian behavior run을 반복하지 않는다. 대신 every exact artifact를
ledger에 열거·취득·digest verify하고 다음 immutable projection으로 `semantic_class_id`를 만든다.

```text
marketplace updater implementation digest
marketplace resolver/cache schema digest
skill/instruction discovery implementation digest
registry/config schema identity
platform-specific behavior module/binary digest class
```

Every artifact는 static class mapping과 focused actual-host smoke를 통과해야 한다. Full
cold/stale-disk/stale-process-memory/ref/scope/config/auto-update/two-restart matrix는 every distinct semantic class ×
platform behavior class에 실행한다. Same class라는 byte/schema proof가 없거나 새/unknown digest가
나오면 blocker이며 임의 representative로 흡수하지 않는다.
공식 v4.32.2 설치가 가능했던 OS/architecture/package/version/scope/config-root lineage인데 artifact 또는
actual-host fixture를 얻을 수 없으면 live `main` promotion은 release blocker다. User-created
foreign/fork/unknown managed topology는 `HOST_TOPOLOGY_RISK_OBSERVED`/unsupported release decision과
사용자 경고로 분리하며 preservation PASS에 넣지 않는다. Switch 뒤 새 Claude Code release는 external host watcher가
같은 matrix를 실행하고, 실패 또는 미검증 동안 bridge/v4.33 rollout kill-switch와 사용자 경고를
유지한다. 이 watcher가 미래 host behavior를 소급 차단할 수 있다고 주장하지 않는다.
이 global containment matrix는 external bridge runtime acquisition의 P0 support가 exact
`darwin-arm64` canary build 하나라는 사실과 별도다. Runtime payload를 설치하지 않더라도 default
catalog/skill discovery 영향을 받는 historical official platform은 matrix에서 생략할 수 없다.

이미 배포된 updater는 Contents API 또는 parse 실패 시 `LATEST=unknown`으로 두고도 clone을
계속 시도한다. 따라서 API 실패와 clone 성공이 결합되면 exact v4.32.2도 fuse tree를 in-place
rsync하고 cache를 `unknown`으로 rename하거나 sibling을 정리할 수 있다. P0는 이 경로를
transactional/no-write라고 주장하지 않는다. Quarantine이 보장하는 것은 clone source가
passive fuse여서 v4.33 development tree가 아니라는 것뿐이다. 공식 안내는 old updater 실행을
금지하고, failure-injection receipt는 `LEGACY_RISK_OBSERVED`와 final v4.33 bootstrap recovery를
기록한다.

---

## 4. Goals

### G1 — Stable Release feed

Authorized acquisition discovery는 GitHub default branch가 아니라 signed exact Release
index를 사용한다. Dynamic highest-stable public update는 P0 범위가 아니다.

### G2 — Immutable staged update

Download와 verification은 current cache 밖 staging directory에서 끝난다. Current
cache bytes는 activation decision 전까지 변하지 않는다.

### G3 — Retained rollback source

이전 installed version directory는 자동 삭제하지 않는다.

### G4 — Idempotent publisher

Publisher는 tag, draft Release, asset upload 중간에 중단돼도 동일 identity라면 이어서
완료한다. 다른 identity 충돌은 overwrite하지 않고 차단한다.

### G5 — True no-write check

`scripts/setup-codex.sh --check`는 uv 설치, venv 생성, editable install, network,
profile write보다 먼저 stdlib-only checker로 dispatch한다.

### G6 — Quarantine main and stable release discipline

별도 sunset proof 전까지 default `main`은 v4.32.2-version passive quarantine lineage에 남고,
v4.32.3/v4.33 stable은 non-default `release/v4-stable`에서만 전진한다.

### G7 — Honest acquisition

Old custom updater와 supported verified Release acquisition을 별도 protocol로 분리한다.
Legacy first hop의 destructive behavior를 bridge-owned success receipt로 포장하지 않는다.
P0는 existing v4.32.2를 자동 전환하지 않고 v4.33 bootstrap으로 명시적으로 defer한다.

---

## 5. Non-goals

Bridge는 다음을 하지 않는다.

1. PR #13 native controller나 Codex plugin을 포함하지 않는다.
2. existing Codex profile, Codex direct MCP, marketplace, AGENTS, personal skill을 migration하지
   않는다. Claude global `mcpServers.samvil-mcp` row는 exact stock lineage여도 P0에서
   remove/rewrite하지 않는다.
3. Claude cache 또는 legacy source tree를 자동 정리하지 않는다.
4. project seed, state, SQLite schema를 migration하지 않는다.
5. arbitrary system Python을 자동 신뢰하거나 dynamic package index를 사용하지 않는다.
   Supported platform에는 attested relocatable Python runtime, attested runtime builder,
   complete hash-locked dependency wheel bundle만 제공한다.
6. Claude/Codex mixed-version shared DB compatibility를 선언하지 않는다.
7. General project health, mixed-host DB, long-running process runtime attestation은 P4로
   미룬다. Bridge는 selected Claude root, verified MCP launch, pending activation만 attest한다.
   Rollback after project use와 uninstall lifecycle은 구현하지 않는다.
8. bridge 설치 여부를 v4.33 stable eligibility의 전제로 사용하지 않는다.
9. repository default branch의 bytes를 stable asset으로 신뢰하지 않는다. Default quarantine은
   version-equality fuse와 legacy source일 뿐 Release trust source가 아니다.
10. directory-source install 또는 unknown Claude registry schema를 자동 전환하지 않는다.
11. corrupt/unknown/older old-updater state의 first hop에 cache retention 또는 rollback을
    약속하지 않는다.
12. existing v4.32.2 selection/global MCP row를 P0에서 자동 변경하지 않는다.
13. GitHub default `main`에 v4.32.3/v4.33 release code를 넣거나 default를 release branch로
    바꾸지 않는다. Quarantine sunset은 별도 승인 workstream이다.
14. 신규 설치를 quarantine marketplace/raw clone으로 공식 안내하지 않는다. v4.33 bootstrap
    공개 전 신규 설치는 일시 중단하고, repository description/pinned Release/external docs는
    그 사실을 명시한다.

Bridge release index의 structured limitations는 supported platform에서 verified assets
download 뒤 MCP runtime provisioning은 offline이고, bootstrap runner에는 trusted absolute
system Python과 `gh`가 필요함을 각각 명시한다. Arbitrary platform/system Python 지원과
supported runtime asset closure를 같은 의미로 사용하지 않는다.

---

## 6. Components

```text
Trusted Release workflow
  → deterministic source archive, Release index, artifact attestations

Release publisher
  → consume trusted workflow output, draft Release, upload, verify, publish, resume

Authorized canary acquisition + in-session guard
  → exact pinned candidate download/stage/activate in isolated closed profile; installed bridge write-0 verify/defer

Canary authorization verifier
  → verify a domain-separated Ed25519 authorization before Python, runner, or protected-scope mutation

Claude selection adapter
  → classify topology, perform Claude-closed move-aside/no-replace selection, attest in a new session

Verified runtime provisioner
  → consume only attested Python, builder, and complete dependency wheel assets

Read-only setup preflight
  → inspect source and profile without mutation

Branch topology guard
  → pin default-main quarantine, separate release/v4-stable, prevent implicit-default consumption

Legacy host compatibility matrix
  → pin historical Claude package/updater/skill-discovery identities and cold/stale-disk/stale-process outcomes

External host release watcher
  → test newly published Claude identities and hold bridge/v4.33 rollout on unknown behavior
```

각 component는 독립된 module/script와 tests를 갖는다. Skill 문서는 orchestration과
user-facing copy만 담당하고 release protocol의 세부 알고리즘을 prose shell block으로
복제하지 않는다.

---

## 7. Release bundle contract

v4.32.3 published Release는 다음 assets를 갖는다.

```text
samvil-4.32.3-core.tar.gz
samvil-4.32.3-release-index.json
samvil-4.32.3-acquire.py
samvil-4.32.3-canary-authz-policy.json
samvil-4.32.3-canary-authz-verify-darwin-arm64
samvil-4.32.3-legacy-catalog.json
samvil-4.32.3-legacy-host-matrix.json
samvil_mcp-4.32.3-py3-none-any.whl
samvil-4.32.3-mcp-wheels-<platform>.tar.gz
samvil-4.32.3-python-runtime-3.12-<platform>.tar.gz
samvil-4.32.3-uv-<version>-<platform>
samvil-4.32.3-provenance-<bundle-sha256>.jsonl
```

Archive와 Release index는 exact source commit의 trusted GitHub Actions workflow에서
만들고 각각 artifact attestation을 발급한다. Local publisher가 임의로 만든 bytes를
stable asset으로 upload하지 않는다.

GitHub-hosted attestation lookup을 primary로 사용하며, provenance JSONL은 offline audit와
support를 위한 detached attestation bundle이다. Signature와 transparency metadata는
workflow rerun마다 달라질 수 있으므로 bundle은 digest-addressed asset name을 사용한다.
Bundle 자체를 Release index 안의 digest로 바인딩하면 index attestation과 순환 의존이
생기므로 그렇게 하지 않는다. Detached bundle subject set은 정확히 다음 union이다.

```text
{ exact release-index filename/digest subject }
∪ { verified index가 열거한 fixed payload filename/digest subjects }
```

Offline verifier는 out-of-band policy로 bundle signatures를 먼저 검증하고 exact expected
index filename subject 하나를 선택한다. Downloaded index digest가 그 subject와 일치한 뒤에만
index를 parse하고, 나머지 bundle subjects가 index-listed fixed payload set과 exact equal인지
검증한다. Missing/extra/index substitution은 차단한다. Online 경로도 같은 index subject와
payload subject set을 가리켜야 한다.

### 7.1 Release index schema

```json
{
  "schema_version": "samvil.release-index.v1",
  "channel": "stable",
  "release_version": "4.32.3",
  "core_version": "4.32.3",
  "tag": "v4.32.3",
  "source_repository": "insamkwon/samvil",
  "source_repository_id": 1201331511,
  "source_ref": "refs/tags/v4.32.3",
  "source_commit": "<full sha>",
  "source_tree": "<full sha>",
  "asset_name": "samvil-4.32.3-core.tar.gz",
  "asset_sha256": "<sha256>",
  "acquisition_asset_name": "samvil-4.32.3-acquire.py",
  "acquisition_asset_sha256": "<sha256>",
  "canary_authorization_policy_asset_name": "samvil-4.32.3-canary-authz-policy.json",
  "canary_authorization_policy_asset_sha256": "<sha256>",
  "canary_authorization_verifier_assets": {
    "darwin-arm64": {
      "asset_name": "samvil-4.32.3-canary-authz-verify-darwin-arm64",
      "asset_sha256": "<sha256>",
      "algorithm": "Ed25519",
      "authorization_schema": "samvil.canary-authorization.v1",
      "canonicalization": "RFC8785-JCS",
      "signature_domain": "insamkwon/samvil:samvil.bridge.canary.authorization.v1",
      "macho_policy_digest": "<sha256>",
      "code_directory_hash": "<sha256>",
      "hardened_runtime_required": true,
      "allowed_dylibs": ["/usr/lib/libSystem.B.dylib"]
    }
  },
  "legacy_catalog_asset_name": "samvil-4.32.3-legacy-catalog.json",
  "legacy_catalog_asset_sha256": "<sha256>",
  "legacy_host_matrix_asset_name": "samvil-4.32.3-legacy-host-matrix.json",
  "legacy_host_matrix_asset_sha256": "<sha256>",
  "mcp_wheel_asset_name": "samvil_mcp-4.32.3-py3-none-any.whl",
  "mcp_wheel_asset_sha256": "<sha256>",
  "dependency_lock_path": "mcp/uv.lock",
  "dependency_lock_sha256": "<sha256>",
  "runtime_requirements_path": "mcp/runtime-requirements.lock",
  "runtime_requirements_sha256": "<sha256>",
  "runtime_assets": {
    "darwin-arm64": {
      "wheel_bundle_asset_name": "samvil-4.32.3-mcp-wheels-darwin-arm64.tar.gz",
      "wheel_bundle_asset_sha256": "<sha256>",
      "python_runtime_asset_name": "samvil-4.32.3-python-runtime-3.12-darwin-arm64.tar.gz",
      "python_runtime_asset_sha256": "<sha256>",
      "runtime_builder_asset_name": "samvil-4.32.3-uv-<version>-darwin-arm64",
      "runtime_builder_asset_sha256": "<sha256>"
    }
  },
  "core_manifest_path": ".samvil-release/core-manifest.json",
  "core_manifest_sha256": "<sha256>",
  "core_tree_digest": "<sha256>",
  "archive_format": "tar.gz",
  "updater_protocol": 1,
  "minimum_updater_protocol": 1,
  "release_epoch": 1,
  "supported_platforms": ["darwin-arm64"],
  "platform_policy": {
    "darwin-arm64": {
      "os": "darwin",
      "architecture": "arm64",
      "os_version_policy": "exact_canary_builds",
      "supported_os_builds": ["<actual candidate and draft canary build>"],
      "cpu_baseline": "armv8-a",
      "python_version": "3.12.<exact>",
      "python_abi": "cp312",
      "wheel_tags": ["py3-none-any", "cp312-cp312-macosx_13_0_arm64"],
      "canary_enclave": "single_tenant_disposable_vm_dedicated_non_admin_uid"
    }
  },
  "signer_workflow": "insamkwon/samvil/.github/workflows/release-bridge.yml",
  "created_at": "<source commit RFC3339 timestamp>",
  "limitations": {
    "legacy_custom_updater_transactional": false,
    "legacy_discovery_failure_no_write": false,
    "legacy_default_branch_quarantine_required": true,
    "external_acquisition_user_supported": false,
    "external_acquisition_canary_authorization_required": true,
    "external_acquisition_single_tenant_enclave_required": true,
    "default_marketplace_plugin_installable": false,
    "newly_published_allowlisted_source_marketplace_plugin_installable": false,
    "stale_marketplace_catalog_revocable": false,
    "historical_pinned_source_revocable": false,
    "future_host_behavior_preventable": false,
    "canonical_stable_branch": "release/v4-stable",
    "github_default_branch": "main",
    "runtime_offline_supported": true,
    "runtime_offline_supported_platforms": ["darwin-arm64"],
    "bootstrap_system_python_required": true,
    "codex_native_migration_supported": false,
    "shared_db_compatibility": "unverified"
  }
}
```

`runtime_assets`, `platform_policy`, `canary_authorization_verifier_assets` key set은
`supported_platforms`와 exact equal해야 한다.
P0는 actual candidate/draft Claude canary를 같은 OS build에서 수행한 `darwin-arm64` 하나만
지원한다. Candidate와 draft receipt의 OS product/build, architecture, Python ABI, wheel tag set이
index row와 exact equal하지 않으면 publish하지 않는다. Broader macOS minimum-version support는
P2에서 oldest-supported-host canary를 확보한 뒤에만 선언한다.
각 platform row는 wheel bundle, Python runtime, runtime builder의
name/digest/version/upstream-lock identity를 모두 포함한다. Separate MCP wheel과 해당 platform
third-party wheel bundle의 union이 `mcp/uv.lock`의 direct/transitive closure와 exact
equal해야 한다. Tracked `mcp/runtime-requirements.lock`은 그 closure를 exact URL-free
name/version/hash rows로 materialize하며 source `uv.lock` digest를 header에 바인딩한다. Missing
platform row, missing dependency bytes, extra wheel, dynamic metadata resolution은 release
build와 client preflight 모두 차단한다.

`created_at`은 wall clock이 아니라 exact source commit timestamp에서 결정한다. 같은
tag/source workflow rerun은 index bytes가 같아야 한다. Core archive, wheel, wheel bundle,
Python runtime repack, runtime builder wrapper의 normalized timestamp는 commit timestamp가
아니라 fixed `SOURCE_DATE_EPOCH=0`을 사용한다. 따라서 같은 tracked tree의 PR candidate와
merge result는 commit identity가 달라도 fixed payload bytes가 같다.

Acquisition runner는 Python 3.9-compatible single-file stdlib implementation이다. PATH lookup을
사용하지 않고 supported OS policy가 지정한 absolute bootstrap interpreter를
`-I -S -B`로 실행한다. Interpreter path의 모든 component, realpath, owner/mode,
device/inode, executable digest, version/ABI를 실행 직전에 descriptor-relative로 확인한다.
Darwin P0 policy는 root-owned `/usr/bin/python3`만 허용한다. Missing/untrusted interpreter는
`PYTHON_MISSING` 또는 `PYTHON_UNTRUSTED`로 protected-scope mutation 0이다.
Runner 자체도 core/index와 같은 pinned workflow에서 attest한다. P0 release-engineering
bootstrap은 exact `v4.32.3` tag에서 runner를 temporary directory로 download하고 attestation을
검증한 뒤에만 실행한다. Dynamic latest tag 또는 unchecked pipe-to-shell은 허용하지 않는다.
이 command는 public existing/new-user install copy가 아니다.
Runner는 verified index를 받은 뒤 실행 중인 자기 file digest가
`acquisition_asset_sha256`와 같은지 다시 확인하고, 다르면 host/profile mutation 전에
차단한다.

Runner를 실행하기 전 outer copy-paste bootstrap 자체가 다음 literal policy를 강제한다.

```text
repo = insamkwon/samvil
runner asset = samvil-4.32.3-acquire.py
source ref = refs/tags/v4.32.3
source digest = <release-control canary sidecar가 바인딩한 exact peeled full SHA>
signer workflow = github.com/insamkwon/samvil/.github/workflows/release-bridge.yml
signer digest = <protected tag workflow exact full SHA>
predicate = https://slsa.dev/provenance/v1
OIDC issuer = https://token.actions.githubusercontent.com
self-hosted runner = denied
```

Bootstrap은 private `mktemp` directory mode `0700`에 exact-name runner를 받고, runner 실행
전에 `gh attestation verify`의 `--repo`, `--signer-workflow`, `--signer-digest`,
`--source-ref`, `--source-digest`, `--predicate-type`, `--cert-oidc-issuer`,
`--deny-self-hosted-runners`를 모두 지원·적용한다. JSON verification result의 certificate
identity와 subject digest가 literal policy와 exact match하지 않거나 result가 ambiguous하면
`/usr/bin/python3`를 호출하지 않는다. Same repository의 wrong workflow attestation도
pre-execution block이다. Runner 내부는 같은 policy를 다시 검증하는 second boundary다.

Outer bootstrap도 PATH-resolved `gh`, alias, function을 실행하지 않는다. P0 controlled canary
copy는 exact allowlisted absolute `gh` path를 literal로 사용하고 symlink chain, realpath,
owner/mode, group/world-writable component, device/inode, executable digest와 capability를 download
전과 verify 직전에 비교한다. Exact `gh` identity는 canary receipt에 바인딩한다. Required
capability 또는 absolute-path policy가 맞지 않으면 runner/Python invocation은 0이다. General
user bootstrap에서 이 prerequisite를 줄이는 일은 P5 범위다.

Preinstalled release-control launcher가 exact `gh`도 `DYLD_*`, `LD_*`, shell/function/alias와
debug injection environment를 제거한 `execve`로 실행하고 JSON output을 bounded pipe로 받는다.
Downloaded script나 shell profile이 `gh`/verifier launch boundary를 소유하지 않는다.

Candidate와 exact-tag stable runner는 모두 signed single-transaction canary authorization 없이는 external
acquisition을 수행하지 않는다. Authorization은 release/index/runner/verifier/policy digest, nonce,
issued-at/expiry, exact isolated fixture root와 pre-created empty state-root/lock-file
device/inode/mode, Claude config/cache parents, platform-policy identity, disposable VM/dedicated UID/
same-UID process-admission-freeze identity와 deny-write-outside sandbox receipt를 바인딩한다.
Authorization은 admission controller executable/policy digest, durable lease epoch, boot generation,
deny-policy receipt와 exact one-shot restart-handoff policy도 함께 바인딩한다.
Default/real Claude profile path 또는 missing, expired, cross-transaction
replayed, mismatched authorization은 protected-scope mutation 0 `BLOCKED_ENVIRONMENT`다.
Authorization은 public Release asset이 아니며 release-control sidecar로 canary operator에게만
전달한다. P0 stable runner를 general clean-user installer로 재사용하지 않는다.

Authorization trust boundary는 Python stdlib이나 같은 transaction이 내려받은 sidecar에
암묵적으로 맡기지 않는다. Canary 시작 전부터 protected release-control plane에 존재하는 reviewed
`canary-verifier-root.v1`은 repository id/name, signer workflow/source policy, exact verifier/policy
filename+digest, verifier Mach-O/load-command/code-directory policy digest, minimum key/revocation
epoch를 out-of-band로 pin한다. Transaction sidecar는 이 root를
narrow할 수만 있고 verifier/policy/key set을 확장할 수 없다. Outer bootstrap은 root와 sidecar가
exact match한 verifier/policy를 private temp에 받은 뒤 runner와 같은 repository/workflow/source
identity로 artifact attestation을 먼저 검증한다. 그 다음
verified self-contained `darwin-arm64` verifier가 Python과 acquisition runner를 실행하기 전에
authorization을 검증한다. Unknown verifier digest, policy substitution, verifier execution failure,
signature failure는 Python invocation과 protected-scope mutation 0이다.

Downloaded verifier를 신뢰하기 전에 실행하는 release-control launcher는 transaction asset이
아닌 preinstalled out-of-band TCB다. Launcher는 verifier를 `O_NOFOLLOW` read-only FD로 열고
arm64 Mach-O header/load-command closure, exact code-directory hash, hardened-runtime flag와
entitlements를 static parse한다. P0 verifier는 `LC_LOAD_DYLIB=/usr/lib/libSystem.B.dylib` exact
allowlist 외 dylib, `LC_RPATH`, `LC_LOAD_WEAK_DYLIB`, `LC_REEXPORT_DYLIB`,
`LC_DYLD_ENVIRONMENT`, writable/plugin search path, `get-task-allow` 또는 disabled library validation을
허용하지 않는다. Launcher는 `DYLD_*`, `LD_*`, `PYTHON*`, `BASH_ENV`, `ENV`와 loader/debug injection
environment를 제거하고, verified file을 private no-symlink/nlink-1 path mode `0555`에 no-replace
materialize한 뒤 immutable seal과 post-seal inode/digest를 확인해 absolute `execve`한다. 이 pre-exec
closure나 single-tenant process-admission freeze를 증명할 수 없으면 verifier invocation은 0이다.

`samvil.canary-authorization.v1`은 RFC 8785 JCS canonical JSON bytes 앞에
`insamkwon/samvil:samvil.bridge.canary.authorization.v1\0` domain을 붙인 message에 대한 detached
Ed25519 signature를 사용한다. Signed body는 최소 다음을 exact bind한다.

```text
schema, audience, repository id/name
candidate-or-draft mode, source ref/commit/tree
release/index/runner/verifier/policy filename and digest
transaction id, 256-bit nonce, issued-at, expiry
fixture root and state-root/lock device/inode/mode
Claude config/cache parent identities
platform-policy and disposable VM/dedicated UID/process-admission-freeze identity
admission-controller executable/policy digest, lease epoch, boot generation, deny-policy receipt
one-shot restart-handoff executable/config/pending-id policy
deny-write-outside receipt digest
key id, key epoch, policy revocation epoch
```

Audience는 exact `insamkwon/samvil:samvil.bridge.canary.v1`이다. Policy는 canonical schema,
algorithm/domain/audience/repository, max lifetime 15분, clock-skew 60초, minimum key epoch,
revocation epoch, revoked key ids와 active current/next Ed25519 public-key overlap을 바인딩한다.
Verifier는 unknown/revoked key, key epoch rollback, policy epoch mismatch, wrong audience/repository,
future-issued token, overlong lifetime와 expired token을 모두 runner 실행 전에 차단한다. Key
rotation은 current+next overlap policy와 out-of-band verifier root를 별도 review로 먼저 전진시킨
뒤에만 허용하며, revoked key를 accepted overlap으로 되살리지 않는다.

Native verifier가 external mutation process의 parent/supervisor다. PASS 뒤 runner를
`O_NOFOLLOW` read-only FD로 열어 inode/nlink/mode/digest를 검증하고 duplicate inherited FDs를 만든다.
Path를 다시 lookup하지 않고 sanitized environment에서 absolute `/usr/bin/python3 -I -S -B
/dev/fd/<script-fd>`를 실행해 Python이 exact descriptor-pinned runner bytes를 읽게 한다. Runner는
별도 inherited verification FD를 fstat/hash하고 parent verifier executable inode/digest와
authorization pipe identity를 검증한다. Canonical authorization digest, policy/verifier identity,
nonce와 transaction id는 verifier-owned anonymous pipe로 전달하고 verifier는 runner 종료까지
parent로 남는다. Direct Python runner invocation, fake receipt file/environment variable, wrong
parent, swapped runner path/inode, extra inherited writable FD는 모두 local inventory 뒤
protected-scope mutation 0이다. 이 handshake는 signature 검증을 대체하지 않고 검증된
authorization을 exact child invocation에 전달하는 capability boundary다.

Authorization nonce와 release/fixture identity는 deterministic `transaction_id`를 만든다.
Journal 전 crash는 같은 auth, exact empty state-root, unchanged inventory digest에서만 safe retry다.
Journal이 durable한 뒤 같은 auth는 그 exact `BRIDGE_PENDING_OWNED` reconcile에만 재사용할 수
있고 새 plan/newer release를 만들 수 없다. State-root lock이 concurrent use를 serialize한다.
Expiry 뒤에도 이미 durable한 transaction은 release-control이 동일 transaction id/pre/target에만
묶은 recovery-only renewal을 발급할 수 있다. `COMMITTED`, `RECOVERED_PREVIOUS` 또는 terminal
rollback 뒤 authorization은 consumed이며 다른 root/transaction replay는 차단한다.

Index의 `signer_workflow`는 검증 뒤 얻는 evidence다. Index parse 전에 사용할 trust root는
updater에 별도로 pin하며 이 필드를 자기서명 trust anchor로 사용하지 않는다.

### 7.2 Signed core manifest

Archive 안의 `.samvil-release/core-manifest.json`은 manifest 자기 자신을 제외한 immutable
core entry 전체를 canonical path order로 기록한다.

이 manifest는 publish workflow가 임의로 inject하는 untracked file이 아니라 release commit에
tracked된 release-owned file이다. External acquisition과 Release archive가 같은 manifest를
받는다. Builder는 stale manifest를 자동 regenerate하지 않고 source tree와 불일치하면
fail한다. Regeneration은 version-sync release commit에서 명시적으로 수행한다.

```json
{
  "schema_version": "samvil.core-manifest.v1",
  "core_version": "4.32.3",
  "files": [
    {"path": "AGENTS.md", "mode": "0644", "size": 123, "sha256": "<sha256>"}
  ],
  "mutable_zones": [
    {"path": "harness-feedback.log", "type": "regular", "max_bytes": 16777216}
  ],
  "generated_runtime_zones": [
    {"path": "mcp/.samvil-runtime", "runtime_manifest_required": true}
  ],
  "core_tree_digest": "<sha256>"
}
```

`core_manifest_sha256`는 manifest file bytes를, `core_tree_digest`는 normalized file
records를 바인딩한다. Existing target 또는 current root가 `CURRENT`가 되려면 다음이 모두
일치해야 한다.

- declared immutable path의 exact set, mode, size, content digest
- undeclared executable 또는 immutable entry가 없음
- extra entry는 typed `mutable_zones` 또는 verified `generated_runtime_zones` 안에만 존재함
- local activation receipt의 release/core identity가 verified index와 일치함

정상 plugin manifest만 복사한 same-version modified target은 절대 no-op으로 승인하지
않는다.

Mutable/generated zone의 모든 path component는 descriptor-relative no-follow traversal을
사용한다. Regular file은 owner, non-world-writable mode, `nlink=1`, size bounds를 enforce하고
directory는 owner/mode와 expected directory semantics를 별도로 검증한다. Bridge-generated
runtime에는 symlink, hardlink, FIFO, device를 허용하지 않고 interpreter도 target-owned
regular copy여야 한다. Legacy `mcp/.venv` symlink는 signed catalog generated-residue policy로
no-follow inventory만 하며 실행하지 않는다. Feedback log가 symlink면 read, append, support
export 모두 차단한다.

`mcp/.samvil-runtime`은 generic mutable allowlist가 아니라 transaction-owned generated
runtime이다.
Acquisition/updater는 platform-matched attested relocatable Python runtime과 attested runtime
builder, complete hash-locked wheel bundle, attested MCP wheel만으로 새 target runtime을
pre-provision한다. Dynamic PyPI/files.pythonhosted resolution, managed-Python download, PATH
builder, shared package cache는 금지한다. Builder는 sanitized environment에서
`--offline --no-index --find-links <verified-wheel-dir> --require-hashes
--requirements mcp/runtime-requirements.lock --link-mode copy
--no-cache --no-config --no-managed-python --no-python-downloads` 또는 machine-tested equivalent를
사용한다. Wheel bundle은 lock closure의 direct/transitive distribution exact set과 license/SBOM
manifest를 포함하며 누락/extra wheel 모두 차단한다.

Provisioner는 installed distribution `RECORD`, interpreter realpath/ABI/platform, copied runtime
file digests, package file digest, dependency set을 `samvil.runtime-manifest.v1`에 기록한다.
Interpreter와 package files는 target-owned copy여야 하고 regular file `nlink=1`을 요구한다.
Directory는 `nlink=1`을 요구하지 않고 descriptor-relative owner/mode와 expected child set으로
검증한다. Editable install, arbitrary `.pth`, `sitecustomize.py`, `usercustomize.py`, unexpected
executable은 금지한다.
Pre-existing 또는 manifest 없는 target runtime은 `CURRENT`로 승인하지 않는다.

Runtime 검사는 candidate Python/import를 실행하지 않는 signed single-file stdlib guard가
no-follow static parsing과 hashing으로 수행한다. Guard PASS 전에는 runtime executable, uv/uvx,
network, profile, project code를 실행하거나 쓰지 않는다.

### 7.3 Signed v4.32.2 legacy catalog

v4.32.2에는 published stable tag, Release index, activation receipt가 없다. P0 runner가
existing state를 mutation 없이 정확히 defer하고 P5가 같은 lineage를 이어받으려면 최소
v4.32.2 catalog가 필요하다.

```json
{
  "schema_version": "samvil.legacy-catalog.v1",
  "source_repository": "insamkwon/samvil",
  "source_repository_id": 1201331511,
  "legacy_version": "4.32.2",
  "historical_snapshots": [
    {
      "source_commit": "<full sha>",
      "source_tree": "<full sha>",
      "manifest_digest": "<sha256>"
    }
  ],
  "quarantine_fuse": {
    "distribution_kind": "default_quarantine_fuse",
    "source_ref": "refs/heads/main",
    "source_commit": "<full sha>",
    "source_tree": "<full sha>",
    "manifest_digest": "<sha256>",
    "plugin_version": "4.32.2",
    "passive_surface_digest": "<sha256>",
    "activation_policy_digest": "<tracked expected branch/ruleset/postcondition policy digest>"
  },
  "manifests": {
    "<sha256>": {
      "files": [],
      "known_residue": [],
      "generated_zones": []
    }
  }
}
```

Catalog input SSOT는 tracked `release/legacy-v4322-distributions.json`이다. Historical row는 reviewed
distribution window, exact source commit/tree, observed default-feed 또는 signed manual
distribution receipt, first/last observation, eligibility decision을 기록한다. Builder는 이
allowlist만 소비하며 `git rev-list`, "bridge parent까지 reachable", version string scan으로
history를 동적 확장하지 않는다. Bridge implementation commits, PR-only snapshots, cutoff 뒤
commit은 manifest version이 4.32.2여도 trusted legacy가 아니다. 예를 들어
`7b996f64349cadd164628793641828506e9a8afc` 같은 test branch SHA도 actual distribution
evidence가 없다면 catalog에 들어가지 않는다.

`quarantine_fuse`는 historical cutoff rule의 유일한 typed exception이다. Exactly one row만
허용하고 reviewed fuse PR/head, expected immutable default-main branch/ruleset policy,
plugin version `4.32.2`, passive manifest surface가 모두 일치해야 한다. 다른 cutoff 이후 row는
0이어야 한다. 실제 expected-old `main` ref promotion observation과 no-write canary receipt는 promotion 뒤에 생기는
release evidence sidecar이며 tracked catalog/index/core에 동적 주입하지 않는다. Publisher gate는
sidecar를 소비하되 deterministic fixed payload equality 대상과 분리한다.

Release gate는 historical ledger가 non-empty이고 모든 historical row가 cutoff 이전이며 plugin
version/tree가 exact match하고, known official default-feed snapshot이 빠지지 않았으며 exact
quarantine fuse row 하나만 존재하는지 machine-check한다. PR candidate와 post-merge build는
같은 tracked ledger를 사용하므로 merge strategy나 commit reachability가 catalog bytes를
바꾸지 않는다. Trusted builder는 allowed snapshot의 normalized per-file manifest를
deduplicate한다. Supported diagnosis는 다음 중 하나여야 한다.

- `STOCK_EXACT`: 한 catalog manifest와 exact immutable set 일치
- `KNOWN_HYBRID`: immutable base는 exact match이고 extra path/mode/digest가 catalog의
  `known_residue` 또는 typed generated-zone policy와 exact match
- `QUARANTINE_FUSE_EXACT`: exact fuse commit/tree/passive surface와 일치

Version string, folder name, mtime, partial manifest match는 provenance가 아니다. Catalog에
없는 bytes는 `USER_MODIFIED` 또는 `FOREIGN`이며 protected-scope mutation 0으로 차단한다.
세 supported diagnosis 모두 P0 mutation 권한이 아니라 `DEFERRED_TO_V433` evidence다. P2는 이
최소 catalog를 older versions, Codex installs, cross-host lineage로 확장한다.

Catalog builder는 allowed snapshots를 chronological distribution order로 replay한다. Exact old
updater semantics인 no-delete `rsync -a`, `.git`/`mcp/.venv`/`node_modules` excludes, editable
refresh, version-directory rename, sibling cleanup을 A→B와 A→B→C sequence 모두에 적용한다.
그 결과만 `known_residue`가 될 수 있다. Source B/C에서 삭제됐지만 rsync가 남긴 file,
preserved legacy venv, rename 전 root를 가리키는 generated metadata를 content/path type별로
기록한다. 임의 extra file을 residue로 일반화하지 않는다.

Legacy `generated_zones`는 `**/__pycache__/*.pyc`, known pytest/cache metadata처럼 정상 old
SessionStart/MCP가 만든 disposable state를 별도 type으로 기록한다. Regular file은
owner/mode/`nlink=1`/size, directory는 owner/mode/expected child policy, 전체 zone은
no-symlink/FIFO/device와 count/size bounds를 enforce하며 provenance/core trust에는 포함하지
않는다. Preserved old venv는 opaque generated residue로 static inventory할 뿐 interpreter
symlink나 Python을 실행하지 않는다. Exact catalog source에서 actual legacy
SessionStart/MCP를 1회 실행한 fixture가 `KNOWN_HYBRID`로 수렴해야 한다.

Catalog는 official GitHub repository identity와 `source.ref` key exact absence를 포함한 known
Claude marketplace source identity와 stock legacy
`mcpServers.samvil-mcp` row lineage도 root-tokenized template로 기록한다. Legacy hook이
rename 전에 쓴 exact row는 command/cwd가 current root가 아니라 renamed-away predecessor
root를 가리킬 수 있다. Adapter는 catalog가 증명한 source snapshot과 ordered rename lineage,
exact command/args/cwd/no-extra-field shape를 진단 receipt에만 기록하고 remove/rewrite하지
않는다. Current-root row만 요구하지 않는다. Fork/local marketplace, unknown scope,
custom MCP command/args/env는 supported legacy로 분류하지 않는다.

### 7.4 Archive allowlist and resource limits

Bundle builder는 tracked files 중 explicit allowlist만 포함한다. 최소 제외 항목은
다음이다.

- `.git`
- worktrees
- `mcp/.venv`
- `mcp/.samvil-runtime`
- any `.venv`
- caches
- node modules
- project `.samvil`
- release evidence
- untracked files
- sockets, FIFO, devices
- symlink and hardlink archive entries

Archive entry는 UTF-8 relative path의 regular file 또는 directory만 허용한다. File mode는
`0644` 또는 `0755`로 정규화한다. Duplicate path, absolute path, `..`, case-fold 또는
Unicode normalization collision은 build와 extraction 양쪽에서 차단한다.

Bridge policy constants:

- compressed asset maximum: 128 MiB
- expanded regular-file bytes maximum: 512 MiB
- single file maximum: 64 MiB
- entry count maximum: 20,000
- path depth maximum: 32
- UTF-8 path length maximum: 256 bytes
- compression ratio maximum: 200:1
- sparse entries, GNU longlink, device/FIFO, hardlink, symlink 금지
- archive format은 deterministic USTAR subset만 허용

Limit은 header preflight와 streaming extraction 양쪽에서 enforce한다. Limit 초과는 partial
target을 만들지 않고 staging을 quarantine한다.

### 7.5 Attestation policy

Updater v4.32.3에 내장하는 out-of-band trust policy는 다음이다.

```text
repository id = 1201331511
repository = insamkwon/samvil
signer workflow = insamkwon/samvil/.github/workflows/release-bridge.yml
source ref = exact discovered refs/tags/v<stable semver>
event = push
predicate = https://slsa.dev/provenance/v1
self-hosted runner = denied
```

Repository rename, transfer, workflow path 변경은 자동 추종하지 않는다. 새 signed root policy를
포함한 forward release 전까지 `BLOCKED_ENVIRONMENT`다.

Release index 자체를 parse하기 전에 index file의 attestation을 먼저 검증한다. 검증된
index는 core asset, acquisition runner, canary authorization policy/verifier, legacy catalog,
legacy host matrix, MCP wheel, dependency lock, embedded core manifest digest와 모든 supported
platform의 complete wheel bundle, relocatable Python runtime, runtime builder exact name/digest를
바인딩한다. Detached offline bundle signature는
exact release-index subject와 그 index가 열거한 fixed payload subject set의 union을 직접
바인딩한다.

```text
pinned trust policy → verified index attestation → index → all fixed release subjects
pinned trust policy → verified detached bundle → index subject ∪ fixed payload subject set
```

Verification은 최소 다음 identity를 enforce한다.

- repository
- GitHub Actions signer workflow
- source repository digest
- stable tag/ref
- artifact subject digest
- SLSA provenance predicate

Repository owner만 확인하고 signer workflow를 생략하는 약한 policy는 허용하지 않는다.

Trusted workflow 자체도 다음 supply-chain contract를 통과해야 한다.

- 모든 `uses:`는 immutable full commit SHA로 pin; mutable `@vN`, branch, latest 금지
- build job은 `contents: read`만, attestation job만 `id-token: write`와
  `attestations: write`; implicit/broad permissions 금지
- `persist-credentials: false`, self-hosted runner 금지, repository secret 전달 금지
- protected `push` tag event만 signer path로 허용; `pull_request_target`, untrusted workflow
  input, fork code, generated/untracked file 금지
- checkout exact expected SHA, clean tracked-only input, submodule/LFS policy explicit
- dependency fetch는 signed lock/hash allowlist만 허용; arbitrary `curl | sh` 금지
- build와 attestation을 분리하고 attestation job은 verified build digest exact set만 서명

Python runtime과 runtime builder upstream bytes는 tracked
`release/runtime-sources.lock.json`의 immutable URL, upstream digest, version, license/SBOM
identity에 pin한다. Workflow는 그 exact inputs만 받아 normalized Release asset을 만들며,
upstream provenance와 repack provenance를 모두 보존한다. User runtime은 GitHub Release
fixed subjects 외 URL을 fetch하지 않는다.

Workflow linter와 release gate가 이 contract를 machine-check한다. 기존 mutable action tag를
그대로 복사한 workflow는 trusted signer가 될 수 없다.

---

## 8. Bridge guard and authorized acquisition contract

In-session bridge command와 release-control acquisition runner는 shell prose가 아니라 tested
implementation을 호출하는 ultra-thin entrypoint로 유지한다.

### 8.1 Inputs

- current `CLAUDE_PLUGIN_ROOT` captured by the running Claude session
- `ClaudeSelectionAdapter` inventory and registry snapshot
- external lane only: pinned exact candidate/tag identity, GitHub repository id/name and signer
  trust policy, optional verified local bundle, noninteractive attestation-capable `gh`
- external lane only: signed single-transaction canary authorization and isolated fixture identity

`ls -td`로 가장 최근 modification time의 cache를 active install로 추측하지 않는다.
In-session current runtime root는 `CLAUDE_PLUGIN_ROOT`와 unique selected entry가 함께
증명하며 remote release discovery는 수행하지 않는다. External `EMPTY_READY`는 selected SAMVIL
entry와 cache가 정확히 0이라는 사실이 authority다. Lane별 required identity가 충족되지 않으면
read-only diagnosis 후 차단한다.

Bridge에서는 `gh`가 없거나 필요한 attestation capability가 없을 때 raw clone, unchecked
`curl`, branch archive로 fallback하지 않는다. `BLOCKED_ENVIRONMENT`와 설치 방법을
출력하고 current install을 유지한다. Version-independent v4.33 bootstrap의 dependency
reduction은 P5 범위다.

`gh`는 version string 하나가 아니라 capability probe로 검증한다. Shell alias/function은
허용하지 않고 resolved absolute regular executable의 realpath, owner/mode, device/inode,
digest, version/capability를 receipt에 바인딩한다. 모든 invocation은 sanitized environment,
`GH_PROMPT_DISABLED=1`, stdin `/dev/null`, bounded timeout을 사용한다. Reason code는 다음
enum으로 receipt에 남긴다.

```text
GH_MISSING
GH_TOO_OLD
GH_AUTH_REQUIRED
GH_SSO_REQUIRED
GH_RATE_LIMITED
NETWORK_UNREACHABLE
TLS_OR_CA_FAILURE
PROXY_FAILURE
PYTHON_MISSING
PYTHON_UNTRUSTED
RUNTIME_ASSET_MISSING
RUNTIME_ASSET_UNSUPPORTED
RUNTIME_BUILDER_MISSING
RUNTIME_BUILDER_UNSUPPORTED
WHEEL_CLOSURE_MISMATCH
```

복구 문구는 OS별 `gh` install/upgrade와 `gh auth login --hostname github.com` 명령을
제공하되 token, proxy credential, custom CA path를 출력하지 않는다. Offline bundle은
`gh attestation verify <artifact> --bundle <jsonl> --repo insamkwon/samvil` capability가
증명된 경우만 사용한다.

### 8.2 Claude selection adapter

```text
ClaudeSelectionAdapter input
  invocation mode: in-session updater | external acquisition
  current CLAUDE_PLUGIN_ROOT when in-session
  statically resolved Claude executable/package identity mapped to a tested schema adapter
  Claude config-root identity and CLAUDE_CONFIG_DIR state
  exact plugin id and installation scope
  marketplace repository/id/source identity and local catalog bytes/digest/freshness evidence
  plugin registry and Claude settings bytes + filesystem identity + digest + metadata identity
  pending activation id, pre identity, target identity

ClaudeSelectionAdapter output
  topology
  marketplace catalog state:
    REFRESHED_PAUSE_COLD | REFRESHED_PAUSE_DISK_ONLY | STALE_INSTALLABLE |
    STALE_PROCESS_MEMORY | MISSING | FOREIGN
  process quiescence/generation identity
  authoritative current runtime root
  authoritative next-restart selected-root intent
  host-derived cache root and SAMVIL state root
  registry pre/target/post digests
  supported | ambiguous classification
```

Topology enum:

```text
EMPTY_READY
BRIDGE_GUARDED_CURRENT
BRIDGE_PENDING_OWNED
LEGACY_STOCK
LEGACY_KNOWN_HYBRID
QUARANTINE_FUSE
DIRECTORY_SOURCE
MULTIPLE_CANDIDATES
FOREIGN
UNKNOWN
```

`EMPTY_READY`는 default config root와 exact user scope에서 official marketplace
repository/id/source row는 이미 존재하고 `source.ref` key는 exact absent이며, local catalog가
approved empty/pause digest의 `REFRESHED_PAUSE_COLD`이고 SAMVIL installable entry는 absent지만,
SAMVIL cache directory, plugin selection,
global MCP settings row, activation receipt가 모두 0인 상태다. Marketplace row는 read-only
input이며 P0가 create/rewrite하지 않는다. External canary에서는 release-control harness가
미리 만든 exact empty state-root directory와 lock file device/inode/mode를 single-transaction authorization이
바인딩한다. Runner는 이 root를 create/adopt하지 않고 exact identity로만 연다.
`REFRESHED_PAUSE_COLD`는 refresh 전 존재하던 모든 Claude process와 relevant open FD가 0이고,
disk pause digest를 확인한 뒤 시작한 새 process generation만 존재함을 뜻한다. Disk bytes만
맞고 pre-refresh process quiescence를 증명하지 못하면 `REFRESHED_PAUSE_DISK_ONLY`, old memo가
관찰되면 `STALE_PROCESS_MEMORY`이며 `EMPTY_READY`가 아니다. Missing/foreign marketplace 또는
state-root identity도 P5로 defer한다.

`BRIDGE_GUARDED_CURRENT`는 valid final activation receipt, signed core/runtime, canonical
plugin MCP route, exact selected root, approved published-source empty/pause catalog digest,
global SAMVIL MCP row 0, monotonic accepted-version receipt와 same-epoch
`ADMISSION_FREEZE_RELEASED` receipt가 모두 일치하는 상태다.
Receiptless bridge core, old-updater hybrid, stale global row는 이 state가 아니다.

`BRIDGE_PENDING_OWNED`는 release-owned state root, valid durable journal/pending receipt,
transaction id, pre/target identity와 observed target/selection intermediate가 exact signed
transaction과 일치하는 recovery-only state다. Normal EMPTY/current classification보다 먼저
검출한다. Truncated, foreign, mode/owner mismatch journal은 이 state가 아니며 새 plan 없이
`RECOVERY_REQUIRED`다.

Bridge updater가 새 mutation plan을 만들 수 있는 topology는 signed release-control
authorization이 있는 isolated external `EMPTY_READY`뿐이다. In-session
`BRIDGE_GUARDED_CURRENT`는 local write 0 `CURRENT` 또는 v4.33 안내만 반환하고 release
discovery/stage/selection mutation을 하지 않는다. `BRIDGE_PENDING_OWNED`는 existing external
canary transaction의 reconcile만 허용한다. `LEGACY_STOCK`, `LEGACY_KNOWN_HYBRID`,
`QUARANTINE_FUSE`는 signed catalog diagnosis 뒤 protected-scope mutation 0
`DEFERRED_TO_V433`다. `DIRECTORY_SOURCE`는 contributor flow이므로
`BLOCKED_USER_STATE`다. 나머지도 unique ownership을 증명하지 못하므로 차단한다.

이 문서의 `protected-scope mutation 0`은 Claude plugin cache, marketplace/registry,
Claude settings, release-owned state root, user project, actual `CODEX_HOME`에 create, write,
rename, delete가 0이라는 뜻이다. Signed index/catalog diagnosis를 위한 private temporary
download는 허용하되 mode `0700`, bounded size, cleanup receipt를 요구한다.
`setup-codex.sh --check`만 temp/network까지 0인 더 강한 contract다.

P0 acquisition은 exact `user` scope만 지원한다. Runner와 registry adapter는 detected scope를
생략하거나 default로 추측하지 않는다. Project, local, managed scope는 P5 전까지
pre-mutation block이다.

P0는 Claude CLI가 보고하는 default config root만 지원한다. Non-empty custom
`CLAUDE_CONFIG_DIR`, default/custom registry split, 두 settings root가 관찰되면
protected-scope mutation 0으로 차단하고 P5 profile transaction으로 넘긴다. Actual
`CODEX_HOME`은 입력, 탐색, mutation scope가 아니다.

Marketplace registry는 plugin/marketplace name만 아니라 repository id `1201331511`,
`insamkwon/samvil`, expected GitHub source kind와 external clean canary의 `source.ref` key exact
absence를 모두 증명해야 한다. Fork, local directory, renamed/foreign marketplace와 explicit
custom ref는 runner mutation topology에서 protected-scope mutation 0으로 차단한다. Host-native
refresh containment은 별도 stale/custom-ref fixture로만 관찰한다.

Local marketplace catalog가 `STALE_INSTALLABLE`이면 otherwise-empty profile도 `EMPTY_READY`가
아니다. Runner는 refresh/install/update를 대신 실행하지 않고 protected-scope mutation 0
`DEFERRED_TO_V433`로 종료하며 `STALE_CATALOG_RISK_OBSERVED` reason을 남긴다. Existing legacy
topology에도 같은 orthogonal reason을 기록한다. Raw host install/update의 observed mutation은
runner success나 no-write PASS로 집계하지 않는다.

Disk catalog가 approved pause digest여도 running pre-refresh process 또는 old memo가 있으면
`STALE_PROCESS_MEMORY`로 분류한다. Runner는 그 process에 install/update를 요청하거나 cache를
invalidate하지 않고 protected-scope mutation 0으로 defer한다. 별도 actual two-process evidence만
`STALE_HOST_MEMORY_RISK_OBSERVED`를 만들며, observed installed bytes와 settings/selection mutation은
P5 recovery classifier의 입력이다.

Marketplace receipt가 바인딩하는 stable projection은 다음 exact semantic set이다.

```text
repository id/name
source kind and supported ref policy
resolved installLocation
approved empty/pause catalog bytes digest and disk semantic state
tracked checkout HEAD commit/tree
authoritative path owner/group/mode/ACL/xattr/flags security projection
```

`known_marketplaces.json.lastUpdated`, 그 config file의 inode, checkout mtime과
`.git/FETCH_HEAD`, lock/log 같은 operational metadata는 stable projection에서 제외한다. Exact
supported adapter가 authoritative paths를 다시 열어 security projection과 stable semantic set을
재검증한 뒤, `lastUpdated`가 same 또는 bounded monotonic advance이고 approved catalog digest가
같을 때만 정상 refresh로 허용한다. Timestamp rollback, implausible future jump, repository/ref,
installLocation, catalog digest/state, tracked HEAD/tree 또는 security projection drift는 block이다.
Process quiescence/generation은 volatile decision evidence라 stable projection에는 넣지 않지만,
각 mutation authorization 직전에 별도 exact receipt로 재검증해 `REFRESHED_PAUSE_COLD`를 만든다.

Registry adapter는 exact tested Claude executable/package identity와 schema range마다 별도
static implementation을 갖는다. Unknown field를 drop하는 generic JSON rewrite는 금지한다.
Production runner는 real profile에서 `claude plugin list`, `claude plugin update`, `claude
--version`을 포함한 opaque Claude CLI를 실행하지 않는다. Descriptor-safe raw registry/settings
parse와 already-captured in-session `CLAUDE_PLUGIN_ROOT`만 authority로 사용한다. In-session은
current root와 registry bytes의 unique selected entry를 대조한다. External acquisition은
all pre-refresh Claude processes와 relevant open FDs가 0이고 pause catalog 확인 뒤의 cold
generation만 허용한 상태에서 registry의 exact zero SAMVIL selected-entry identity를 authority로
사용하며 `CLAUDE_PLUGIN_ROOT` 또는 mtime fallback을 요구하지 않는다. Running old Claude
process, nonzero selected entry, unrecognized executable/package identity, ambiguous schema는 차단한다.

Claude settings adapter는 global `mcpServers.samvil-mcp` row가 0인 상태만 P0 mutation
eligible로 인정한다. Signed legacy catalog가 current/stale stock row ownership을 증명해도
진단 결과만 `DEFERRED_TO_V433`로 반환하며 remove/rewrite하지 않는다. Bridge canonical route는
signed plugin `.mcp.json` 하나다. Custom/foreign row는 `BLOCKED_USER_STATE`다.

Journal, lock, accepted-version receipt는 adapter가 증명한 Claude selection surface
밖의 release-owned `.samvil-state/`에 mode `0700/0600`으로 둔다. `HOME` string 또는 glob으로
state root를 추측하지 않는다. Version directory 내부나 user project에는 transaction state를
쓰지 않는다. External canary harness는 runner 전에 empty state root와 lock file을 create/fsync하고
authorization에 exact identity를 넣는다. Runner는 이를 descriptor-relative로 열 뿐 create하지
않는다. In-session lane은 valid final receipt가 이미 바인딩한 state root만 연다. Cache
namespace가 없으면 transaction journal이 planned parent/target identity를 durable하게 기록한
뒤에만 exact bridge-owned directory를 `mkdirat` no-follow로 만든다. 실패 시 recorded inode가
같고 empty인 directory만 제거할 수 있다.

Accepted-version receipt는 release epoch, exact tag/index/core/runtime/activation identity,
transaction lineage와 previous accepted high-water를 바인딩하는 monotonic trust record다. Runtime
attestation 뒤 `BRIDGE_ACCEPTANCE_INTENT`를 먼저 fsync하고 accepted-version receipt를 durable하게
전진시킨 다음에만 그 digest를 bind한 commit receipt와 ready token을 쓴다. Accepted-version receipt가
durable해진 뒤 failure는 older bridge로 automatic rollback하지 않고 exact target roll-forward 또는
`RECOVERY_REQUIRED`다. `CURRENT`는 final activation receipt뿐 아니라 accepted-version receipt까지
exact해야 하며 missing/tampered receipt를 clean/receiptless state로 adopt하지 않는다.

### 8.3 One verified installation engine

P0에는 public user update mutation lane이 없다. 유일한 mutation lane은 release-control이
소유한 isolated `EMPTY_READY` Claude-closed canary acquisition이다. Installed bridge의
in-session command는 local verification과 v4.33 안내만 제공한다.

| Lane | Authority | Release selection |
|---|---|---|
| External clean canary acquisition | all pre-refresh Claude process/open FD 0과 `REFRESHED_PAUSE_COLD`가 증명된 authorized isolated `EMPTY_READY` | runner가 pin한 exact `v4.32.3`; stage와 selection을 한 transaction에서 수행 |
| In-session bridge guard/update command | running `BRIDGE_GUARDED_CURRENT` final+accepted-version+admission-release receipts + `CLAUDE_PLUGIN_ROOT` | network/temp/profile/cache/registry write 0 `CURRENT` 또는 `DEFERRED_TO_V433`; target 선택 0 |

공통 engine은 실제 user profile에서 `claude plugin update`, old updater, rsync, editable
install을 호출하지 않는다. Exact supported CLI/schema/scope/marketplace/current
catalog/settings ownership과 registry owner/group/mode/ACL/xattr/flags identity를 read-only
classify한다. Legacy 또는 receiptless state는 여기서 `DEFERRED_TO_V433`로 끝난다. Only
authorized external canary가 verified Release core/runtime을 새 target에 stage한다. In-session
lane은 local final/accepted-version/admission-release receipt와 core/runtime/selection/catalog identity가 exact하면 write 0 `CURRENT`,
아니면 mutation 없이 `DEFERRED_TO_V433` 또는 block이다. External canary만 Claude process와
registry open-writer가 0임을 attest한 뒤 move-aside/no-replace registry transaction을 수행한다.

Opaque Claude CLI와 host updater는 production inventory/mutation primitive가 아니라 isolated
synthetic shadow-profile characterization oracle로만 사용한다. Shadow fixture는 disposable
`HOME`, `CLAUDE_CONFIG_DIR`, cache, registry, settings와 deny-write-outside sandbox를 사용해
CLI topology를 관찰하고 static adapter 결과와 대조한다. Actual user bytes나 secret-bearing
settings를 shadow CLI에 전달하지 않는다. Production real profile에서 opaque CLI invocation은
0이어야 하며, shadow에서 write event가 하나라도 관찰되거나 detached writer를 배제하지
못하면 해당 executable/schema identity는 unsupported다.

Common transaction:

1. Exact release-owned pending journal/receipt를 normal topology보다 먼저 classify하고, 있으면
   authorized external canary의 기존 transaction만 reconcile한다.
2. Pending이 없을 때 invocation을 authorized Claude-closed external canary 또는 in-session
   read-only command로 분리한다. In-session은 local identity만 검증하고 여기서 `CURRENT`,
   `DEFERRED_TO_V433` 또는 block으로 종료하며 remote probe/temp/new state-root/target/registry
   mutation은 0이다.
3. External canary는 exact single-tenant disposable VM, dedicated non-admin UID, verifier-supervised
   process tree와 root-owned durable same-UID process-admission lease를 먼저 증명한다. Lease는
   controller crash/reboot에도 deny-all로 남고 exact one-shot restart handoff까지 같은 epoch에서
   소유되어야 한다. 이어 exact supported
   CLI/schema/user scope/default config root, marketplace, cache/selection/settings/receipt ownership과
   single-transaction authorization을 classify한다.
   `EMPTY_READY` 외 topology는 signed diagnosis 뒤 protected-scope mutation 0으로 종료한다.
4. Target core와 darwin-arm64 runtime을 private same-filesystem staging에 완성하고 static
   verify한다.
5. Release-owned lock 아래 current/target/registry/settings/receipt identity를 다시 읽는다.
6. Planned parent/target creation과 registry pre/target digests를 durable journal과 pending
   receipt에 먼저 fsync한다.
7. 필요한 bridge-owned cache container를 expected-absent create하고 fully verified target을
   Darwin atomic no-replace로 install한다.
8. Root-owned admission controller가
   `ADMISSION_FREEZE_ACQUIRED(transaction_id, lease_epoch, supervisor_instance, boot_generation,
   policy_digest)`를 durable하게 만든 상태에서 dedicated UID의 새 process admission을 freeze하고 exact Claude
   process 0, verifier-supervised transaction tree 외 same-UID process 0, known background updater 0,
   registry inode를 연 writable descriptor 0과 armed directory-event observation을
   `PROFILE_QUIESCENT`로 attest한다. 증명 불가능하면 registry content/path mutation 0
   `BLOCKED_ENVIRONMENT`다.
9. Durable gate intent 뒤 pinned live inode에 platform-policy `registry_write_gate`를 적용한다.
   Gate는 new write-open/append/metadata-write를 kernel policy로 거부하고 original metadata
   projection과 transaction-only gate delta를 journal에 분리한다. Darwin `UF_IMMUTABLE`만으로
   pre-opened writable FD가 무효화된다고 가정하지 않는다. Gate 적용 뒤 writable-FD inventory와
   live digest를 다시 확인하며, 남은 held FD 하나라도 있으면 gate를 원복·검증하고
   `BLOCKED_ENVIRONMENT` 또는 원복 불명 시 `RECOVERY_REQUIRED`다.
10. Gated live inode에서 private same-filesystem content-addressed rollback snapshot을 만들고 original
    bytes/metadata projection을 검증·fsync한다. Snapshot에는 transaction-only immutable seal을
    적용하고 post-seal digest와 new write-open/write denial을 machine-test한다. Seal primitive가
    unavailable하거나 snapshot에 pre-opened FD가 있거나 post-seal drift가 있으면 live path move 전
    block한다.
11. Move critical section에서는 rename을 막는 immutable bit만 제거하되 new write-open을 막는
    read-only mode/deny-ACL gate와 same-UID process-admission freeze를 유지한다. Writable FD 0을 다시 증명한 뒤 live inode를
    expected-absent private moved-original path로 atomic no-replace rename하고 즉시 다시 seal한다.
    Sealed moved-original bytes가 sealed rollback snapshot과 다르면 live/target/snapshot/
    moved-original을 overwrite하지 않고 `RECOVERY_REQUIRED`다. Exact할 때만 target registry를
    original metadata projection + transaction-only immutable/parent-entry gate로 now-absent live
    path에 atomic no-replace install하고 parent를 fsync한다. Target live inode/path는 serving intent
    전까지 write/rename/unlink 불가능해야 한다. Race `EEXIST`도 모든 사본을 보존한다.
12. Sealed rollback snapshot과 moved-original, sealed target registry/path, exact-absent global MCP row,
    journal-bound marketplace stable projection을 `PENDING_RESTART` 직전과 finalization 직전에 다시
    검증한다. Snapshot/moved-original은 `COMMITTED` 뒤에도 P0에서 보존한다. 모두 일치하면
    `PENDING_RESTART`다.
13. Root-owned admission controller가 durable lease epoch와 sealed target/pending receipt를 다시
    검증하고 exact Claude executable/code identity, sanitized environment, config root와 pending id를
    묶은 one-shot handoff를 fsync한 뒤 새 Claude tree를 직접 spawn한다. Controller 밖 same-UID
    process는 계속 deny하며 controller/verifier/Claude parent death, boot generation drift 또는 audit
    gap은 admission을 열지 않고 `RECOVERY_REQUIRED`다. New-session guard와 finalizer가 같은 lease
    epoch/process ancestry와 sealed target core/runtime/selection/MCP process 및 marketplace stable
    projection을 attest하고 bridge acceptance intent→monotonic accepted-version receipt→그 digest를
    bind한 commit receipt→ready token을 durable하게 만든다. Serving intent를
    fsync한 뒤에만 target transaction seal을 제거하고 original metadata projection을 복원·검증한다.
    그 뒤 capability receipt와 first controlled response를 만들고, controller가 same lease epoch를
    consume해 canary baseline admission을 복원·검증한 durable release receipt까지 있어야
    `COMMITTED`다.

SIGKILL, timeout, network cut, ENOSPC, no-replace collision, registry-move-only와
target-registry-only success를 모두 fault-inject한다. External canary 중 죽으면 journal-bound sealed
rollback snapshot, moved-original, live path, target temp의 observed identity로만
restore/roll-forward하며 어느 concurrent bytes도
overwrite하지 않는다. Selection 뒤 죽어도 selected target은 fully verified signed guard를
포함하므로 new-session reconcile이 안전하게 완료 또는 `RECOVERY_REQUIRED`로 차단한다.
Current/sibling cache는 어느 failure path에서도 overwrite/delete하지 않는다.

### 8.4 State machine

```text
LOCAL_INVENTORY
  ├─ BRIDGE_PENDING_OWNED
  │    → RECONCILING
  │    → PENDING_RESTART | RECOVERED_PREVIOUS | CURRENT | RECOVERY_REQUIRED
  ├─ BRIDGE_GUARDED_CURRENT in-session
  │    → LOCAL_VERIFY_ONLY
  │    → CURRENT | DEFERRED_TO_V433 | BLOCKED_USER_STATE
  ├─ LEGACY_OR_RECEIPTLESS
  │    → INDEX_VERIFIED
  │    → LEGACY_CATALOG_VERIFIED
  │    → STATIC_CLASSIFIED
  │    → DEFERRED_TO_V433 | BLOCKED_USER_STATE
  └─ AUTHORIZED_EXTERNAL_EMPTY_READY
       → ADMISSION_FREEZE_ACQUIRED
       → RELEASE_DISCOVERED
       → INDEX_VERIFIED
       → ASSET_DOWNLOADED
       → ASSET_VERIFIED
       → STAGED
       → STAGE_VERIFIED
       → ACTIVATION_INTENT
       → PENDING_RECEIPT_DURABLE
       → TARGET_INSTALLED
       → PROFILE_QUIESCENT
       → REGISTRY_WRITE_GATED
       → ROLLBACK_SNAPSHOT_SEALED
       → MOVED_ORIGINAL_SEALED
       → TARGET_REGISTRY_SEALED
       → SELECTION_INTENT_VERIFIED
       → PENDING_RESTART
       → RESTART_HANDOFF_DURABLE
       → NEW_SESSION_TREE_ATTESTED
       → RUNTIME_ATTESTED
       → BRIDGE_ACCEPTANCE_INTENT_DURABLE
       → ACCEPTED_VERSION_RECEIPT_DURABLE
       → COMMIT_RECEIPT_DURABLE(bind accepted-version digest)
       → READY_TOKEN_DURABLE
       → SERVING_INTENT_DURABLE
       → TARGET_GATE_RELEASED
       → TOOL_SERVING_VERIFIED
       → ADMISSION_FREEZE_RELEASED
       → COMMITTED
       → CURRENT on repeat
```

Terminal results:

```text
CURRENT
COMMITTED
PENDING_RESTART
DEFERRED_TO_V433
BLOCKED_USER_STATE
BLOCKED_ENVIRONMENT
RECOVERED_PREVIOUS
RECOVERY_REQUIRED
```

`COMMITTED`는 Claude plugin core, canonical MCP route, generated runtime, selected root와 durable
accepted-version receipt와 이를 bind한 commit receipt/ready token/serving intent/capability receipt, same-epoch
`ADMISSION_FREEZE_RELEASED` receipt가 새 process에서 모두 증명된
bridge-owned clean activation만 뜻한다. General P4 runtime health를 뜻하지 않는다. Receiptless
bridge/legacy state는 adoption하지 않고 `DEFERRED_TO_V433`다.

### 8.5 Algorithm

1. Invocation을 in-session bridge command 또는 signed Claude-closed external canary/diagnosis로
   고정한다. External outer bootstrap은 literal candidate/draft sidecar로 exact `gh`, verifier,
   policy, runner와 source identities를 private temp에서 attest하고 native verifier로 authorization을
   검증한다. Verifier-supervised child handshake가 없으면 Python invocation과 protected-scope mutation은
   0이다.
2. Verified native parent가 absolute bootstrap interpreter identity를 검증하고 runner의
   `O_NOFOLLOW` read-only FD, inode/nlink/mode/digest와 inherited verification FD를 고정한 뒤 sanitized
   `/usr/bin/python3 -I -S -B /dev/fd/<script-fd>` child를 descriptor-pinned 방식으로 시작한다.
   Runner lexical path는 실행 권한이나 재조회 입력으로 사용하지 않는다. Child inherited FD set은
   stdin/stdout/stderr, exact script FD, verification FD와 authorization pipe allowlist와 exact equal해야
   하며 wrong/replaced FD, writable extra FD 또는 exec 직전 path lookup은 fail-closed다. In-session path는
   already-running signed bridge guard identity만 검증한다. External runner는 inherited
   authorization capability를 확인한 뒤에도 normal profile path를 열기 전에 fixture/state-root
   identity를 다시 대조한다.
3. Descriptor-safe로 release state-root, journal, pending/final receipt를 normal topology보다 먼저
   inspect한다. Opaque Claude CLI와 new state-root creation은 0이다.
4. Exact `BRIDGE_PENDING_OWNED`는 same canary authorization 또는 transaction-bound recovery-only
   renewal로만 reconcile한다. Journal-bound index/core/runtime, marketplace stable projection,
   sealed rollback snapshot/moved-original/live/target, settings와 receipt identity를 observed state와
   비교한다. Exact
   pre-state는 `RECOVERED_PREVIOUS`, exact selected target은 `PENDING_RESTART`, exact
   final+accepted-version+same-epoch admission-release state는
   `CURRENT`; partial/foreign/concurrent state는 어느 bytes도 overwrite하지 않고
   `RECOVERY_REQUIRED`다. Pending reconcile은 network 없이 여기서 끝난다.
5. Pending이 없으면 plugin id, scope/config root, marketplace/catalog state, registry/settings,
   cache/receipt identity를 static inspect한다. In-session `BRIDGE_GUARDED_CURRENT`는 valid
   final/accepted-version/same-epoch admission-release receipts와 exact local
   core/runtime/selection/marketplace stable projection이면 network/temp/write
   0 `CURRENT`, 아니면 mutation 없이 `DEFERRED_TO_V433` 또는 block으로 끝난다.
6. External diagnosis/canary만 absolute allowlisted `gh` identity/capability와 bounded remote
   auth/network를 검증한다. Legacy/receiptless diagnosis는 attested index/catalog를 private temp에
   받아 static classify하고 cleanup receipt와 함께 `DEFERRED_TO_V433` 또는
   `BLOCKED_USER_STATE`로 끝난다. Profile/cache/registry/settings/release-state mutation은 0이다.
7. Mutation은 exact external `EMPTY_READY`만 허용한다. Runner에 pin된 exact `v4.32.3` tag를
   resolve/peel하고 repository id/name, tag ref와 immutable source commit을 고정한다.
8. Release index를 private temp에 받고 parse 전에 exact outer trust policy로 attest한다. Schema,
   release/core version, platform, epoch/protocol과 every-fixed-subject inventory를 검증한다.
9. Core, acquisition runner, canary authorization policy/verifier, legacy catalog, legacy host matrix,
   MCP wheel, darwin-arm64 complete wheel bundle, Python runtime과 runtime builder를 download하고
   exact name/size/SHA256/
   attestation/closure를 검증한다. Archive resource preflight를 extraction 전에 끝낸다.
10. Authorization이 바인딩한 pre-created empty state root/lock을 exact device/inode/mode로 열고 OS
    lock을 획득한다. Runner는 state root/lock을 create/adopt하지 않는다.
11. Lock 아래 `EMPTY_READY`, target absence, marketplace stable projection, registry bytes와
    owner/group/mode/ACL/xattr/flags, exact-absent global MCP row, settings/receipt를 다시 inventory한다.
    Drift면 plan을 폐기한다.
12. Same-filesystem private staging에 core/runtime을 extract하고 signed manifest, exact file set,
    interpreter, `RECORD`, dependency closure, no-`.pth`/site customization과 copy-link policy를
    absolute bootstrap interpreter `-I -S -B` guard로 static verify한다.
13. Planned cache/target creation, marketplace stable projection와 volatile freshness floor,
    registry byte+metadata pre/target, exact-absent global MCP row, runtime과 receipt identity를
    durable journal/pending receipt에 먼저 쓰고 parent까지 fsync한다.
14. Missing cache container를 pinned parent FD 아래 expected-absent/no-follow로 만들고, target을
    Darwin atomic no-replace로 install한다. Equivalent primitive가 없으면 activation 전에 block한다.
15. Root-owned control-plane admission controller가 dedicated UID의 durable lease를 소유하고
    crash/reboot 기본 deny, current boot generation과 verifier process ancestry를 증명한 상태에서 exact Claude
    process 0, verifier-supervised transaction tree 외 same-UID process 0, known background updater 0,
    registry inode를 연 writable descriptor 0과 armed directory-event observation을
    `PROFILE_QUIESCENT`로 attest한다. Durable gate intent 뒤
    platform-policy `registry_write_gate`를 적용하고 writable FD/digest를 다시 검사한다.
    `UF_IMMUTABLE`이 pre-opened FD를 revoke한다고 가정하지 않으며 held FD가 하나라도 남으면
    registry content/path mutation 전에 block한다.
16. Gated live inode에서 private same-filesystem content-addressed rollback snapshot을 만들고
    original bytes/metadata projection을 검증·fsync한 뒤 transaction-only immutable seal을 적용한다.
    Post-seal digest와 new write denial을 검증하고, 지원되지 않는 filesystem/flag/ACL 또는 seal
    failure는 live move 전에 block한다.
17. Immutable bit만 잠시 제거하고 read-only mode/deny-ACL gate, same-UID process-admission freeze와 writable-FD 0을 유지한 채 live
    registry를 expected-absent private moved-original path로 atomic no-replace rename한 뒤 즉시 다시
    seal한다. Sealed moved-original과 rollback snapshot이 exact equal하지 않으면 every copy를
    보존하고 `RECOVERY_REQUIRED`다. Exact supported adapter로 SAMVIL selection 하나만 추가한 target
    bytes를 original metadata projection + transaction-only immutable/parent-entry gate로 검증·fsync하고
    now-absent live path에 atomic no-replace install한다. Target inode/path는 serving intent 전까지
    write/rename/unlink 불가능해야 한다. Race `EEXIST`도 snapshot/moved-original/new path/temp를 모두 보존한다.
18. Sealed snapshot/moved-original/target path, exact-absent global MCP row, marketplace stable
    projection이 일치하는지 `PENDING_RESTART` 직전에 재검증한다. `lastUpdated`/config inode만 bounded
    monotonic하게 바뀌고 stable projection이 같은 정상 refresh는 허용한다. Pending receipt를
    selected-intent로 쓰고 `PENDING_RESTART`를 출력한다. Snapshot/moved-original은 final
    attestation과 P0 retention 동안 보존한다.
19. `PENDING_RESTART` 뒤 root-owned admission controller는 exact durable lease/journal/sealed target을
    reconcile하고 one-shot restart handoff를 fsync한 뒤 exact Claude executable/code identity와
    sanitized environment/config root/pending id로 새 process를 직접 spawn한다. Controller 밖
    same-UID process는 계속 deny한다. 새 process의 SessionStart/MCP stdlib guard는 marketplace stable projection, bounded volatile
    freshness, journal/pending, core/runtime manifest와 canonical MCP route를 검증하기 전 runtime,
    network, profile/project code를 실행하지 않는다. Semantic/security drift면 pending 유지,
    runtime/MCP/final receipt 0 `RECOVERY_REQUIRED`다. PASS한 MCP도 처음에는
    `ATTESTATION_ONLY` capability로 시작하며 stateful tools/project/DB write와 normal tool
    advertisement는 0이다.
20. Guard PASS 뒤 verified bundled Python을 `-I -S -B`로 attestation-only exec하고 MCP startup
    receipt를 pending id에 바인딩한다. Finalizer는 state lock 아래 commit receipt 직전에 sealed
    rollback snapshot/moved-original/target identity와 zero relevant watcher events, stable projection,
    registry/settings와 volatile freshness를 다시 검증한다. Same digest의 timestamp/inode-only
    normal refresh는 허용하고 repo/ref/catalog/tree/security drift는 commit receipt 0이다. Exact할
    때 `BRIDGE_ACCEPTANCE_INTENT`를 먼저 fsync하고 release epoch/exact tag/index/core/runtime/
    activation/transaction lineage의 accepted-version receipt를 monotonic하게 durable advance한다.
    그 digest를 bind한 commit receipt를 fsync한 뒤 transaction-bound ready token을 별도 durable
    write한다. Acceptance 뒤 old bridge rollback/replay는 fail-closed다.
21. MCP는 exact commit receipt+ready token을 read-only verify한 뒤 state lock에서
    `SERVING_INTENT_DURABLE`을 fsync하기 전까지 normal tool advertisement/request를 열지 않는다.
    Intent write가 실패하면 attestation-only를 유지하고 capability를 열지 않으며 ready token은
    pre-serving reconcile에서 revoke/renew할 수 있다. Intent가 durable해진 순간부터 automatic
    activation rollback을 금지하고 exact roll-forward 또는 `RECOVERY_REQUIRED`만 허용한다. Intent
    뒤 target transaction seal을 제거하고 original metadata projection을 복원·fsync·검증한다.
    Unseal/metadata restore 또는 post-unseal identity verification이 실패하면 capability를 닫은
    roll-forward/`RECOVERY_REQUIRED`이며 rollback하지 않는다. Exact할 때도 normal capabilities를
    열지 않고 controller-bound one-shot controlled readiness probe만 실행해 serving receipt와 first
    controlled response를 기록한다.
    New-session selected root, MCP startup, serving intent와 capability receipt까지 exact한 뒤
    controller가 same lease epoch의 one-shot handoff를 consume하고 admission policy를 원래 canary
    baseline으로 복원·검증해 `ADMISSION_FREEZE_RELEASED`를 durable하게 기록한다. Release 실패나
    controller instance/boot drift는 normal admission을 열지 않고 capability를 닫은
    `RECOVERY_REQUIRED`다. Admission release 뒤 guard가 accepted-version/commit/ready/serving/
    gate/capability/admission-release full receipt set과 recovery-absent state를 다시 확인한 뒤에만
    normal tool advertisement/hooks/project write를 연다. 이 release까지 exact할 때만
    `COMMITTED`다. Previous version, sealed rollback artifacts, user modification과 sibling cache는
    automatic cleanup하지 않는다.

Host가 directory naming만으로 active version을 선택한다는 가정은 금지한다. 실제 Claude
restart test로 selected root를 증명한다. Registry update는 running session에서 수행하거나
last-read-then-rename을 CAS라고 부르지 않는다. Claude-closed quiescence와
write-gate/sealed-snapshot/move-aside/no-replace transaction만 사용한다. Same old session은 restart 후
runtime proof를 만들 수 없다.

### 8.6 Verifier-first startup and canonical MCP route

Bridge release는 current SessionStart ordering을 교체한다.

```text
.claude-plugin/plugin.json SessionStart
  → absolute trusted /usr/bin/python3 -I -S -B bridge-runtime-guard.py session-start
      → static core/journal/pending/runtime/config verification
      → no durable serving intent: attestation-only receipt, project/bootstrap hooks 0
      → no same-epoch ADMISSION_FREEZE_RELEASED: transaction probe only, project/bootstrap hooks 0
      → PASS + exact accepted-version/commit/ready/serving/gate/capability/admission-release receipts:
        project/bootstrap hooks

.claude-plugin/plugin.json every PreToolUse/PostToolUse hook
  → same absolute interpreter and bridge-runtime-guard.py hook <hook-id>
      → same static verification
      → only on PASS + exact accepted-version/ready/serving/gate/capability and same-epoch
        admission-release receipts: exact signed hook implementation

.mcp.json samvil-mcp
  → absolute trusted /usr/bin/python3 -I -S -B bridge-runtime-guard.py mcp
      → same static verification
      → no serving intent: exec attestation-only MCP, normal tool advertisement/write 0
      → commit receipt + ready token: internal serving-intent transaction only
      → exact durable serving intent: release target transaction gate, restore original metadata
      → exact target-gate-release receipt under active admission lease: exec verified bundled Python
        in transaction-scoped controlled-probe mode only; normal advertisement/write 0
      → exact controlled-response + same-epoch admission-release receipt: exec verified bundled
        python -I -S -B signed-mcp-launch.py in normal mode
          → construct only manifest-listed import paths
          → import and run verified samvil_mcp.server
```

Guard는 Python 3.9-compatible single-file stdlib code이며 plugin-local package와 candidate
runtime을 import하지 않는다.
Core manifest, guard self-digest, pending/final receipt, generated runtime manifest, effective
merged MCP config를 descriptor-relative로 검증한다. PASS 전 network, uv/uvx, runtime executable,
profile write, project `.samvil` write는 0이다.

MCP startup attestation과 tool-serving readiness는 별도 receipt다. Commit receipt와 ready token이
durable해도 `SERVING_INTENT_DURABLE` 전에는 `get_stage_envelope` 같은 read-only public tool도 normal
capability로 광고하지 않고 internal attestation/serving-intent handshake만 허용한다. Serving intent
fsync가 irreversible boundary이며, 그 뒤 capability-open/first-request receipt가 유실돼도 automatic
registry/profile rollback은 0이다. Intent write 실패는 capability closed 상태에서 pre-serving
reconcile로 수렴한다.

Plugin manifest에는 guard를 우회해 shell/Python implementation을 직접 실행하는 hook row가
없어야 한다. Old updater로 bridge core만 in-place 수신해 activation receipt/runtime이 없는
straggler도 모든 hook과 MCP가 containment-only block으로 수렴하며 project/profile code를
실행하지 않고 external acquisition 안내만 출력한다.

Bridge `.mcp.json`은 unpinned `uvx --from <source>`를 제거하고 absolute bootstrap
interpreter→signed guard→verified bundled runtime route만 사용한다. P0 mutation lane은 global
`mcpServers.samvil-mcp` row가 exact absent일 때만 허용하며 existing current/stale lineage row를
remove/rewrite하지 않는다. Effective merged config에 SAMVIL route가 둘 이상이거나
command/args/cwd/env가 signed route와 다르면 launch를 차단한다.

Verified bundled Python도 `-I -S -B`로 실행한다. Signed `signed-mcp-launch.py`는 runtime
manifest가 열거한 stdlib와 site-package directory만 `sys.path`에 구성하고, 모든 path/file
digest를 guard receipt와 다시 대조한 뒤 MCP module을 import한다. Normal `site`,
`sitecustomize`, `usercustomize`, arbitrary `.pth` 처리는 실행하지 않는다.

기존 `setup-mcp.sh`는 curl installer, editable install, global settings rewrite를 더 이상
수행하지 않는다. Guard PASS 뒤 verified runtime의 health check와 project bootstrap만 호출할
수 있다. MCP process는 startup receipt에 executable realpath, argv, cwd, wheel/module digest,
core identity, activation id를 기록한다.

Receiptless exact v4.32.3 straggler는 guard가 untrusted legacy runtime을 실행하지 않고
`DEFERRED_TO_V433`을 안내한다. P0 runner는 이를 adoption/repair하지 않는다.

### 8.7 Pinned canary and replay policy

| Observed state | Result |
|---|---|
| In-session guarded current | local write/network/temp 0 `CURRENT`; update discovery 0 |
| In-session receiptless/legacy/other | mutation 0 `DEFERRED_TO_V433` 또는 block |
| External candidate authorization | exact CI candidate identity만 허용; public user profile 금지 |
| External draft authorization | exact tag/draft asset identity만 허용; 다른 release discovery 0 |
| Draft/prerelease/channel이 authorization과 다름 | block |
| Pinned index/asset malformed | 다른 release로 fallback하지 않고 block |
| Target protocol unsupported 또는 minimum protocol이 client보다 높음 | `BLOCKED_ENVIRONMENT` |
| Release epoch가 client policy와 다르거나 accepted epoch보다 낮음 | trust-policy/replay block |
| Current version unknown | `BLOCKED_USER_STATE` |
| Matching external pending id/target | same authorization 또는 recovery-only renewal로만 reconcile |
| Receiptless exact current core/runtime/selection | protected-scope mutation 0 `DEFERRED_TO_V433` |
| Same version, same release/core/runtime identity, final receipt, accepted-version receipt and same-epoch admission-release receipt | write 0 `CURRENT` |
| Same version, different digest or repository identity | collision block |
| Repository id/name/workflow policy changed | trust-policy forward release 전까지 block |

Explicit downgrade는 bridge 범위가 아니다. P5 rollback contract에서 별도 signed command와
user confirmation을 정의한다.

### 8.8 Update failure behavior

| Failure | Required result |
|---|---|
| Release discovery unavailable | current install unchanged |
| Required `gh` capability unavailable | current install unchanged, exact prerequisite shown |
| Auth, SSO, rate limit, proxy, TLS failure | current install unchanged, structured reason code |
| Channel/ref differs from signed canary authorization | block |
| Pinned candidate index invalid | current install unchanged, do not fall back to another release |
| Unsupported updater protocol or platform | current install unchanged |
| Authorization replay or signed release identity mismatch | current install unchanged |
| Modified, foreign, directory-source, ambiguous current | profile mutation 0 |
| Download interruption | current install unchanged |
| Hash or attestation mismatch | current install unchanged, asset quarantined |
| Unsafe archive entry | current install unchanged |
| Same version, different bytes | block without overwrite |
| Staging write failure | current install unchanged |
| Runtime builder signal/timeout/partial staging | current unchanged; staging quarantine |
| Activation rename failure | observed-state recovery or `RECOVERY_REQUIRED` |
| Registry partial mutation | re-inventory, recover or `RECOVERY_REQUIRED` |
| Restart selects old or foreign root | do not report completed update; preserve pending evidence |

Authorized external canary와 in-session guard의 automatic sibling version cleanup은 모든 경우에 금지한다. 이미
배포된 legacy updater의 negative behavior를 이 문장으로 미화하지 않는다.

### 8.9 Concurrency and recovery

- Lock은 PID text sentinel이 아니라 OS file lock을 사용한다.
- 두 updater가 동시에 실행되면 하나만 activation을 수행하며 다른 하나는 write 0으로
  `BLOCKED_ENVIRONMENT`를 반환한다.
- In-session bridge command는 activation lock을 획득하거나 registry/selection을 변경하지 않는다.
  Mutation/recovery lock은 authorized isolated external canary만 사용한다.
- Mutation/recovery는 authorized single-tenant disposable VM의 dedicated non-admin UID와
  control-plane same-UID process-admission freeze에서만 가능하다. General user account, interactive
  desktop, unrelated same-UID process 또는 unverifiable process creation surface에서는 diagnosis-only다.
- Lock 획득 전 download는 가능하지만 cache-root staging과 activation은 불가능하다.
- Lock 뒤 preflight plan digest가 달라지면 기존 plan을 버리고 다시 계산한다.
- Activation journal은 mode `0600`이며 directory entry와 contents를 fsync한다.
- Cache root, `.samvil-state`, staging parent는 symlink가 아닌 owned directory인지 file
  descriptor 기준으로 확인한다.
- Extracted file은 `O_EXCL | O_NOFOLLOW`로 생성하고 file과 directory metadata를 fsync한다.
- Target parent directory FD는 lock 아래 pin하고 target absent identity를 기록한다. Install은
  atomic no-replace primitive만 사용하며 concurrent empty directory/symlink/foreign target이
  생기면 `EEXIST`로 차단한다. Plain POSIX `rename()` fallback은 금지한다.
- Plugin registry에는 filesystem identity, raw pre bytes digest, parsed pre identity, exact target
  bytes digest와 owner/group/mode/ACL/xattr-name-and-value-digest/flags pre-target metadata identity를
  journal에 기록한다. Marketplace는 stable projection과 bounded volatile freshness, Claude
  settings는 exact absence invariant를 기록한다. Public receipt에는 metadata 원문 대신 redacted
  digest만 남긴다.
- Registry last-read 뒤 direct rename을 CAS라고 부르지 않는다. Exact process/writable-descriptor
  quiescence, platform-policy write gate, post-gate writable-FD recheck와 sealed rollback snapshot을
  먼저 증명한다. `UF_IMMUTABLE` alone이 pre-opened FD write를 revoke한다고 가정하지 않는다.
- Gate는 original metadata projection과 transaction-only mode/ACL/flag delta를 journal에 분리한다.
  Immutable bit을 제거해야 하는 move critical section에서도 read-only/deny-write gate와 writable
  FD 0, dedicated-UID admission freeze를 유지한다. Live inode를 private moved-original path로 no-replace move한 뒤 즉시 seal하고
  rollback snapshot과 exact content equality를 다시 검증한다.
- Snapshot/moved-original mismatch, held FD, unsupported gate/seal, concurrent live path가 있으면
  모든 사본을 보존하고 capability를 닫은 `RECOVERY_REQUIRED`다. Exact할 때만 target temp를
  original supported metadata projection으로 byte+metadata verification/file fsync 뒤 absent live
  path에 atomic no-replace install한다. ACL/xattr/flags를 exact 보존하거나 transaction gate에서
  exact 복원할 수 없으면 live registry move 전에 block한다.
- Pending receipt는 registry selection mutation보다 먼저 durable하다. Selection 뒤 receipt
  state update 전 crash해도 new-session guard가 journal과 observed selection을 reconcile한다.
- Crash 뒤 current가 pre-state이고 target이 없으면 orphan staging만 검증 후 정리한다.
- Target이 complete verified bytes이고 durable activation intent가 있으면 roll-forward할 수
  있다.
- Target이 partial이거나 journal과 다른 bytes면 자동 overwrite/delete 없이
  `RECOVERY_REQUIRED`다.
- Registry bytes 또는 metadata를 사용자가 동시에 수정했다면 current, pre-state,
  bridge-intended state를 모두 보존하고 자동 restore하지 않는다. Recovery의 pre/target
  equality도 bytes만이 아니라 full supported metadata identity까지 포함한다.
- Pre-gate에 열린 external writable FD는 post-gate FD inventory가 blocker로 검출해야 한다.
  Gate 경계에서 write-close race가 있으면 post-gate live digest 또는 moved-original/snapshot
  equality가 검출한다. Exact enumeration을 제공하지 못하는 OS build/filesystem은 P0 지원 대상이
  아니다. Live/snapshot/moved-original/target 중 어느 사본도 overwrite/delete하지 않고
  `RECOVERY_REQUIRED`다.
- Target live inode와 directory entry는 original metadata를 아직 노출하지 않고 transaction seal을
  유지한 채 new-session attestation/commit/ready를 통과한다. `SERVING_INTENT_DURABLE` 뒤에만 seal을
  제거하고 original metadata를 restore한다. Intent 전 target write/rename/unlink 또는 host startup의
  registry write 시도는 capability 0 blocker다. Intent 뒤 unseal/restore failure는 no-rollback
  roll-forward/`RECOVERY_REQUIRED`다.
- Sealed rollback snapshot과 moved-original은 `COMMITTED` 뒤에도 P0에서 자동 삭제하지 않는다.
  P3/P5 lifecycle이 explicit rollback/retention policy를 승인하기 전에는 release-control fixture
  artifact로 보존한다. Rollback은 seal을 제거해 원본을 재사용하지 않고 snapshot에서 original
  metadata projection을 가진 새 verified copy를 absent live path에 no-replace install한다.

---

## 9. Publisher contract

현재 publisher의 tag-only 동작을 trusted workflow output을 promotion하는 상태 머신으로
확장한다.

```text
LOCAL_GATES_PASSED
  → REMOTE_GATES_PASSED
  → FUSE_PR_APPROVED
  → MAIN_QUARANTINE_RULESET_VERIFIED
  → ORIGINAL_ANCHOR_AND_STAGE_R_PINNED
  → HOST_MATRIX_AND_STALE_PROCESS_GATE_PASSED
  → MAIN_FUSE_STAGE_A_APPLIED
  → RELEASE_BRANCH_CREATED_AND_FROZEN
  → OPERATIONAL_PROPAGATION_BARRIER_PASSED
  → DEFAULT_MAIN_LIVE_CONTAINMENT_VERIFIED
  → FROZEN_BASE_HEAD_TREE_PINNED
  → CANDIDATE_PAYLOADS_VERIFIED
  → PREMERGE_RUNTIME_CANARY_PASSED
  → RELEASE_BRANCH_MERGED_AND_PINNED
  → PRETAG_PAYLOADS_VERIFIED
  → TAG_CREATED
  → TAG_BUILD_COMPLETED
  → TAG_ARTIFACTS_VERIFIED
  → DRAFT_RELEASE_READY
  → ASSETS_UPLOADED
  → REMOTE_ASSETS_VERIFIED
  → ATTESTATION_VERIFIED
  → DRAFT_RUNTIME_CANARY_PASSED
  → RELEASE_PUBLISHED
  → PUBLIC_DISCOVERY_VERIFIED
```

### 9.1 Idempotent resume

| Existing state | Action |
|---|---|
| No tag, no Release | verify frozen release/v4-stable and pretag every fixed payload/index, then create tag |
| Same tag and source identity, no Release | verify pinned tag workflow run and resume draft creation |
| Same draft, missing deterministic fixed subject | rebuild from same source; upload only if digest is exact expected identity |
| Missing provenance bundle | upload only a valid content-addressed bundle whose subject set exactly equals release-index subject ∪ every fixed payload subject listed by that verified index |
| Same asset digest | treat as completed step |
| Published identical Release | return success/no-op |
| Same tag, different commit or tree | permanent block |
| Same fixed subject name listed by index, different digest | permanent block |
| Published Release missing required asset | forward-fix release required |

Published stable tag와 asset을 delete, replace, retag하지 않는다.

### 9.2 Draft and publish boundary

- Publisher는 guard 평가 전에 release branch를 push하지 않는다. Branch/head/clean/version,
  local gate, remote gate, freeze policy를 모두 확인한 뒤에만 remote mutation을 시작한다.
- Merge 뒤 exact `release/v4-stable` commit/tree를 expected identity로 pin하고 tag, draft, upload,
  publish 각 단계 직전에 `origin/release/v4-stable`이 그대로인지 재검증한다.
- PR candidate와 post-merge pretag build의 equality 대상은 core archive, acquisition runner,
  canary authorization policy/verifier, legacy catalog, legacy host matrix, MCP wheel, dependency
  lock digest와 모든 platform wheel bundle/Python runtime/runtime builder를 포함한 every
  deterministic fixed payload다. Index와 provenance는
  ref/source identity가 달라 동일할 필요가 없다.
- Immutable remote tag는 post-merge pretag fixed payloads가 approved PR candidate와 일치하고
  deterministic tag index digest까지 계산된 뒤에만 push한다.
- Tag ruleset이 update/delete를 금지하고 publisher identity만 create할 수 있는지 먼저
  확인한다. Tag creation은 expected-absent create-only CAS이며 race로 ref가 생기면 exact
  peeled commit/tree가 같을 때만 resume하고 다르면 permanent block한다.
- PR candidate workflow는 deterministic payload digest set, clean tracked input, CI run identity,
  review receipt만 남긴다. Protected tag signer policy와 혼동되는 production artifact
  attestation을 PR/fork event에 발급하지 않는다.
- `release-bridge.yml`은 protected exact tag/source commit에서 archive와 index를 build하고
  production attestation을 발급한다.
- Publisher는 workflow run의 head SHA, source ref, conclusion을 expected release identity와
  비교한다.
- Publisher는 verified workflow artifacts를 download한 뒤 draft Release에 promotion한다.
- Core, index, acquisition runner, canary authorization policy/verifier, legacy catalog, legacy host
  matrix, MCP wheel과 darwin-arm64 wheel/runtime/builder asset은 fixed deterministic names를 사용한다.
  Attestation bundle은
  `provenance-<bundle-sha256>.jsonl` content-addressed name을 사용해 signer timestamp가
  idempotent resume을 깨지 않게 한다.
- Release는 asset upload 동안 draft 상태다.
- 모든 remote digest와 attestation verification, draft-runtime canary PASS 전에는
  publish하지 않는다.
- Published Release immutability가 적용되는 repository setting을 release gate로 확인한다.
- Publish 뒤 stable API가 exact tag와 assets를 반환하는지 다시 조회한다.

### 9.3 Two runtime canaries before exposure

첫 canary는 default-main quarantine과 `release/v4-stable` freeze가 먼저 활성화된 뒤, frozen base/head/synthetic
merge tree에서 만든 PR candidate exact payload로 수행한다. Temporary isolated Claude
profile/cache에서 다음 세 경로를 분리해 검증한다.

1. Exact deployed v4.32.2 old updater: no-ref Contents API와 `gh repo clone` default가 모두
   quarantine fuse를 가리키고 manifest version이 `4.32.2`여서 `CURRENT == LATEST`; clone,
   rsync, rename, sibling delete, cache/profile write가 0이다.
2. Newly installed quarantine fuse updater와 runner-on-legacy diagnosis: plain update는
   no-write `DEFERRED_TO_V433`; signed catalog diagnosis도 private temp cleanup 뒤 protected-scope
   mutation 0이다.
3. Exact `EMPTY_READY` candidate-mode acquisition runner: signed single-transaction authorization, exact
   isolated fixture root와 deny-write-outside sandbox를 먼저 증명한다. 그 뒤 candidate
   core/runtime을 no-replace install, Claude-closed registry write-gate/sealed-snapshot/
   move-aside/no-replace selection, preserved rollback artifacts, complete Claude 종료·재실행,
   new-session guard와 actual MCP process receipt를 검증한다.

별도 negative canary는 Contents API rate limit/parse/TLS failure 뒤 no-ref clone만 성공하는
조합을 실행한다. Old updater의 rsync/rename/sibling-delete 위험을 `LEGACY_RISK_OBSERVED`로
고정하고, clone source가 exact passive fuse이며 v4.33/release/integration bytes가 0인지 확인한다.
이 결과는 no-write PASS로 집계하지 않으며 existing-user rollout이 아니라 v4.33 bootstrap
recovery input이다.

Candidate mode는 CI-issued single-transaction nonce, isolated fixture root, deny-write-outside sandbox가
모두 있어야 하며 real/default Claude profile에서는 protected-scope mutation 0으로
차단한다. 이 canary가 PASS하지 않으면 bridge PR을 `release/v4-stable`에 merge하지 않는다.

둘째 canary는 post-merge protected tag workflow가 non-default `release/v4-stable` commit에서 만든 exact
draft assets로 수행한다. Release
admin path로 draft asset을 받아 production attestation, every fixed subject digest, candidate
payload byte equality를 확인하고 같은 `EMPTY_READY` acquisition→complete restart→MCP proof를
반복한다. Receipt의 OS version/build/architecture/Python ABI/wheel tag set은 release index의
darwin-arm64 `platform_policy` exact row와 같아야 한다.
Receipt는 tag/source, draft asset ids/digests, Claude CLI/schema, target core/runtime, pending/final
activation id를 바인딩한다. 이 canary가 PASS하지 않으면 Release는 draft로 남고 public
stable publish를 하지 않는다.

Publish 뒤 smoke는 public URL discovery, exact asset digest, repeat `CURRENT`만 확인한다.
실제 acquisition/restart의 첫 실행을 public publish 뒤로 미루지 않는다.

---

## 10. True no-write Codex preflight

현재 `scripts/setup-codex.sh`는 installer `--check` 전 uv, venv, editable install을 수행할
수 있다. Bridge에서 mode parsing 직후 stdlib-only checker로 분기한다.

```text
parse args
  ├─ --check → stdlib checker → stdout only → exit
  ├─ --dev   → explicit local contributor path
  └─ install → verified stable bundle required
```

### 10.1 `--check` contract

- network access 0
- uv invocation 0
- venv creation 0
- temp directory creation 0
- profile lock creation 0
- `HOME` write 0
- `CODEX_HOME` write 0
- repository write 0
- stdout JSON only

`--save-report PATH`를 명시한 경우에만 caller-selected path에 report를 쓴다.

Checker는 supported OS policy의 absolute bootstrap interpreter를 `-I -S -B`로 실행하는
Python 3.9-compatible single-file stdlib entrypoint다. PATH lookup, import side effect, bytecode
cache, global/user site customization을 차단하며 mode dispatch 전에는 network helper, package
manager, temp helper를 호출하지 않는다.

### 10.2 Stable source requirement

일반 install은 다음 중 하나만 허용한다.

- verified published stable bundle
- already verified local cache with matching index and attestation bundle

Working checkout의 `HEAD`는 일반 사용자 source가 아니다. Contributor가 local source를
시험하려면 `--dev --from-local`을 명시하고 user-facing receipt에 non-stable source를
표시한다.

Bridge 자체는 production Codex native activation을 수행하지 않는다. Verified source
boundary가 없으면 mutation 전에 차단한다.

---

## 11. Branch topology guard

Bridge tests와 release documentation은 다음 invariant를 enforce한다.

```text
default branch == main quarantine fuse
canonical stable Release branch == release/v4-stable and is non-default
all release/development automation uses explicit ref
PR #13 base == codex/v4.33-integration
```

CI는 repository API 또는 injected fixture metadata에서 다음을 검증한다.

- current default branch name is `main` and its ref/SHA/tree is approved quarantine lineage
- default quarantine manifest version `4.32.2`, no-write updater digest, fuse allowlist
- repository-local scheduled monitor identity and expected default SHA repository variable
- latest published stable Release identity
- current PR target branch
- explicit `release/v4-stable` tree가 approved bridge 또는 approved final stable tree인지 여부
- CI, publisher, security scan, dependency automation, docs, clone command에 implicit default-ref가
  0인지 여부

Bridge merge 전 default `main` quarantine ruleset과 `release/v4-stable` stable ruleset을 먼저
활성화한다. 이 program은 GitHub default setting을 변경하지 않으며 repository PATCH를 CAS라고
가정하지 않는다.

- `main` quarantine ruleset과 pinned `release-topology-guard`를 Stage A 전에 활성화한다. Stage A
  old-base→exact-fuse expected-old single-ref fast-forward와 semantic-fuse emergency Stage R
  fuse→pre-reviewed forward-restoration commit만 App/workflow identity별 separate one-shot
  authorization으로 허용하고 direct/force/delete/broad bypass는 0이어야 한다.
- `legacy/v4.32.2-original`은 exact pre-promotion base SHA/tree에 pin하고 update/delete/force-push/
  broad bypass 0으로 잠근 rollback anchor다.
- Default `main`은 reviewed fuse PR의 exact base/head authorization으로 reviewed head를
  server-acknowledged expected-old fast-forward한 뒤 update/delete/force-push/broad bypass 0으로
  잠근다. Merge/squash/rebase가 새 commit SHA를 만들게 두지 않는다.
- Fuse commit은 `.claude-plugin/plugin.json` version `4.32.2`, quarantine-only skills,
  hooks/MCP command 0, empty marketplace plugin catalog, installation pause copy, read-only
  scheduled default-identity monitor만 allowlist한다.
- `release/v4-stable`은 exact fuse head에서 create-only로 만들고 즉시 stable freeze ruleset으로
  잠근다. Stage B는 release branch의 fuse-base→bridge remainder PR/synthetic tree만 one-shot
  허용한다. `main`은 Stage B에서 절대 전진하지 않는다.
- Stage R restoration commit은 parent가 exact fuse head이고 tree/catalog가 immutable
  `legacy/v4.32.2-original`과 byte-identical한 signed commit으로 Stage A 전에 생성·review·pin한다.
  일반 merge/update에는 사용할 수 없고 semantic-fuse failure 또는 분류 불가능한 unexpected
  mutation incident에서만 expected fuse default `main`을 single-ref fast-forward해 no-ref와
  explicit-main consumer를 pre-promotion bytes로 복구한다.
- `main` direct push, force push, deletion 금지
- `release/v4-stable` direct push, force push, deletion 금지
- PR required
- required `release-topology-guard` status check
- release window 동안 bridge PR 외 `release/v4-stable` target change 금지
- bridge merge 직후 exact `release/v4-stable` SHA를 freeze receipt와 repository policy에 pin
- final v4.33 release 전에는 approved v4.32.x forward-fix release PR 외 release branch update를
  guard가 reject
- `v*` tag update/delete 금지와 create-only publisher identity를 tag ruleset으로 enforce

Release freeze는 candidate build나 bridge merge 뒤 수행하는 cleanup step이 아니다. Default
`main` quarantine과 release-branch freeze policy가 먼저 활성화되고 bridge PR merge가 release
window의 유일한 허용 mutation이어야 한다. Publisher는 ruleset, required check, expected PR/base/head,
synthetic merge tree, current default branch name/SHA를 GitHub API로 확인한다.
Branch topology validation 또는 enforcement가 unavailable이면 merge와 release publish를
모두 fail-closed한다.

Publisher는 ruleset `enforcement=active`뿐 아니라 bypass actor/principal 목록도 inspect한다.
Main quarantine과 release freeze ruleset은 broad admin/app bypass 0이고, 각 one-shot
authorization만 exact actor/head에 제한한다. Tag ruleset은 exact create-only publisher 외 update/delete bypass
0이어야 한다. Broad organization/admin bypass가 남아 있으면 merge/tag/publish를 차단한다.

`release-topology-guard` producer도 context 문자열만으로 신뢰하지 않는다. Ruleset은 exact
GitHub Actions App `integration_id`를 요구한다. Publisher는 check run의 app integration id,
repository/workflow id/path, protected base의 workflow source SHA, event, run/head SHA, expected
base/head와 synthetic merge tree를 검증한다. PR이 같은 이름의 workflow/check를 수정하거나
wrong App이 같은 context를 보고하면 reject한다. Base/head/workflow/synthetic tree drift는 모든
candidate receipt를 무효화하고 freeze verification부터 다시 시작한다.

Default `main`에 포함한 `.github/workflows/legacy-feed-monitor.yml`은 immutable full-SHA action,
read-only permission, protected expected-SHA repository variable로 branch name/ref/SHA/tree,
manifest version, fuse updater digest를 정기 검증하는 보조 monitor다. Default 자체가 다른
branch setting이나 `main` ref가 바뀌면 이 schedule이 사라지거나 변조될 수 있으므로 safety
monitor로 단독 사용하지 않는다.

필수 primary monitor는 repository 밖의 reviewed GitHub App 또는 organization control plane이다.
Repository id, expected default `main` ref/SHA/tree, main/release ruleset identity, repository admin
access inventory를 pin하고 repository-edited/audit-log webhook과 bounded poll을 함께 사용한다.
Drift는 즉시 release/rollout kill switch와 human alert를 열고, response runbook은 default-main
exposure window와 public API/clone evidence를 보존한 뒤 exact expected-old Stage R 또는 forward-fix
여부를 판단한다. Broad admin token과 automatic blind rewrite는 허용하지 않는다. 별도의
release-control check도 모든 merge/tag/publish 전에 같은 identity를 조회한다.

Main quarantine freeze는 default `main`이 v4.32.2-version passive lineage를 벗어나지 않는다는
뜻이다. Release freeze는 `release/v4-stable`의 v4.33 development 금지와 approved stable SHA pin을
뜻한다. Published defect의 v4.32.x forward-fix release만 새 authorization으로 release pin을
전진시킬 수 있으며, 해당 patch는 integration branch에도 즉시 반영한다.

---

## 12. Security and privacy

- Download URL과 redirect target은 GitHub release asset allowlist에 제한한다.
- Release index와 asset size에 상한을 둔다.
- Archive validator는 extraction 전에 path와 type을 전부 검사한다.
- Temporary and staging directories는 mode `0700`이다.
- Journal과 manifest cache는 mode `0600`이다.
- Proxy와 custom CA 환경은 host environment를 존중하되 secret 값을 receipt에 쓰지 않는다.
- User receipt는 active root를 `$PLUGIN_ROOT`로 tokenization한다.
- Support bundle은 opt-in이며 automatic upload가 없다.
- Failed asset은 user path를 포함하지 않는 content digest identifier로 quarantine한다.

---

## 13. Test strategy

### 13.1 Unit and property tests

- Release index schema and canonical serialization
- every fixed subject exact-set binding across index, online attestation, detached provenance
- signed core manifest exact-set and mutable-zone classification
- historical legacy ledger cutoff, exactly-one typed quarantine-fuse row, passive-surface digest,
  dynamic-history rejection
- legacy host matrix exact OS/architecture/platform-artifact/package version/digest, installation
  scope and config-root lineage coverage from declared compatibility floor or marketplace-feature
  floor through switch cutoff;
  missing/unobtainable official identity rejection
- every exact host artifact → immutable `semantic_class_id` mapping, focused class-mapping smoke,
  distinct semantic×platform behavior class coverage and unknown digest rejection
- ordered A→B and A→B→C old-updater residue/stale-row derivation
- deterministic archive ordering and metadata
- complete wheel closure, hash-locked runtime assets, runtime-builder command policy
- archive traversal, duplicate, symlink, hardlink, special-file, sparse, resource-limit rejection
- exact authorized candidate/tag selection, malformed pinned release, authorization replay and
  protocol negotiation
- same published stable release version/different digest rejection; typed catalog-only
  quarantine-fuse exception cannot become `CURRENT`
- publisher resume decision table
- updater state transitions and illegal transitions
- attestation-only → commit-receipt → ready-token → serving-intent → tool-serving capability state
  machine; ready-before-commit, capability-before-serving-intent and automatic rollback-after-intent
  rejection
- Claude selection adapter schema and topology classification
- marketplace catalog state classification, exact refreshed-pause digest, cold-process gate,
  stale cached-entry/process-memory install/downgrade observation and no-semver-guard fixture
- registry write-gate/sealed-snapshot/move-aside/no-replace state machine, original
  bytes+owner/group/mode/ACL/xattr/flags projection preservation, transaction-only gate delta,
  unsupported gate/seal/metadata pre-move block and concurrent metadata preservation
- production real-profile opaque Claude CLI invocation count 0; executable/package digest selects
  static adapter, shadow synthetic oracle only
- `gh` capability/error reason mapping with no-prompt behavior
- outer bootstrap exact repo/asset/ref/source digest/signer workflow/signer digest/predicate/OIDC/
  deny-self-hosted policy; wrong workflow or missing flag means Python invocation 0
- RFC8785/domain-separated Ed25519 canary authorization signature, wrong audience/repository,
  forged body/signature, unknown/revoked key, key-epoch rollback, current+next rotation overlap,
  policy-revocation-epoch, nonce/expiry/recovery-renewal/replay and fixture-inode/platform/sandbox
  binding
- attested native verifier/policy fixed-subject binding; direct Python runner, wrong parent digest,
  fake inherited receipt/environment and extra writable-FD invocation fail before protected-scope mutation
- out-of-band `canary-verifier-root.v1` vs transaction sidecar exact-match, sidecar widening/substitution,
  verifier/policy/key-set expansion and root-epoch rollback rejection
- native verifier arm64 Mach-O/load-command/code-directory/hardened-runtime closure; malicious
  `LC_RPATH`/weak/reexport/dyld-environment, extra dylib, disabled library validation,
  `get-task-allow`, `DYLD_*` injection and verify→exec replacement rejection
- descriptor-pinned `/dev/fd/<script-fd>` runner launch, runner path swap/inode replacement,
  wrong inherited script/verification FD and child environment injection rejection
- bootstrap interpreter absolute-path/owner/digest/`-I -S -B` policy
- plugin manifest every-hook guard routing and direct-entry bypass rejection
- quarantine fuse manifest exposes only quarantine skills; hooks/MCP registration and conventional
  auto-discovered `.mcp.json` command count 0
- quarantine fuse passive overlay exact historical skill/hook/MCP/setup/sync path set; default
  clone + legacy `scripts/setup-codex.sh`/sync/direct setup invocation의 network/temp/profile/project
  mutation 0
- root README/AGENTS/CLAUDE/GEMINI/OpenCode/Codex instruction allowlist and active chain-marker
  directive 0; each clone-consuming host의 inert-control 대비 fuse first-open differential에서
  SAMVIL-attributable MCP/network/temp/profile/project/chain-marker mutation 0
- detached provenance exact `{index subject} ∪ {index-listed fixed payload subjects}` equality;
  missing index, extra subject, index substitution rejection
- ruleset required-check exact App integration id/workflow/base/head/synthetic-tree identity and
  same-name wrong-App/PR-modified-workflow rejection
- external GitHub App/org monitor default-setting webhook loss, poll recovery, admin inventory drift,
  alert/kill-switch runbook; repo-local schedule disappearance is not a PASS
- external Claude package watcher new-version detection, exact artifact digest/class mapping smoke,
  new semantic/platform class full-matrix dispatch and bridge/v4.33 rollout kill-switch until
  compatible receipt exists
- darwin-arm64 exact OS build/ABI/wheel-tag policy equality
- structured limitations to Korean copy snapshot rendering
- no-write checker classification

### 13.2 Integration fixtures

- supported v4.32.3 guarded current + synthetic newer stable → write/network/temp 0
  `DEFERRED_TO_V433`
- already-current v4.32.3 no-op
- current core with allowed generated runtime/log zone
- normal legacy uv venv interpreter symlink and pycache as opaque generated residue
- new runtime copy-mode interpreter/package files with regular-file `nlink=1`
- malicious runtime interpreter symlink, package hardlink, FIFO, feedback-log symlink
- `sitecustomize.py`, `usercustomize.py`, arbitrary `.pth` and poisoned PATH/system site fixture
- user-modified executable, foreign manifest, directory source, ambiguous multiple candidates
- default config root, nonempty `CLAUDE_CONFIG_DIR`, split roots, project/local/managed scope
- catalog-proven current-root and stale pre-rename stock MCP row; custom row rejection
- catalog-proven stock, known-hybrid, quarantine-fuse exact state → temp cleanup and
  protected-scope mutation 0 `DEFERRED_TO_V433`
- old cache with missing or corrupt manifest/receipt
- old-updater bridge core with no runtime/receipt: every hook/MCP containment-only, project write 0
- receiptless exact bridge core/runtime/selection → no adoption/repair, `DEFERRED_TO_V433`
- exact `EMPTY_READY`: default root, user scope, official marketplace row present with
  `source.ref` key exact absent, approved `REFRESHED_PAUSE_COLD`, all pre-refresh process/open FD 0,
  SAMVIL cache/selection/global MCP row/receipt all absent
- single-tenant disposable VM/dedicated non-admin UID, verifier-supervised process tree and
  same-UID process-admission freeze exact receipt; interactive login/unrelated launch agent/new same-UID
  process race는 mutation 0 blocker
- cached old installable entry + plugin absent install, refresh network failure, recent cache
  `<30s` skip, higher v4.32.3 → cached v4.32.2 downgrade attempt, auto-update actual `>600s` and
  two complete restarts → `STALE_CATALOG_RISK_OBSERVED`, never holdback/no-write PASS
- actual process A가 old installable UI/memo entry를 적재하고 process B가 disk catalog를 approved
  pause로 refresh한 뒤 A가 install을 실행함. Cached entry/source, resolved installLocation pre/post
  inode/tree, installed tree digest, settings/selection mutation을 inert/original control과 비교함.
  Baseline-equivalent old-active 또는 exact passive no-worse는 `STALE_HOST_MEMORY_RISK_OBSERVED`;
  hybrid/active delta/downgrade/uninstall/extra selection-settings mutation은 blocker
- custom `source.ref: "main"` with exact main fuse empty catalog: host-native
  fresh-refresh containment observation; runner는 `BLOCKED_USER_STATE`
- historical immutable tag/commit with installable catalog and fork/local source → remote revoke
  불가 `PINNED_SOURCE_RISK_OBSERVED` 또는 unsupported; runner protected-scope mutation 0
- default fuse clone 뒤 legacy `scripts/setup-codex.sh`, sync-cache, direct setup/hook entrypoint를
  isolated `HOME`/`CODEX_HOME`에서 실행 → network/temp/profile/cache/settings/project mutation 0,
  `DEFERRED_TO_V433`
- default fuse checkout first-open을 exact Codex/Claude/OpenCode/Gemini clone-host matrix에서 inert
  control project와 differential 실행 → host 자체 session state를 제외한 SAMVIL-attributable
  chain marker/MCP/network/temp/profile/project mutation 0, passive pause copy only
- otherwise EMPTY-looking real/default profile without exact canary authorization →
  `BLOCKED_ENVIRONMENT`, protected-scope mutation 0
- expired/replayed/wrong-root/wrong-audience/wrong-repository/forged/unknown-key/revoked-key canary
  authorization, current+next rotation overlap and sandbox escape attempt
- direct Python runner, fake verifier receipt/environment, wrong verifier parent executable,
  verifier/policy digest or Mach-O loader closure substitution, runner path/inode swap →
  protected-scope mutation 0
- authorization crash before journal safe retry, post-journal exact pending reconcile, expiry
  recovery-only renewal, terminal consume, concurrent lock serialization
- missing/foreign marketplace and each independently nonempty cache, selection, global MCP row,
  receipt axis invalidates EMPTY before mutation
- authorization-bound pre-created empty state root/lock identity; missing/wrong inode blocks
- absent cache namespace expected-absent create, crash recovery, exact-inode empty cleanup
- target directory collision with identical bytes
- target directory collision with different bytes
- absent target raced to empty directory or symlink before no-replace
- filesystem without atomic no-replace primitive
- copied manifest plus modified executable collision
- partial download and corrupt asset
- network unavailable before download
- unauthenticated, expired auth, SSO, rate limit, no-TTY, proxy auth, TLS/custom CA failure
- shell alias/function or poisoned-PATH `gh` wrapper; resolved executable identity drift
- interrupted extraction
- interrupted activation rename
- registry partial success and partial failure
- external registry writer before move, after move and before target no-replace install
- held writable FD before gate, open-between-first-inventory-and-gate, write-close race, write after
  pending verification, unsupported filesystem flag/ACL and seal failure. Pre-opened FD는
  `UF_IMMUTABLE`로 revoke된다고 가정하지 않고 post-gate FD inventory가 block하며, race는
  live/snapshot/moved-original equality가 검출하고 every copy를 보존함
- source immutable-removal critical section에서 same-UID process creation/chmod/fchmod/open race,
  target live write/rename/unlink before serving intent, host startup registry-write attempt와
  target-gate release ENOSPC/SIGKILL. Enclave/admission freeze가 없으면 pre-move block하고 target은
  serving intent까지 sealed, intent 뒤 gate-release failure는 capability 0 no-rollback recovery
- verifier/runner parent death, admission-controller crash/IPC loss, reboot와 boot-generation drift,
  stale freeze receipt/supervisor instance, unexpected same-UID child/audit gap, handoff 기록 전·후
  SIGKILL, wrong Claude executable/config/pending id, duplicate handoff와 unrelated launch. 모든 경우
  admission은 fail-closed deny이고 일반 Claude 자동 launch 0이며 target gate를 유지함
- `SERVING_INTENT_DURABLE → TARGET_GATE_RELEASED → TOOL_SERVING_VERIFIED` 전 admission release 시도는
  거부됨. Exact tool-serving 뒤 admission release receipt 실패도 broad unfreeze 0, capability closed
  `RECOVERY_REQUIRED`
- admission-release 실패/RECOVERY_REQUIRED 상태의 SessionStart, hook과 MCP re-entry는 normal
  advertisement/project write 0이며 controller-bound one-shot controlled probe를 재사용하지 못함.
  Same-epoch admission-release full receipt set 뒤에만 normal mode가 열림
- registry mode/owner/group, POSIX ACL, supported xattr/flags preservation and unsupported metadata;
  bytes-unchanged metadata-only concurrent writer
- selection 뒤 restart 전 stale catalog swap/source.ref insertion/stable-projection drift;
  guard check 뒤 final-receipt write 전 catalog/source race → runtime/final receipt 0,
  pending `RECOVERY_REQUIRED`
- same approved catalog/tree with bounded monotonic `lastUpdated` and config inode-only refresh →
  guard/commit 유지; repository/ref/catalog/tree/security drift → block
- MCP startup receipt 뒤 bridge-acceptance intent/accepted-version receipt/pair-bound commit
  receipt/ready token/serving-intent 각 경계의 ENOSPC, SIGKILL, old-version replay,
  response loss와 concurrent first tool request; serving intent 전 normal advertisement와
  state/project/DB write 0, intent 뒤 automatic rollback 0
- two concurrent updater processes
- crash before and after activation-intent fsync
- matching pending repeat, pending-newer restart-first block, mismatched pending recovery
- truncated or foreign activation journal
- cache root, staging parent, or target swapped to symlink before mutation
- restart selecting old root
- exact authorized candidate/tag와 channel mismatch, malformed pinned candidate, replayed authorization
- current newer than discovered stable and previously accepted higher-version replay
- proxy/custom CA
- read-only cache
- low disk and injected ENOSPC
- runtime builder missing, wrong platform/OS build/ABI/wheel tag, digest mismatch, network attempt,
  wheel closure mismatch
- registry selected/response lost reconciliation and concurrent settings-row appearance fail-close
- default branch drift, fuse digest drift, implicit-default CI/publisher/docs/clone use
- default changed to branch without local monitor: external App detects, release/rollout fail-close,
  evidence preserved before authorized response
- old updater Contents API/parse/rate-limit failure + default clone success →
  `LEGACY_RISK_OBSERVED`, no v4.33 bytes, no no-write PASS
- same-name required check from wrong App, PR-modified workflow, base/head/synthetic-tree drift

### 13.2.1 Publisher remote fault matrix

Fake GitHub API와 live private draft smoke에서 다음 경계마다 fail-once와 retry를 수행한다.

- tag create request 전/후와 create success response loss
- tag workflow dispatch/poll interruption
- draft create request 전/후와 create success response loss
- each fixed subject upload 전/후, upload success response loss, same-name digest collision
- detached provenance upload/lookup interruption
- remote digest 또는 attestation lookup transient failure
- draft canary receipt upload 전/후
- publish request 전/후와 publish success response loss
- public discovery response loss

Retry는 같은 identity에서만 다음 state로 수렴해야 하고, 다른 tag/commit/tree/index 또는 any
fixed subject digest 충돌은 permanent block이다. Live smoke는 draft를 public publish하지
않고 interruption 뒤 resume하여 remote asset id/digest set과 publisher journal이 일치함을
증명한다.

### 13.3 Straggler topology fixture

Local bare repository fixture를 만든다.

```text
default main: reviewed passive fuse, manifest version 4.32.2
explicit release/v4-stable: v4.32.3 bridge candidate
integration: PR #13 or later v4.33 development
installed legacy updater: v4.32.2
```

필수 assertions:

- reviewed legacy-host-matrix가 every OS/architecture/platform artifact/package digest를 열거하고
  focused mapping smoke로 exact semantic/platform class에 매핑함. Every distinct class × documented
  scope × default/custom/split config-root/cache full matrix가 실행되고 누락 official row/class가 0임.
  Matrix 밖 historical official identity 또는 package digest drift는 switch blocker
- old updater의 no-ref Contents API와 clone이 default fuse만 보고 `CURRENT == LATEST`로
  plugin/cache mutation 0 종료
- discovery-failure clone이 fuse를 받으면 plugin manifest는 quarantine skills만 expose하고
  every legacy-host/source-row fixture의 discovered skill set도 quarantine-only이며
  plugin-owned hooks/MCP route가 0이고 plain updater와 direct setup/sync entrypoint가 no-write
  `DEFERRED_TO_V433` 반환.
- default clone의 root README/AGENTS/CLAUDE/GEMINI/host instructions가 passive allowlist이고,
  first-open differential fixture에서 SAMVIL-attributable chain marker/MCP/setup mutation 0
  Pre-existing global MCP row fixture는 별도 `LEGACY_RISK_OBSERVED` process evidence로 남김
- all pre-refresh Claude process가 종료된 뒤 시작한 exact `REFRESHED_PAUSE_COLD` process에서 new
  install은 not-found이고 installed SAMVIL
  root/cache/selection/settings mutation 0이며 existing 4.32.2 또는 bridge 4.32.3의 manual/auto
  update는 uninstall, selection rewrite, same-version refresh, downgrade를 하지 않음;
  marketplace source checkout의 expected digest change는 별도 기록함
- cached old entry + plugin absent install, refresh network failure, `<30s` recent-cache skip,
  higher v4.32.3 downgrade, auto-update `>600s`/two-restart fixture가 exact
  `STALE_CATALOG_RISK_OBSERVED` receipt로 재현됨. 이 receipt가 없거나 cold/stale 결과를 한
  PASS로 합치면 live `main` promotion과 bridge merge 0
- process A old memo → process B approved pause disk refresh → process A install actual fixture가
  `STALE_HOST_MEMORY_RISK_OBSERVED`로 재현되고 source/installLocation/installed-tree/settings/
  selection 결과가 모두 receipt에 있음. Result bytes를 passive fuse로 가정하거나 cold PASS와
  합치면 live `main` promotion과 bridge merge 0
- integration commit이 clone source가 되지 않음
- default `main`이 bridge/release 또는 PR #13 tree를 가리킬 때 negative fixture가 unsafe로 실패함
- manifest만 4.32.3으로 유지해도 post-PR-13 main tree clone을 막지 못한다는 회귀가
  고정됨
- inactive cache의 mtime이 더 최신인 multiple-cache fixture에서 old updater가 wrong root를
  고르는 위험이 재현됨
- modified active cache, custom sibling cache, directory-source install을 old updater에 넣었을
  때 overwrite/delete 위험이 `LEGACY_RISK_OBSERVED`로 기록됨
- rsync, editable refresh, rename, sibling cleanup 각 interruption point가 hybrid/stale state를
  만들 수 있음이 재현됨
- 위 negative fixture는 bridge success나 cache-retention PASS로 집계되지 않음
- exact v4.32.2 외 older/corrupt `CURRENT != LATEST` first hop은 unsupported limitation으로
  별도 기록되고 no-op PASS로 집계되지 않음
- exact v4.32.2라도 Contents API failure로 `LATEST=unknown`이 된 뒤 clone만 성공하는 조합은
  destructive fuse first hop을 재현하고 `LEGACY_RISK_OBSERVED`로 집계됨
- quarantine root와 every passive command가 network/profile/cache mutation 0으로 exact v4.33.0
  landing page만 출력하고, unauthenticated Release/pinned announcement/docs의 bootstrap copy와 digest가
  일치하며 clean/legacy/modified fixture가 expected terminal state로 수렴함

### 13.4 Verified bridge acquisition fixture

Temporary isolated Claude profiles에서 exact supported CLI versions에 대해
attested `samvil-4.32.3-acquire.py`와 one verified installation engine을 검증한다.

- single-tenant disposable VM, dedicated non-admin canary UID, no interactive login/unrelated
  launch agent, verifier-supervised process tree와 same-UID process-admission freeze가 exact함
- plugin id와 scope가 unique함
- all pre-refresh Claude processes와 relevant open FDs가 0이고 selected SAMVIL
  entry/current runtime/cache/receipt가 exact 0임
- official marketplace repository/id/source row는 이미 존재하고 `source.ref` key exact absent,
  local catalog는 approved `REFRESHED_PAUSE_COLD`이며 read-only input임
- missing marketplace, pre-existing SAMVIL cache/selection/global MCP row/receipt는 mutation 전에
  defer 또는 block
- registry pre-state와 unrelated non-SAMVIL sibling inventory를 먼저 기록함
- directory source와 obvious ambiguous multiple candidate는 network/temp/protected-scope mutation
  0으로 차단됨
- legacy diagnosis candidate의 `USER_MODIFIED`와 `FOREIGN`은 attested index/catalog를 private
  temp에서 검증한 뒤 cleanup receipt를 남기고 protected-scope mutation 0으로 차단됨
- real profile에서 opaque `claude plugin update` invocation이 0임
- real profile에서 `claude plugin list`, `claude --version`과 poisoned PATH wrapper invocation도
  0이며 descriptor-safe static adapter만 실행됨
- shadow-profile characterization command가 deny-write-outside sandbox를 벗어나지 않음
- stock/known-hybrid/quarantine-fuse는 acquisition하지 않고 protected-scope mutation 0
  `DEFERRED_TO_V433`
- target core/runtime가 verified Release manifest와 다르면 registry move intent 전에 차단됨
- target/cache parent가 absent여도 durable intent 뒤 exact create/no-replace로 수렴함
- post-gate writable FD 0, sealed content-addressed rollback snapshot, sealed moved-original과
  serving-intent 전까지 sealed target live path의 no-replace selection 뒤 next-restart intent만 보고
  `PENDING_RESTART`로 남음; settings는 read-only exact-absence invariant이고
  snapshot/moved-original은 보존됨
- 새 Claude session verifier가 exact v4.32.3 Release index/core manifest를 attest한 뒤 target
  `CLAUDE_PLUGIN_ROOT`와 core identity를 증명하고 initial activation receipt를 씀. Commit/ready 뒤
  serving intent를 fsync한 다음에만 target gate를 release/original metadata restore하고 capability를
  열며, intent 전 host registry write는 blocker임
- unsupported CLI/schema는 old skill fallback 없이 `BLOCKED_ENVIRONMENT`임

이 fixture가 실패하면 candidate merge와 public publish gate는 닫힌 채 passive containment만
유지한다.

### 13.5 No-write observation

`setup-codex.sh --check` 전후에 repository, temp, isolated fixture `HOME`, `CODEX_HOME`의
scoped Merkle digest를 비교한다. Merkle는 final-state 보조 oracle이다. Primary oracle은
deny-write/deny-network sandbox 또는 syscall/filesystem event trace이며 create-delete,
write-restore, child-process temp write까지 관찰한다. PATH trap으로 uv, git, gh, curl,
package installer 호출도 기록한다.

Hostile global/user site-package fixture는 `sitecustomize.py`가 write/network sentinel을
시도하게 한다. Runner, SessionStart guard, MCP guard, Codex checker의 absolute bootstrap
interpreter `-I -S -B` path에서 sentinel execution과 syscall event가 0이어야 한다. Verified
runtime launcher도 `-I -S -B`와 manifest-listed import path만 사용해 site customization
execution이 0이어야 한다.

Machine receipt는 최소 다음을 포함한다.

```json
{
  "write_events": 0,
  "network_connect_events": 0,
  "external_mutator_processes": 0,
  "pre_post_digest_equal": true
}
```

모든 fixture는 temporary isolated profiles를 사용한다. 실제 사용자 `HOME`,
`CODEX_HOME`, Claude cache를 test input으로 사용하지 않는다.

### 13.6 Actual runtime proof

Bridge candidate와 draft RC에서 actual Claude Code로 legacy containment와 clean acquisition을
분리해 각각 검증한다.

1. Reviewed legacy-host-matrix의 every exact OS/architecture/platform artifact/Claude package는
   acquisition/digest/class-mapping smoke를 통과한다. Every distinct semantic×platform behavior
   class에서 official no-ref, custom-main, historical tag/commit, fork/local source-row form과
   cold/stale-disk/stale-process-memory catalog axes를 실행하고 discovered SAMVIL skill set, direct setup paths,
   manual/auto updater behavior를 class digest에 바인딩한다.
2. Isolated exact v4.32.2 fixture에서 successful discovery의 old updater default-feed no-op을
   증명한다. Separate discovery-failure/clone-success fixture는 passive fuse surface와
   `LEGACY_RISK_OBSERVED`로 남긴다. All pre-refresh Claude processes를 종료한 뒤 시작한 exact
   `REFRESHED_PAUSE_COLD` process의 new install not-found와
   existing 4.32.2/bridge 4.32.3 installed root/cache/selection/settings/runtime unchanged를 manual,
   auto-update `>600s`, 두 restart에 걸쳐 확인한다. Marketplace checkout digest는 별도 기록한다.
3. Cached old entry + plugin absent install, refresh failure, recent `<30s` skip, higher v4.32.3
   downgrade와 auto-update/two-restart를 actual Claude로 실행해
   `STALE_CATALOG_RISK_OBSERVED` receipt를 만든다. 이 receipt는 PASS가 아니지만 누락되면
   main promotion과 bridge merge를 차단한다.
4. Actual process A가 old UI/memo entry를 적재하고 process B가 disk catalog를 approved pause로
   refresh한 뒤 A가 install하도록 한다. Cached source/installLocation, pre/post inode/tree,
   installed bytes와 settings/selection mutation을 inert/original control과 비교한다. Exact
   baseline-equivalent old-active 또는 exact passive no-worse만 `STALE_HOST_MEMORY_RISK_OBSERVED`와
   P5 recovery input으로 허용한다. Hybrid/active delta/downgrade/uninstall/extra selection-settings
   mutation은 `SEMANTIC_FUSE_OR_UNKNOWN`이며 main promotion과 bridge merge를 차단한다.
5. Single-tenant disposable VM/dedicated non-admin UID의 별도 isolated default Claude profile에
   `source.ref` key가 absent인 official marketplace row와 approved pause local catalog만 preseed하고,
   root-owned controller가 boot-default deny와 durable lease epoch를 활성화해 verifier-supervised tree
   외 same-UID process admission을 freeze한다. Controller crash/restart와 VM reboot 뒤에도 deny가
   유지되고 exact pending transaction만 reconcile되는지 먼저 증명한다. All pre-refresh
   processes/open FDs 0과 cold generation, SAMVIL cache/selection/global MCP row/receipt 0인
   `EMPTY_READY`를 만든다.
6. Merge 전에는 CI-verified candidate runner, publish 전에는 exact-tag production-attested
   runner를 실행한다.
7. `PENDING_RESTART` receipt와 selected-root intent를 확인한다.
8. Claude를 완전히 종료한 상태에서 root-owned controller의 exact one-shot handoff로 새 process를
   실행한다.
9. Handoff가 exact Claude executable/code identity, sanitized environment/config root, lease epoch와
   pending activation id를 bind하고 duplicate/unrelated same-UID spawn을 거부하는지 확인한다.
   New-session verifier가 v4.32.3 `CLAUDE_PLUGIN_ROOT`, core digest, pending activation id와 sealed
   target registry/path를 확인하고 MCP Python/package/settings 경로가 새 root를 resolve하는지
   확인한다. Serving intent 전 normal tool advertisement/request와 target registry write는 0이고,
   commit receipt+ready token 뒤 serving intent를 먼저 durable하게 만든 다음 target gate release/
   original metadata restoration, readiness receipt와 first controlled tool response를 증명한다.
   그 뒤에만 admission freeze가 exact canary baseline으로 release되는지 확인한다.
10. Unrelated non-SAMVIL sibling이 보존되고 bridge in-session guard repeat가 exact registry/core
   write 0 `CURRENT`인지 확인한다.
11. Candidate/draft receipt의 macOS product/build, arm64, Python ABI, wheel tags가 index
   `platform_policy` exact row와 일치하는지 확인한다.

Candidate canary는 merge 전에, draft RC canary는 public publish 전에 PASS해야 한다. Actual
runtime proof는 machine receipt와 별도 manual observation을 함께 남긴다.

---

## 14. Commit-sized implementation plan boundary

Bridge implementation plan은 quarantine fuse 1개와 bridge 8개를 각각 한 commit-sized
unit으로 구현한다.

0. v4.32.2-version passive quarantine fuse, Stage R restoration commit contract, catalog row,
   default-main no-write and single-ref recovery tests
1. Legacy distribution ledger, straggler, stale-process-memory and shadow-host topology characterization
2. Deterministic core, complete wheel/runtime bundle, signed manifest contract
3. Asset-aware resumable publisher and pre-merge stable freeze guard
4. Claude selection adapter, current classifier, next-session verifier
5. Out-of-band-rooted canary authorization, supervised external acquisition,
   write-gated/sealed-snapshot registry recovery and serving-intent boundary
6. True no-write Codex check and verified-source guard
7. Bridge fault-injection, topology, release-check integration
8. Default-main holdback/explicit-release docs, v4.32.3 version synchronization, release readiness

각 commit은 focused RED, focused GREEN, related fixtures, full
`scripts/pre-commit-check.sh` PASS를 요구한다. 한 commit에서 다음 항목의 production code를
미리 구현하지 않는다.

---

## 15. Review program

Bridge PR은 세 독립 관점으로 review한다.

### Review A — Distribution and provenance

- default branch escape
- tag/ref confusion
- asset substitution
- same-version equivocation
- prerelease selection
- downgrade, replay, protocol mismatch
- out-of-band signer trust root
- canary authorization root/key rotation/revocation and direct-runner bypass
- publisher resume

### Review B — Filesystem and interruption

- partial download
- archive attacks
- staging collision
- rename and registry partial mutation
- external registry writer, held-FD/write-gate/sealed-snapshot and move-aside/no-replace race with
  every copy preserved
- commit/ready/serving-intent/capability irreversible-boundary fault injection
- ENOSPC
- current cache preservation

### Review C — Real user compatibility

- old v4.32.2 updater straggler
- verified Release acquisition vs destructive old updater separation
- already-current bridge user
- missing `gh` or network
- proxy/custom CA
- modified, directory-source, multiple-cache, unsupported Claude schema
- Claude restart and selected root
- all pre-refresh process quiescence, cold-process invalidation and two-process stale memo behavior
- propagation-only abort vs semantic-fuse default-main Stage R recovery
- transient no-write observation
- actionable Korean failure copy

P1/P2 finding이 나오면 수정 후 세 review를 모두 다시 실행한다.

---

## 16. Release choreography

1. Current public default `main`의 approved v4.32.2 base SHA/tree와 old-updater behavior를 receipt로
   고정한다.
2. 그 base에 immutable `legacy/v4.32.2-original` rollback anchor와
   `codex/v4.32.2-quarantine-fuse`를 만든다. Bridge remainder는 final reviewed fuse head를 direct
   ancestor/base로 사용한다.
3. Fuse unit과 bridge 8-unit implementation plan을 완료한다.
4. Fuse PR은 default `main`을 대상으로 review하고, bridge remainder의 synthetic
   `release/v4-stable` tree도 같은 fuse base에서 미리 build/review한다.
5. User-visible tree 변경 전에 `main` quarantine ruleset과 pinned `release-topology-guard`를
   활성화한다. Stage A old-base→exact-fuse와 semantic emergency Stage R
   fuse→pre-reviewed restoration만 separate one-shot authorization으로 허용한다.
6. Parent=fuse, tree/catalog=exact original인 signed Stage R commit을 생성·review·pin한다.
   Release branch ruleset은 fuse head→exact bridge synthetic tree만 허용하도록 준비한다.
7. Exact fuse, synthetic `release/v4-stable` bridge/new-tag empty-catalog tree와 Stage R을 disposable
   mirror에서 characterize한다. Reviewed legacy-host-matrix는 every exact artifact를 class-map하고
   every semantic×platform class의 no-ref, custom-main, explicit-release, historical/fork/local,
   cold/stale-disk/stale-process-memory, auto/manual, refresh success/failure, `>600s`, two-restart와
   discovered skill/direct-setup axes를 실행한다.
8. `REFRESHED_PAUSE_COLD`는 new install not-found와 installed state unchanged를 증명한다.
   Cached-entry/recent/failure/fixed-ref 결과는 typed residual로 분리한다. Process A old memo →
   process B pause refresh → A install fixture는 inert/original control과 비교한다. Exact
   baseline-equivalent old-active 또는 switch-attributable executable/auto-loaded surface가 exact
   passive이고 mutation cardinality/settings/selection이 control보다 나쁘지 않은
   `PASSIVE_ONLY_NO_WORSE`만 residual로 허용한다. Hybrid, downgrade/uninstall, active surface 또는
   추가 selection/settings mutation은 `SEMANTIC_FUSE_OR_UNKNOWN` blocker다.
9. Release App이 default `main`을 expected old base에서 exact fuse head로 Stage A single-ref
   expected-old fast-forward한다. Default branch name은 계속 `main`이며 repository setting mutation은
   0이다. Ref/tree/passive/catalog identity를 확인한 뒤 Stage A authorization을 닫고 ref를 잠근다.
10. Exact fuse head에서 `release/v4-stable`을 create-only로 만들고 stable ruleset을 활성화한 뒤
    bridge remainder PR을 그 branch 대상으로 연다.
11. Bridge merge 전에 operational propagation barrier를 통과한다. 최소 3개 independent egress에서
    unauthenticated no-cache metadata/Contents API, Git HEAD와 first/last no-ref clone을 1분 cadence로
    관찰해 15분 연속 exact fuse를 요구하고 최대 30분 뒤 실패한다. 이는 global cache 소멸 증명이
    아니다. 관찰 밖 stale default-name은 여전히 `main`을 선택하고 `main`은 holdback 전체에서 fuse에
    남으므로 safety가 barrier의 전역 완전성에 의존하지 않는다. Old-base/fuse mixed bytes는
    `LEGACY_RISK_OBSERVED`지만 bridge/v4.33 bytes는 0이어야 한다.
12. Live default-main에서 successful-discovery no-op, cold not-found/installed-state unchanged,
    stale-disk/process no-worse classification과 API-failure/clone passive-source receipt를 재검증한다.
13. Frozen fuse base/bridge head/synthetic merge tree로 every deterministic fixed payload를 build하고
    CI/review/catalog/default-main sidecar receipts를 release decision에 바인딩한다.
14. Signed single-transaction authorization으로 candidate diagnosis와 exact `EMPTY_READY`
    acquisition→restart→actual MCP canary를 isolated darwin-arm64 exact OS build에서 PASS한다.
15. Main/release ruleset, default=`main`, base/head/workflow/synthetic tree가 그대로인지 재검증한다.
    Drift면 candidate와 receipt를 폐기하고 step 5부터 반복한다.
16. Bridge remainder PR을 expected fuse base/head로 `release/v4-stable`에 merge하고 exact post-merge
    tree가 approved synthetic tree와 같은지 확인한 뒤 release SHA를 freeze한다. `main`은 unchanged다.
17. Live explicit `release/v4-stable` empty catalog와 custom-main fuse matrix를 즉시 재검증한다.
    Missing receipt 또는 unexpected install/downgrade/uninstall/selection rewrite는 tag/integration을
    멈추고 pre-publish fix로 처리한다.
18. Exact release branch에서 pretag fixed payload set을 재build해 candidate와 비교한다.
19. Tag ruleset 확인 뒤 create-only로 immutable-intent `v4.32.3` tag를 생성한다.
20. Exact tag-triggered trusted Release workflow와 every fixed-payload equality/provenance를 검증한다.
21. Draft Release를 만들고 verified workflow artifacts를 promotion한 뒤 remote subjects를 재검증한다.
22. Exact tag/index/runner authorization으로 draft assets `EMPTY_READY` restart/new-session/MCP canary를
    같은 platform-policy build에서 PASS한다.
23. Stable Release publish, public discovery, repeat `CURRENT` smoke를 수행한다.
24. Frozen bridge `release/v4-stable` commit에서 `codex/v4.33-integration`을 만든다.
25. PR #13을 bridge 위로 rebase하고 integration 대상으로 retarget한다.

Step 5--8이 실패하면 Stage A를 실행하지 않는다. Stage A 뒤 propagation-only timeout이면
bridge merge를 하지 않고 default `main` fuse를 잠근 채 원인을 조사하거나 승인된 Stage R로
pre-promotion tree에 forward-restore한다. Semantic fuse defect, switch-attributable active/hybrid
delta, unexpected mutation 또는 class 불명은 `SEMANTIC_FUSE_OR_UNKNOWN`이며 Stage R으로 expected
fuse `main`을 pre-reviewed restoration commit에 single-ref fast-forward한다. No-ref와 explicit-main
fresh/stale/process fixtures가 original/no-worse result로 안정화된 incident receipt 없이는 종료하지
않는다. Stage R 또는 verification 실패는 critical kill-switch다. Step 11, 12 또는 14가 실패하면
release branch에 merge하지 않는다. Step 17 또는 18이 실패하면 tag를 만들지 않는다. Step 22가
실패하면 Release를 draft로 유지한다. Remote tag 뒤 code/payload defect는 v4.32.4 forward fix로
처리한다. Default `main` quarantine은 별도 sunset proof 전까지, release freeze는 final v4.33
stable까지 유지한다.

---

## 17. Rollback and forward fix

### Before publish

- Propagation-only failure는 GitHub default setting을 바꾸지 않는다. Bridge release merge를 멈추고
  default `main` fuse를 잠근 채 원인을 조사한다. 명시적 abort가 필요하면 expected fuse `main`을
  parent=fuse/tree=original인 pre-reviewed Stage R commit으로 single-ref forward-restore한다.
- Semantic fuse defect, switch-attributable active/hybrid delta, unexpected mutation 또는 class 불명은
  `SEMANTIC_FUSE_OR_UNKNOWN`으로 처리하고 Stage R을 즉시 실행한다. Repository metadata,
  unauthenticated/no-cache Contents API, Git HEAD와 no-ref/explicit-main fresh/stale/process fixtures가
  exact original 또는 approved no-worse result로 안정화된 incident receipt 없이는 종료를 주장하지
  않는다. Release branch/remainder는 abandon하고 어느 복구 단계든 실패하면 critical alert와
  rollout kill-switch를 유지한다.
- bridge PR revert 가능
- draft Release와 unpublished assets 정리 가능
- tag가 아직 remote에 push되지 않았다면 local tag를 폐기하고 다시 만들 수 있음
- tag가 remote에 push된 뒤 transient workflow failure면 같은 source에서 재실행함
- remote tag source/build identity 자체가 잘못됐으면 tag를 이동하지 않고 v4.32.4 forward
  fix를 사용함

### After publish

- published tag 또는 asset을 이동, 삭제, 교체하지 않는다.
- 문제가 있으면 same stable-only gate로 v4.32.4 forward fix를 만들고 새 approved SHA로
  `release/v4-stable` freeze pin을 전진시킨 뒤 integration에도 반영한다.
- Published release와 별개로 default-main fuse semantic incident가 생기면 tag/asset은 건드리지
  않고 Stage R로 `main`만 exact original tree에 forward-restore하며 release rollout kill-switch와
  incident receipt를 남긴다.
- authorized external canary가 activation 전 실패하면 current installed version을 유지한다.
- activation intent 뒤 uncertain state는 unchanged라고 주장하지 않고 `RECOVERY_REQUIRED`다.
- verified external canary acquisition은 previous version directories와 sealed rollback snapshot/
  moved-original을 automatic cleanup하지 않아야 한다. Legacy old updater에는 이 보장을 적용하지
  않는다.

PR #13은 integration에서만 존재하므로 bridge rollback 또는 forward fix가 native core를
되돌릴 필요가 없다.

---

## 18. Acceptance criteria

### AC-1 — Dual-branch quarantine topology

Bridge candidate build 전에 immutable original rollback anchor가 pre-promotion base에 pin되고,
GitHub default `main`은 reviewed v4.32.2-version passive fuse SHA/tree로 expected-old fast-forward된다.
Default branch name은 바꾸지 않는다. Non-default `release/v4-stable`은 같은 fuse head에서 시작하고
bridge remainder만 그 branch의 exact PR/head로 허용한다. Default `main`에는 v4.32.3/v4.33 code와
automatic mutation surface가 없다. Main fuse, release branch와 holdback 뒤 newly published
allowlisted tag의 marketplace catalog는 installable SAMVIL entry 0이다. Parent=fuse/tree=original
Stage R도 promotion 전에 review/pin되고 semantic failure에서는 default-main single-ref restoration
receipt가 필수다. Historical immutable tag/commit은 이 AC에 포함하지 않는다.

### AC-2 — Straggler containment

Exact v4.32.2 old updater는 successful version discovery에서 default-fuse manifest version
equality로 plugin/cache mutation 0 no-op이며 `release/v4-stable`, integration, PR #13 또는 후속
commits를 받을 수 없다. Explicit `main`도 같은 fuse다. Discovery failure/clone success 조합은 no-write AC 밖의
`LEGACY_RISK_OBSERVED`지만 clone source에는 passive fuse만 있어야 한다. 그 clone 결과의
plugin-owned hooks/MCP registration은 0이고 quarantine skill은 passive defer만 제공한다. 다만
old updater가 이미 수행한 clone/rename/delete는 no-write PASS로 집계하지 않는다.
All pre-refresh Claude processes가 종료된 뒤 시작한 exact `REFRESHED_PAUSE_COLD` process의 raw
new install만 installed SAMVIL root/cache/selection/settings mutation 0 not-found이고, marketplace
source checkout change는 별도 receipt다. Cached old entry, refresh failure, recent-cache skip,
running old process memo, historical fixed ref와 unsupported scope/config-root는 각각
`STALE_CATALOG_RISK_OBSERVED`, `STALE_HOST_MEMORY_RISK_OBSERVED`, `PINNED_SOURCE_RISK_OBSERVED`,
`HOST_TOPOLOGY_RISK_OBSERVED`로 분리된다. Running-memo result는 baseline-equivalent old-active 또는
exact passive no-worse만 residual로 허용하며 hybrid/active delta/downgrade/uninstall/extra
selection-settings mutation은 `SEMANTIC_FUSE_OR_UNKNOWN`이다. Reviewed historical host matrix와
이 risk receipts, fuse clone first-open/direct-setup no-write proof가 없으면 main promotion과 bridge
merge를 하지 않는다.

### AC-3 — Verified stable artifact

Published archive, acquisition runner, canary authorization policy/verifier, legacy catalog, legacy
host matrix, MCP wheel, darwin-arm64 wheel bundle/Python runtime/runtime builder의 release/core version,
tag, commit, tree, asset digest,
signed manifests, signer identity가 release index와 exact match한다.

### AC-4 — No in-place future update

Authorized external canary와 in-session guard는 current cache directory에 rsync 또는 overwrite하지 않는다. Old
v4.32.2 custom updater는 이 AC의 supported path가 아니다.

### AC-5 — No automatic cache deletion

Bridge-owned update는 success와 failure 모두 previous version directories를 보존한다. Exact
`EMPTY_READY` acquisition은 pre-existing SAMVIL cache가 0이어야 하며 unrelated non-SAMVIL
siblings를 보존한다. Legacy old updater negative fixture에는 적용하지 않는다.

### AC-6 — Idempotent update

동일 matching pending repeat는 receipt/selection write 0 `PENDING_RESTART`다. Valid final
receipt, monotonic accepted-version receipt, same-epoch `ADMISSION_FREEZE_RELEASED` receipt와 exact
core/runtime/selection/settings-absence repeat만 write 0 `CURRENT`다.
Receiptless exact state는 adoption/repair 없이 protected-scope mutation 0
`DEFERRED_TO_V433`다.

### AC-7 — Fail-closed collision

같은 version의 다른 bytes 또는 identity 충돌은 overwrite 없이 차단된다.

### AC-8 — True no-write check

`setup-codex.sh --check`는 syscall/event receipt에서 network, uv, venv, temp, repository,
profile mutation이 0이다.

### AC-9 — Resumable publisher

동일 tag/commit/tree/index/every-fixed-subject identity의 partial publish는 안전하게 이어서
완료된다.
Provenance bundle은 content-addressed name으로 재발급 가능한 detached evidence다. Remote
tag/workflow/draft/each asset/attestation/publish 경계의 fail-once와 success-response-loss
fixture가 같은 identity로 수렴한다.

### AC-10 — Actual Claude selection

새 Claude process의 verifier가 v4.32.3 `CLAUDE_PLUGIN_ROOT`, core digest, manifest digest,
pending activation id와 MCP Python/package/settings resolved root를 실제로 사용한다는
receipt가 있다. MCP는 durable commit receipt/ready token/serving intent 전 attestation-only이며
serving intent 전 sealed target path, normal advertisement와 state/project/DB write 0이다. Intent
뒤 target gate release/original metadata restoration receipt와 capability receipt가 존재한다. Intent
이후 gate-release/receipt loss에도 automatic rollback은 0이다. Monotonic accepted-version receipt를
bind한 commit receipt와 exact tool-serving 뒤 same-epoch `ADMISSION_FREEZE_RELEASED` receipt까지
있어야 `COMMITTED`다.

### AC-11 — Honest limitation

Release index와 receipt의 structured limitations가 legacy custom updater non-transactional,
discovery-failure destructive risk, stale disk catalog와 running process-local marketplace memo,
historical pinned source의 remote revoke 불가,
future/unsupported host behavior limitation, default quarantine와 신규 설치 일시 중단,
exact-canary-build darwin-arm64 runtime assets,
single-tenant disposable-VM canary-only acquisition, trusted system bootstrap Python prerequisite,
Codex native migration, shared DB compatibility
미완료를 표현하며 Korean copy가 이를 그대로 렌더링한다.

### AC-12 — Integration handoff

Candidate build 전에 default `main` quarantine과 `release/v4-stable` freeze가 시작되고 stable
smoke 뒤에도 유지되며 PR #13의 target이 `codex/v4.33-integration`으로 전환된다.

### AC-13 — Supported acquisition separation

v4.32.2 old `/samvil:update`, raw `claude plugin update`, marketplace install은 공식 safe
acquisition으로 안내되지 않고 production runner가 actual user profile에서 opaque host updater를
호출하지 않는다. Attested runner의 Release-owned staging/no-replace registry-transaction path는 controlled
`EMPTY_READY` canary authorization에만 사용하며 missing/replayed authorization 또는 real/default
profile에서는 fail-close한다. Authorization은 attested native verifier/policy의 RFC8785
domain-separated Ed25519 검증, audience/repository/key-epoch/revocation/expiry/replay gate와 supervised
child handshake를 통과해야 한다. Out-of-band launcher는 verifier Mach-O/hardened-loader closure를
검증하고 runner는 descriptor-pinned FD로 실행되며 direct/path-swapped Python runner는 mutation
권한을 얻지 못한다. Mutation은 single-tenant disposable VM/dedicated UID enclave에서만 가능하다.
v4.33 전 existing/new-user migration으로 확대하지 않는다.

### AC-14 — Canary before exposure

PR candidate의 legacy default no-write/defer proof와 exact `EMPTY_READY` actual Claude
acquisition/restart/MCP canary가 merge 전에 PASS하고, exact tag draft-assets EMPTY canary가
public publish 전에 PASS한다. Public stable publish 뒤에 첫 full acquisition smoke를 수행하지
않는다.

### AC-15 — Existing-user discovery without legacy mutation

Quarantine root/passive commands는 exact v4.33.0 Release landing page만 안내하고 executable latest
command를 내장하지 않는다. GA 전에 unauthenticated Release page, pinned announcement와 canonical
docs가 같은 version-independent bootstrap/digest/attestation copy를 제공하며 clean/legacy/modified
fixture가 그 한 명령으로 expected terminal state에 도달한다. Dormant installed users의 automatic
prompt를 주장하지 않고, 발견 전 runtime unchanged를 명시한다.

---

## 19. User-visible result

Existing v4.32.2 사용자는 기능 변화 없이 default-main quarantine 뒤에 남는다. Bridge는
별도 설치 prerequisite가 아니며 old `/samvil:update`를 safe transition으로 안내하지 않는다.
v4.33 bootstrap 공개 전 신규 설치도 공식적으로 일시 중단한다.

Disk catalog가 pause 상태여도 refresh 전에 실행된 Claude 창/process가 old install entry를
기억할 수 있다. 따라서 모든 Claude 창과 background process를 완전히 종료하기 전에는 raw
marketplace install/update가 안전하다고 안내하지 않으며, 공식 copy는 계속 실행 금지를 유지한다.

```text
현재 SAMVIL v4.32.2 설치는 변경하지 않았습니다.

- 기존 plugin/cache: 변경하지 않음
- Codex 설정: 변경하지 않음
- 프로젝트: 변경하지 않음

v4.33 공식 전환이 준비되면 한 번의 bootstrap 명령으로 안내합니다.
공식 안내: https://github.com/insamkwon/samvil/releases/tag/v4.33.0
GitHub 조회 실패 때 기존 updater가 위험하게 계속 진행할 수 있으므로,
지금은 old /samvil:update 또는 raw marketplace update를 실행하지 마세요.
상태: DEFERRED_TO_V433
```

Discovery-failure old clone으로 quarantine fuse를 받은 상태는 plugin-owned hook/MCP surface를
passive로 제한하고 같은 대기 copy를 출력한다. 다만 old updater의 clone/rename/delete 자체는
no-write가 아니므로 `LEGACY_RISK_OBSERVED`로 기록한다. Existing installed old updater의 literal
출력은 successful version discovery에서 `이미 최신 버전`일 수 있지만 machine proof는 default
fuse version equality와 protected-scope mutation 0을 별도로 기록한다.

Release engineering의 controlled `EMPTY_READY` canary에서만 다음 copy를 사용한다.

```text
SAMVIL v4.32.3 canary 설치 파일 준비가 끝났습니다.
아직 현재 Claude Code 세션에는 적용되지 않았습니다.

- 업데이트 채널: exact stable Release candidate
- SAMVIL 이전 cache: 없음
- unrelated plugin cache: 변경하지 않음
- Codex 설정과 프로젝트: 변경하지 않음

Claude Code를 완전히 종료한 뒤 다시 실행해 주세요.
```

Dynamic latest, raw old updater, raw host-native update, raw marketplace update, unchecked
pipe-to-shell은 existing-user 안내에 등장하지 않는다. v4.33 stable이 준비된 뒤에만 exact
version-independent bootstrap을 primary one-command path로 공개한다.

Pre-mutation block:

```text
SAMVIL 업데이트를 중단했습니다.
현재 설치는 변경하지 않았습니다.

원인: release 파일의 신원을 확인할 수 없음
```

Activation intent 뒤 uncertain state:

```text
SAMVIL 업데이트 상태를 자동으로 확정할 수 없습니다.
추가 변경을 중단했습니다.

복구 ID: <redacted transaction id>
다음 단계: /samvil:doctor --recovery
```

Bridge 완료 자체는 v4.33 native migration 완료가 아니다. v4.33 stable이 준비되면
공식 version-independent bootstrap을 별도로 안내한다.

---

## 20. Completion

Bridge workstream은 다음이 모두 끝나야 완료다.

1. quarantine fuse 1개와 bridge implementation units 8개가 각각 Task -2-attested
   invocation-exclusive kernel-quota filesystem 위의 canonical full gate를 통과함.
   현재처럼 지원 adapter가 없으면 이 항목은 미완료이고 workstream은
   `BLOCKED_ENVIRONMENT`이며, portable contract/orchestration GREEN으로 대체할 수 없음
2. bridge PR의 세 independent review에 unresolved P1/P2가 없음
3. PR candidate successful-discovery legacy no-write/defer proof, discovery-failure
   `LEGACY_RISK_OBSERVED`, stale catalog `STALE_CATALOG_RISK_OBSERVED`, historical source
   `PINNED_SOURCE_RISK_OBSERVED`, unsupported topology `HOST_TOPOLOGY_RISK_OBSERVED`, actual
   two-process stale memo의 `STALE_HOST_MEMORY_RISK_OBSERVED` receipts와 all pre-refresh process 0
   `REFRESHED_PAUSE_COLD`/`EMPTY_READY` actual Claude acquisition/restart/MCP canary가 merge 전에
   모두 존재함. Canary authorization은 out-of-band verifier root, attested policy/native verifier,
   Ed25519 audience/key-epoch/revocation/replay와 supervised-child receipt를 가짐
4. merge 전에 complete reviewed legacy-host/clone-host matrix, fuse first-open/direct-setup
   no-write proof, external future-host watcher, default-main quarantine, `release/v4-stable` freeze ruleset과
   pinned `release-topology-guard`가 실제 state에서 확인됨
5. exact tag draft assets acquisition/restart/MCP canary가 public publish 전에 PASS함. Out-of-band
   launcher의 verifier Mach-O/hardened-loader closure, descriptor-pinned runner, single-tenant
   VM/dedicated UID process-admission freeze, registry write-gate/post-gate writable-FD 0/sealed
   snapshot+moved-original+target과 acceptance-intent→accepted-version→bound-commit→ready→
   serving-intent→target-gate-release→capability→admission-freeze-release fault matrix가 exact
   platform build에서 PASS함
6. exact frozen `release/v4-stable`에서 v4.32.3 stable Release가 publish됨
7. public every-fixed-subject identity와 online/offline attestation이 재검증됨
8. old custom updater, raw host-native updater, raw marketplace install/update가 official safe
   acquisition copy에 등장하지 않음
9. default `main` quarantine fuse SHA/tree/monitor가 별도 sunset proof 전까지 유지됨
10. `codex/v4.33-integration`이 frozen `release/v4-stable` bridge commit에서 생성됨
11. PR #13이 integration target으로 이동함
12. propagation-only abort와 semantic-fuse default-main Stage R single-ref compensation이 isolated
    repository에서 no-ref/explicit-main consumer receipt까지 검증됨

그 뒤에만 parent program의 P1을 시작한다.
