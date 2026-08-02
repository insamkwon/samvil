# SAMVIL v4.33 Safe Upgrade Program — Design Spec

**Date:** 2026-07-28

**Status:** Written for user review

**Program releases:** v4.32.3 bridge, v4.33.0 RC, v4.33.0 stable

**Stable branch:** `release/v4-stable`

**Integration branch:** `codex/v4.33-integration`

---

## 1. Decision

SAMVIL v4.33은 하나의 거대한 PR로 배포하지 않는다. 사용자에게는 한 번의
공식 upgrade 명령과 필요한 경우 Codex 재시작 한 번만 보이게 하되, 내부
엔지니어링은 독립적으로 검증 가능한 release program으로 나눈다.

```text
v4.32.3 distribution bridge
  → Codex native core closure
  → immutable release core
  → transactional profile installer
  → runtime and cross-host compatibility
  → lifecycle and release evidence
  → v4.33 RC
  → v4.33 stable
```

프로그램의 핵심 안전장치는 old updater가 암묵적으로 소비하는 GitHub default branch와
새 Release가 소비하는 canonical stable branch를 분리하는 것이다. Manifest version을
`4.32.2`로 유지하고 updater mutation을 fuse한 reviewed
`main` 자체를 compatibility quarantine default로 유지한다. 실제 stable Release는 새
non-default `release/v4-stable`에서만 진행한다. PR #13과 후속 v4.33 작업은
`codex/v4.33-integration`에서 합치며, stable 승인 전에는 `release/v4-stable`에 들어가지 않는다.

v4.32.3 bridge를 default `main`에 넣거나 GitHub default branch를 release branch로 바꾸는
방식은 허용하지 않는다. Bridge를 실행하지 않은 구 updater와 stale default-name cache는
계속 `main`을 조회하고 clone할 수 있으므로, `main`은 별도 sunset proof 전까지 exact fuse
lineage에서 벗어나지 않는다.

---

## 2. Program goal

다음 사용자 경험을 제공한다.

```text
공식 upgrade 명령 한 번
  → read-only inventory and preflight
  → verified release download
  → reversible profile cutover
  → PENDING_RESTART when an old runtime is active
  → new runtime self-attestation after restart
  → COMMITTED
```

지원되는 online host의 이 명령은 preinstalled `gh`, GitHub authentication, interactive TTY 또는
system Python을 요구하지 않는다. OS별 official command는 platform-native HTTPS/hash primitive로
exact-version self-contained bootstrap asset을 private temp에 받고, copy에 pin된 digest와 OS
code-signature/trust policy를 실행 전에 검증한 뒤 호출한다. Unchecked pipe-to-shell은 사용하지
않는다. 해당 최소 OS primitive조차 없는 host는 supported clean host가 아니며 mutation 전에
정확한 prerequisite와 함께 차단한다.

모든 환경에서 억지로 설치에 성공하는 것은 목표가 아니다. 모든 입력은 다음 세
부류 중 하나로 수렴해야 한다.

```text
증명 가능한 지원 상태  → 완전 전환
증명 가능한 실패 상태  → 정확한 이전 상태 복구
소유권이 불명확한 상태 → mutation 0으로 차단
```

---

## 3. Non-goals

이 프로그램은 다음을 하지 않는다.

1. PR #13에 installer, publisher, lifecycle 변경을 계속 누적하지 않는다.
2. Codex upgrade 과정에서 Claude plugin cache를 자동 정리하지 않는다.
3. shared home payload가 SAMVIL 생성물처럼 보여도 자동 삭제하지 않는다.
4. host installer가 임의의 프로젝트를 스캔하거나 일괄 migration하지 않는다.
5. Codex Desktop 또는 실행 중 MCP를 강제 종료하지 않는다.
6. user-modified config, skill, AGENTS를 추측으로 병합하거나 덮어쓰지 않는다.
7. green CI만으로 실제 runtime 전환이 완료됐다고 선언하지 않는다.
8. release version 문자열이나 local Git tag만으로 legacy ownership을 증명하지 않는다.
9. 자동 telemetry 또는 support bundle 자동 업로드를 추가하지 않는다.
10. v4.33에서 OpenCode, Gemini, Windows native installer까지 범위를 확장하지 않는다.
11. 개발·자동화 검증에서 실제 사용자 `HOME` 또는 `CODEX_HOME`을 사용하지 않는다.

지원 OS와 architecture 목록은 Release Core sub-spec의 승인된 release index에
명시한다. 목록에 없는 host는 `BLOCKED_ENVIRONMENT`이며 mutation은 0이다.

Release-control의 canonical PASS는 또 하나의 지원 환경 조건을 갖는다. Task -2가
소유하고 candidate가 mount, remount, resize할 수 없는 invocation-exclusive
kernel-enforced hard-quota filesystem을 제공하고, 그 경계의 class와 identity digest가
manifest/receipt에 bind되어야 한다. 이 경계는 regular data만이 아니라
preallocation, xattr, directory metadata, unlinked/mapped inode, sparse/clone 할당까지
동일한 fixed capacity에 charge해야 한다. 증명을 제공하는 adapter가 없거나
증거가 drift하면 `UNSUPPORTED_INVOCATION_STORAGE_QUOTA`로 실행 전에
fail closed하고 program terminal은 `BLOCKED_ENVIRONMENT`, mutation은 0이다.
`RLIMIT_FSIZE`, `RLIMIT_NOFILE`, path/FD/map inventory, `st_size`, `st_blocks`, RSS/AS
측정은 defense-in-depth 또는 telemetry일 뿐 storage-boundary PASS authority가 아니다.

Canonical execution은 detached descendant에도 atomic identity-bound signal handle을
요구한다. Native birth identity는 Darwin `PROC_PIDTBSDINFO` 또는 Linux
`/proc/<pid>/stat`로 재검증하지만, PID-only signal은 금지한다. Linux `pidfd`처럼
identity-bound handle이 없는 현재 Darwin foundation은 quota authority가 나중에
제공되더라도 temp 생성·materialization·execution 전에
`DETACHED_PROCESS_SIGNAL_UNAVAILABLE` / `BLOCKED_ENVIRONMENT`로 차단한다.

따라서 PR #14의 release-control 결과는 현재 기준으로 fail-closed control
foundation이다. Portable test-double/Linux 결과는 schema와 orchestration contract를
검증하지만 actual supported-host canonical end-to-end PASS나 release authorization으로
승격되지 않는다.

---

## 4. SSOT hierarchy

문서와 증거의 권한은 다음과 같다.

1. 이 문서: 전체 program 순서, 공통 불변조건, branch/release 정책
2. sub-spec: 한 workstream의 입력, 출력, 상태 머신, acceptance gate
3. implementation plan: commit-sized TDD 실행 순서
4. machine receipt: 실제 실행 결과와 release decision evidence
5. PR description: 위 SSOT의 요약이며 독립적인 truth source가 아님

충돌 시 더 낮은 계층이 상위 설계 계약을 바꿀 수 없다. 변경이 필요하면 먼저 이
문서 또는 해당 sub-spec을 수정하고 사용자 review gate를 다시 통과한다.

---

## 5. Branch and release topology

```text
legacy/v4.32.2-original (immutable pre-promotion rollback anchor)

main (GitHub default, immutable compatibility quarantine)
  └─ reviewed v4.32.2-version quarantine-fuse commit/tree
       ├─ installed old updater: CURRENT == LATEST no-op
       ├─ REFRESHED_PAUSE_COLD: new install not-found
       ├─ stale disk/process memory: typed risk receipt, not PASS
       └─ discovery-failure clone: passive surface only, LEGACY_RISK_OBSERVED

release/v4-stable (non-default, canonical stable Release branch)
  └─ same quarantine-fuse commit/tree first
       └─ v4.32.3 bridge remainder
       └─ freeze
            └─ codex/v4.33-integration
                 ├─ PR #13 native core
                 ├─ immutable release core
                 ├─ transactional installer
                 ├─ runtime compatibility
                 └─ release lifecycle
                      ├─ v4.33.0-rc.N prerelease
                      └─ final release PR → release/v4-stable
                           └─ v4.33.0 stable
```

### 5.1 Stable branch rules

- `main`은 reviewed quarantine-fuse commit/tree와 manifest version
  `4.32.2`에 pin된 GitHub default branch다. Fuse는 plain `/samvil:update`의 clone, rsync,
  rename, sibling delete, manual rsync fallback을 제거하고 marketplace installable entry도
  비운다. New install not-found는 `REFRESHED_PAUSE_COLD`에서만 주장하고 stale disk/process
  memory는 typed risk로 분리한다. Discovery-failure clone은 passive surface로만 수렴한다.
  Update, delete, force-push와 broad bypass는 모두 금지한다.
- `legacy/v4.32.2-original`은 main fuse promotion 전 exact old-main base를 보존하는 immutable
  rollback anchor다. Propagation-only abort 또는 fuse semantic defect에서는 `main`을 fuse
  descendant이면서 tree/catalog가 exact original과 같은 narrowly authorized Stage R forward
  restoration commit으로 단일-ref fast-forward한다. No-ref와 explicit-main consumer 안정화
  receipt 없이는 복구 완료가 아니다.
- `release/v4-stable`은 non-default canonical stable Release branch다. Release, CI, publisher, security scan,
  dependency automation, docs와 clone command는 default branch를 추측하지 않고 explicit
  `release/v4-stable`, integration 또는 exact tag/ref를 사용한다.
- `main`을 old base에서 exact reviewed fuse commit으로 single-ref expected-old fast-forward하고,
  `release/v4-stable`을 그 fuse head에서 만든다. Bridge remainder는 release branch의 fuse head를
  base로 하며 `main`은 전진시키지 않는다. 따라서 stale default-name과 custom-main consumer는
  holdback 전체에서 passive tree만 본다.
- Legacy holdback이 끝날 때까지 default `main`, `release/v4-stable`과 holdback 시작 뒤 새로 만드는
  v4.32.3/v4.33 allowlisted tag의 `.claude-plugin/marketplace.json`은 installable SAMVIL entry 0을
  유지한다. 기존 immutable historical tag/commit은 변경하지 않으며 그 ref에 pin된 custom
  source는 unsupported residual로 분리한다. 공식 설치와 전환은 mutable marketplace listing이
  아니라 attested Release asset/bootstrap으로만 한다.
- v4.33 개발 기간에는 `release/v4-stable`의 latest approved v4.32.x tree에서 stable-only freeze한다.
- Published bridge defect의 v4.32.x forward fix만 같은 release authorization과,
  Task -2가 attested한 invocation-exclusive kernel-quota storage boundary 위의 canonical
  full gate로 `release/v4-stable`을 전진시킬 수 있다. 그 경계가 없으면
  forward fix도 `BLOCKED_ENVIRONMENT`에 머물며, 승인된 fix는 integration에도
  즉시 forward-merge한다.
- v4.33 RC는 integration commit으로 만들며 prerelease로만 게시한다.
- stable 승인 전까지 integration의 code commit을 `release/v4-stable`에 cherry-pick하지 않는다.
- final release PR은 승인된 RC core tree와 stable candidate core tree가 같은지 검증한다.
- final merge 뒤 exact `release/v4-stable` SHA로 stable tag, Release, asset을 게시한다.
- final `release/v4-stable`에서 core archive를 결정적으로 다시 만들고 RC core archive와 byte
  equality를 검증한다. Stable index와 attestation은 final `release/v4-stable` commit을 가리키며 RC
  index/attestation과 동일할 수 없다.
- published stable tag와 asset은 이동하거나 덮어쓰지 않는다. 문제는 forward fix로
  해결한다.
- v4.33 stable 뒤에도 별도 sunset proof와 사용자 승인 전에는 default `main`을 fuse lineage에서
  벗어나게 하거나 GitHub default를 `release/v4-stable`로 바꾸지 않는다. Repository UI의 passive
  default 부작용은 repository description과 explicit `git clone --branch release/v4-stable`
  contributor 안내로 보완한다.

### 5.2 PR #13 rules

PR #13 `codex/codex-native-autonomy`는 bridge 위로 rebase하고 base를
`codex/v4.33-integration`으로 변경한다.

PR #13의 종료 조건은 native controller와 plugin core의 기준점 확정이다. 다음은
후속 workstream으로 넘긴다.

- production installer hardening
- immutable release payload
- shared DB mixed-version proof
- full lifecycle
- stable publisher

PR #13의 current-HEAD Desktop evidence는 integration merge 전에 persisted artifact로
갱신한다. source validation, authentication-blocked CLI readiness, stale process evidence를
actual current-runtime PASS와 섞지 않는다.

---

## 6. Architecture ownership

```text
Stable Release Feed
  owns: release discovery, channel, immutable artifacts, provenance

Runtime Core
  owns: tracked plugin bytes, locked dependencies, core identity

Profile Activation
  owns: one Codex profile, user approval policy, transaction lineage

Runtime Attestation
  owns: proof that the new MCP process is actually running

Runtime Capability Gate
  owns: commit receipt와 ready token 뒤 irreversible serving intent를 fsync하고 normal capability를 여는 경계

Project Compatibility
  owns: per-project first-open recovery and schema compatibility
```

의존성은 위에서 아래로 단방향이다.

- installer는 verified Release Core만 입력으로 받는다.
- runtime attestation은 installer receipt를 읽지만 profile mutation을 수행하지 않는다.
- runtime capability gate는 attestation-only process가 commit receipt와 ready token을 검증한 뒤
  `SERVING_INTENT_DURABLE`을 fsync하기 전까지 normal tool advertisement와 state/project/DB write를
  0으로 유지한다. Serving intent 뒤에는 receipt loss가 있어도 automatic rollback하지 않는다.
- project compatibility는 host install을 되돌리지 않는다.
- release decision은 각 계층의 receipt를 소비하지만 receipt 내용을 추측으로 보완하지
  않는다.

---

## 7. Shared identities

### 7.1 Release identity

```text
release_identity =
  channel
  + release version
  + source commit
  + source tree
  + every fixed subject name/digest set
  + dependency lock digest
  + signer workflow identity
```

`release_version`은 `4.33.0-rc.1` 또는 `4.33.0`처럼 channel publication을
식별한다. `core_version`은 payload가 최종적으로 보고할 `4.33.0`이다. RC 표시는 core
archive 안에 넣지 않고 Release index, tag, provenance에만 둔다.

같은 published stable `release_version`에 다른 core bytes가 있으면 illegal republish로
차단한다. 서로 다른 RC release는 각자 다른 core digest를 가질 수 있지만 final stable은
승인된 RC의 exact core digest를 재사용해야 한다.

### 7.2 Core identity

```text
core_identity = core version + signed core digest
```

Core에는 사용자별 approval policy를 넣지 않는다.

### 7.3 Activation identity

```text
activation_identity =
  core digest
  + activation schema
  + rendered approval policy digest
  + profile identity
```

승인 정책 변경은 activation digest만 바꿀 수 있다. command, args, env, transport가
사용자에 의해 변경된 direct MCP는 approval overlay로 해석하지 않고
`BLOCKED_USER_STATE`로 종료한다.

### 7.4 Profile identity

실제 `HOME`과 `CODEX_HOME`은 독립 입력이다. profile identity는 lexical path 하나가
아니라 resolved filesystem identity와 profile-local receipt lineage를 함께 사용한다.

### 7.5 Installed release and trust-history identity

```text
installed_release_receipt =
  exact release identity
  + core identity
  + activation identity
  + profile identity
  + transaction lineage

accepted_release_high_water =
  repository id
  + release epoch
  + highest accepted stable identity
  + accepted RC-to-stable lineage
  + profile lineage hash chain
```

Activation identity가 같아도 RC와 stable release identity는 다르다. `CURRENT`는 target release의
installed receipt와 accepted high-water까지 exact해야 한다. Normal uninstall은 activation과
runtime만 제거하며 release-owned mode `0600` trust-history tombstone을 지우지 않는다. Tombstone
missing/tamper는 clean profile로 재해석하지 않고 block한다. Intentional downgrade나 trust-history
purge는 별도 explicit authorization, 사용자 경고와 receipt가 있어야 한다.

일반 install/update의 release acceptance는 runtime commit receipt와 별개인 durable trust
transaction이다. `RELEASE_ACCEPTANCE_INTENT`가 target release, previous high-water와 exact installed
closure를 먼저 fsync한 뒤, canonical profile trust ledger의 한 atomic transaction에서 installed
release receipt와 monotonically advanced high-water를 함께 commit한다. Ledger가 두 durable resource로
구현되는 adapter는 high-water를 먼저 fsync하고 installed receipt를 나중에 publish해야 하며, 그
사이 crash는 high-water tombstone을 낮추거나 지우지 않고 exact target receipt를 roll-forward하거나
`RECOVERY_REQUIRED`로 끝낸다. Installed receipt가 high-water보다 먼저 관찰되는 상태는 invalid다.
Commit receipt는 이 두 digest를 bind하고, ready token과 serving intent는 exact pair가 durable한 뒤에만
허용한다. Release acceptance 뒤 failure는 serving 전이라도 old release로 automatic rollback하지
않고 exact roll-forward 또는 `RECOVERY_REQUIRED`로 수렴한다.

### 7.6 RC-to-stable reused subject closure

RC에서 stable로 payload mutation 없이 승격할 수 있는 단위는 core archive 하나가 아니라 다음
전체 closure다.

```text
promotion_reused_subject_closure =
  every installed or reused fixed subject digest
  + runtime, wheel, builder and launcher manifest digests
  + dependency lock identity
  + activation schema identity
  + approval-policy renderer identity

promotion_current_installed_state =
  current on-disk core and runtime identity
  + current activation identity including rendered approval digest
  + current profile identity and transaction lineage
  + RC installed receipt and ready-capability identity
```

Promotion intent 직전에 `promotion_current_installed_state`가 RC installed receipt와 exact equal하고,
RC receipt가 가리키는 closure와 stable index closure도 exact equal할 때만 receipt/high-water
promotion을 허용한다. User approval/profile/core/runtime drift 또는 closure drift가 하나라도 있으면
receipt-only promotion으로 포장하지 않고 정상 verified update transaction과 필요 시
`PENDING_RESTART`를 사용한다.

### 7.7 Canonical project identity and scoped transition keys

Project authority는 display label, lexical path 또는 basename이 아니다. Supported filesystem adapter가
resolved project-root directory FD에서 얻은 다음 anchor를 canonicalize한다.

```text
canonical_project_identity =
  schema samvil.project-identity.v1
  + volume UUID
  + directory file ID/inode
  + directory birthtime/generation
```

Initial v4.33 filesystem adapter matrix는 다음처럼 보수적으로 고정한다.

| Adapter | Scope | Verdict |
|---|---|---|
| `darwin-apfs-local-v1` | local internal/external APFS, stable volume UUID+file ID+birthtime, case-sensitive/insensitive | supported after move/recreate/clone fixtures |
| HFS+ and other local filesystems | stable generation semantics 미검증 | `BLOCKED_ENVIRONMENT` |
| SMB/NFS/WebDAV/FUSE/cloud-file-provider/network mount | server reconnect/clone에서 inode·birthtime 재사용 가능 | `BLOCKED_ENVIRONMENT` |
| Linux/Windows filesystem adapters | 별도 host-specific identity contract 없음 | initial v4.33 unsupported |

Encrypted APFS는 unlock된 local volume이 같은 adapter proof를 만족할 때만 허용한다. APFS snapshot/
clone restore, volume migration과 backup restore는 anchor가 바뀌면 새 project로 취급한다. Adapter
identity/version은 receipt와 release index에 포함하며 unknown mount type, unstable file ID,
birthtime/generation 부재 또는 volume UUID drift는 transition lookup/write 전에 block한다. 향후
filesystem 지원 확장은 alias/move/recreate/clone/reconnect fixture와 migration proof를 갖춘 새 signed
adapter version으로만 가능하다.

Filesystem anchor는 project incarnation을 구분하지만 same-anchor snapshot rollback까지 증명하지는
못한다. 따라서 각 supported project의 정본은 project-local no-follow append-only lineage journal과
CAS head marker이며, 각 profile DB는 검증 가능한 materialized checkpoint/cache다.

```text
project_state_lineage =
  canonical project identity
  + random project-incarnation nonce
  + monotonic generation
  + previous-lineage digest
  + latest committed transition/event digest
  + transition id and canonical request/receipt/event digests
  + canonical joined-profile binding-set digest
  + canonical project trust-root-set digest
  + writer profile-binding identity
  + writer signing-key id/epoch and domain-separated record signature
  + writer release/schema identity
```

Hash chain alone은 forged extension을 막지 못한다. Initial `darwin-apfs-local-v1` writer profile은
Keychain/Secure Enclave의 non-exportable P-256 signing key와 public-key certificate를 profile trust
ledger에 등록한다. Private key bytes는 Python/runtime에 노출하지 않고, signed SAMVIL code requirement와
profile lineage를 검증하는 release-owned signing broker만 descriptor-pinned request를 서명할 수 있다.
Broker는 current project head, canonical request/receipt/event body, transaction id와 writer release/
schema identity를 직접 재검증하고 arbitrary caller-supplied digest signing을 거부한다. Software-exportable
key, raw key file, unknown broker/code identity 또는 unsupported Keychain ACL은 project write 전에
`BLOCKED_ENVIRONMENT`다.

Profile trust-ledger file은 root of trust가 아니다. Verified v4.33 installer가 notarized native broker의
fixed Team ID/bundle ID/code-directory policy와 전용 Keychain access group 아래 non-exportable device-root
key를 만들고, 같은 protected Keychain item에 root public-key fingerprint, canonical profile identity,
installer release/transaction receipt digest, trust-ledger head digest와 monotonic generation을 저장한다.
그 item의 create/read/CAS-update는 exact broker code requirement만 허용하며 일반 same-UID process는 새
key를 만들어도 canonical application label/access-group item을 read/replace/adopt할 수 없다. Enrollment
receipt는 root key로 self-sign한 것만 믿지 않고 verified installer identity, release attestation,
broker code-directory hash, Keychain persistent-ref identity와 initial head를 함께 bind한다.

Every trust-ledger update는 previous head/generation을 bind해 device-root로 서명한다. Signed successor
body를 protected profile state에 fsync한 뒤 broker가 Keychain anchor를 expected-old active state에서
`PENDING_TRUST_LEDGER_ADVANCE(previous, successor digest/generation, transaction id, staged-file identity)`로
CAS한다. 그 뒤 ledger file을 atomic no-replace successor로 materialize하고 file/parent를 fsync한 다음
Keychain pending anchor를 exact successor active state로 CAS한다. 마지막에 staged successor를 지운다.

Startup/catch-up은 Keychain anchor를 먼저 broker로 읽는다. Active state면 ledger signature/head/
generation과 exact equal해야 한다. Pending state면 project 접근 전에 staged successor, old/new ledger
file과 previous/successor digest를 reconcile한다: exact old file은 staged body로 advance하거나 외부
effect 0이면 pending을 expected-old abort하고, exact successor file은 anchor를 finalize한다. Foreign/
missing staged body, third digest, generation gap 또는 CAS ambiguity는 mutation 0
`RECOVERY_REQUIRED`다. Mutable ledger/public-key
substitution, copied profile, Keychain application-label collision, generation rollback 또는 anchor/head
mismatch는 project journal/profile DB mutation 0이다. Device-root rotation은 old+new dual signature,
verified broker update와 Keychain anchor CAS를 요구한다. Administrator가 broker access group이나 entire
Keychain+profile을 함께 rollback하는 경우는 local threat boundary 밖의 typed limitation으로 남긴다.

Every `PROFILE_BINDING_JOIN`, transition, catch-up checkpoint, key rotation/revocation record는
`insamkwon/samvil:project-lineage-record.v1\0` domain-separated canonical bytes에 대한 signature,
profile key certificate id/epoch와 revocation generation을 포함한다. Device enrollment root와 trust
ledger head는 위 protected Keychain anchor에서 검증한다. Project journal genesis는 journal/head가
exact absent인 first join에서만 verified installer/device-root certificate를 initial
`project_trust_root_set`으로 채택한다. First join과 later join은 verified installer가 그
device-root broker를 통해
user-approved migration transaction에 발급한 nonce/expiry/project/profile/key/history-bound
`PROFILE_JOIN_AUTHORIZATION`을 요구한다. Later join은 current head를 bind해 replay를 막는다. Normal
record는 currently joined, non-revoked key만 append할 수 있다. Later join의 authorization signer는
current project trust-root set의 non-revoked roots여야 하며 new profile/root도 join body를 서명한다.
Genesis는 signed `join_threshold` policy를 고정하고, default threshold는 current non-revoked root set의
strict majority다(1개면 1-of-1). Every later-join countersign body는 current project head/root-set digest,
every signer key epoch, revocation generation, new profile/root certificate, legacy history digest,
authorization nonce/expiry와 user-approved transaction을 bind하며 threshold signatures가 exact해야 한다.
새 device root는 이 countersignature quorum 없이 자기 root authorization만으로 join할 수 없다.
Same-device 새 `CODEX_HOME`은 protected canonical device root를 재사용하되 current project root membership과
threshold policy를 먼저 증명한다.

Join, root add/rotation/revocation, threshold 변경과 recovery-policy 변경을 포함한 every trust-root-set
mutation은 pre-operation current head/root-set digest, every current key epoch, revocation generation,
proposed root set/policy와 authorization nonce/expiry를 bind한 current threshold countersignature를
요구한다. Compromised root 하나가 다른 roots를 순차 revoke해 threshold를 낮출 수 없다. Rotation은
current threshold countersignature에 더해 retired old root와 new root의 dual signature를 요구한다.

Project root-set mutation과 affected profile Keychain/trust-ledger advance는 하나의 distributed crash
transaction이다. Project resource lock 아래 `ROOT_SET_MUTATION_INTENT`를 먼저 fsync하며 transaction id,
pre/post project head/root-set/policy/revocation generation, affected Keychain persistent-ref identities와
각 pre/successor ledger epoch/head, required quorum/dual/recovery signatures를 exact bind한다. 이 prepare
record 자체는 old project authority를 바꾸지 않는다. Each affected broker는 기존 trust-ledger 2PC로
old+proposed overlap을 허용하는 `PENDING_PROJECT_ROOT_SET_MUTATION(transaction id, pre/post project head)`
상태까지만 durable하게 준비하고 signed prepare receipt를 반환한다. New authority만 active하게 만들거나
old authority를 먼저 revoke하지 않는다.

Required prepare receipt set이 exact한 뒤 threshold/dual/recovery signatures를 포함한 project root-set
mutation record와 side effects를 fsync하고 project head를 CAS+directory fsync한다. 이 project-head
advance와 signed `ROOT_SET_MUTATION_COMMITTED` decision이 authority activation commit point다. Commit하지
않는 경우 current threshold가 pre-head/root-set을 bind한 signed `ROOT_SET_MUTATION_ABORTED` decision을
project coordinator journal/head에 durable하게 publish한다. Decision 없는 PREPARED 상태에서만 global
project writes는 0이다.

ABORT decision 뒤 online profiles는 old authority로 즉시 write를 재개하고 pending anchor finalize를
기다리지 않는다. Offline pending broker는 reconnect 때 global abort decision을 검증해 old active state로
expected-old reconcile한다. COMMIT decision 뒤 overlap policy와 project record를 검증한 online/reconciled
profiles는 즉시 write를 재개하며, prepared-but-unfinalized offline profile만 local capability closed로
남아 reconnect 때 successor anchor로 roll-forward한다. Project root set을 automatic rollback하지 않는다.
Mixed anchor state, response loss와 broker restart는 transaction id, global decision, pre/post heads와
prepare receipts로만 reconcile한다. Anchor finalize receipts는 project coordinator log에 비동기로
append하지만 global write 재개의 전제는 아니다. Every affected anchor가 finalize 또는 signed
quarantine disposition에 도달하면 coordinator는 exact receipt/disposition set을 bind한 signed
`ROOT_SET_MUTATION_SETTLED` record를 append/fsync한다. 이 record는 cleanup/old-root retirement의 SSOT이지
authority activation이나 normal write reopen gate가 아니다. Last-finalize response loss는 same
transaction id/receipt set으로 idempotent하게 settled record에 수렴한다.

Rotation/revocation은 add-overlap activation과 old-root retirement를 별도 root-set transactions로
나눈다. Old root retirement는 모든 affected anchor finalize receipt와 offline/stale joined-profile의
verified catch-up 또는 explicit quarantine disposition이 있어야 시작한다. Inaccessible affected anchor가
있으면 new root overlap은 유지할 수 있지만 old authority를 retire/revoke했다고 보고하지 않는다.
Never-return profile은 signed quarantine disposition 뒤에만 retirement set에서 제외할 수 있고, 나중에
돌아오면 local capability closed 상태에서 recovery/catch-up을 요구한다. Concurrent root-set transactions는
project lock과 expected-head CAS로 직렬화한다.

Genesis는 normal root set과 별개인 `project_recovery_policy`도 고정한다. 지원 policy는 project/device
밖에 보관하는 offline recovery public key, guardian threshold 또는 account transparency authority 중
하나이며 public identity/policy digest만 project journal에 둔다. Threshold root가 남지 않은 경우
normal join/root mutation은 0이고, recovery authority가 project identity, current observed head/root set,
lost roots, proposed new root set/threshold, monotonically advanced recovery epoch, nonce/expiry를 서명한
`PROJECT_ROOT_RECOVERY_AUTHORIZATION`과 broker-enforced fresh user-presence proof가 함께 있어야 별도
recovery transaction을 열 수 있다. Genesis receipt나 writable project copy, 새 device-root self-signature,
user presence만으로는 recovery authority가 되지 않는다. Recovery proof가 없으면 canonical project를
변경하지 않고 `RECOVERY_REQUIRED`; explicit import-as-new-project/fork만 별도 허용한다. Unknown/revoked
key, insufficient quorum, epoch rollback, wrong project/head/profile, expired/replayed join/recovery
authorization은 journal/head/profile DB mutation 0이다.

첫 adoption은 journal/head와 profile checkpoint가 모두 absent이고 project write 전일 때만
nonce/generation 0을 만든다. 이후 transition은 project resource lock 아래 current head와 global
project-scoped transition-id index를 읽고 exact side-effect path/type/cardinality, canonical ordered bodies,
pre/post digests와 expected DB rows를 bind한 `LINEAGE_TRANSITION_INTENT`를 먼저 fsync한다. Writer profile
DB에는 intent-bound pending receipt/event rows만 durable하게 만들고, project-local JSONL/claim 등
side-effect records를 같은 intent id와 canonical body digest로 append/fsync한다. Pending side effects는
canonical head가 그 intent를 commit하기 전에는 public/complete로 읽지 않는다. 모든 required side-effect
file과 parent directory의 fsync 및 digest/cardinality recheck가 끝난 뒤에만 signed canonical committed
record를 project journal에 append하고 journal file을 fsync한다. 그 exact record offset/digest를 가리키는
head를 atomic CAS advance하고 head file과 parent directory를 fsync한다. 이 durable head+directory
advance가 유일한 visibility commit point다.
마지막으로 writer profile DB rows와 checkpoint를 finalize한다. 각 record는 previous
digest, canonical request/receipt/event body와 writer profile binding을 포함한다. 한쪽만 앞선 crash
intermediate는 exact project intent/profile pending/prepared side-effect set/previous digest에서만
roll-forward한다. Head 뒤 side effect missing은 정상 reconcile이 아니라
`PROJECT_STATE_ROLLBACK_DETECTED`다. Head 전 prepared side effect는 matching intent에서만 commit하거나
ignored pending artifact로 보존/정리한다.

다른 joined profile의 checkpoint가 project head의 strict ancestor이면 rollback으로 보지 않는다.
해당 profile은 새 write 전에 intervening canonical records, hash chain, writer bindings와 project-local
JSONL/claim/marker side effects, every record signature/certificate/key epoch/revocation과 join authorization을
순서대로 검증하고, missing scoped receipts/events를 한 DB catch-up
transaction으로 idempotent materialize한 뒤 checkpoint를 current head로 fast-forward한다. Original
writer profile DB나 journal에 의존하지 않는다. Project journal의 transition-id index에 같은 id와 같은
canonical request digest가 있으면 canonical receipt를 반환하고 event/write 0이며, 같은 id와 다른
request digest면 `TRANSITION_ID_CONFLICT` mutation 0이다.

Project head가 profile checkpoint의 ancestor보다 뒤로 가거나, 어느 쪽 chain이 분기되거나, canonical
record/side-effect가 누락·변조된 경우만 `PROJECT_STATE_ROLLBACK_DETECTED`로 project mutation 0이다.
Profile DB가 old checkpoint로 복원됐지만 complete project canonical superset이 남은 경우는
`PROFILE_LINEAGE_CATCHUP_REQUIRED`로 안전하게 reconstruct한다. APFS snapshot/backup restore가 volume
UUID, inode와 birthtime을 유지해도 project journal rollback은 newer profile checkpoint와 비교해
검출한다.
Project와 모든 release-owned external lineage anchor가 함께 과거로 복원된 whole-system rollback은
local-only 증명으로 구분할 수 없으므로 support bundle에 limitation으로 표시하고 remote transparency
anchor를 별도 workstream 없이 자동 주장하지 않는다.

이미 transition/event/project history가 있는 legacy project는 fresh adoption으로 위장하지 않는다.
Scoped-key schema migration이 complete ordered DB history와 당시 project-local JSONL/claim/marker의
exact set/digest를 canonicalize해 profile별 `legacy_profile_history_digest`와 lineage-control files를
제외한 `legacy_project_artifact_digest`를 profile ledger의
`LEGACY_LINEAGE_BASELINE_PENDING` row에 먼저 durable하게 기록한다. Profile pending row는 random
project nonce를 선점하지 않는다. Host migration 자체는 project file을 쓰지 않는다.

해당 project의 first open에서 새 write 전에 canonical project resource lock을 획득하고 current legacy
artifact set이 captured digest와 exact equal한지 확인한다. Project-local singleton lineage marker가
absent면 lock 아래 `LEGACY_LINEAGE_SINGLETON_INTENT`를 fsync하고 random incarnation nonce와 generation
0 marker를 no-replace로 만든다. 이미 valid singleton marker가 있으면 그 nonce/chain을 검증해 사용하되
다른 profile history를 자기 history로 adopt하지 않는다. 각 profile은
`profile lineage identity + signing-key certificate/epoch + PROFILE_JOIN_AUTHORIZATION +
legacy_profile_history_digest + scoped migration backup/schema identity`의 signed binding을 singleton
marker의 canonical binding set에 CAS append하고 marker generation/hash chain을
전진시키는 canonical `PROFILE_BINDING_JOIN` lineage record를 남긴 뒤, 자기 profile baseline을 exact
shared nonce/generation/join digest로 finalize한다. 이미 joined된 다른 profile의 checkpoint는 stale해질
수 있으며, 재방문 시 자기 binding이 unchanged이고 old head가 canonical join-chain ancestor임을
검증해 intervening join records를 materialize하고 current head로 fast-forward한다.

A→B, B→A와 concurrent first-open은 같은 resource lock/CAS로 직렬화된다. Exact same-profile binding
repeat는 write 0이고, same profile identity/different history 또는 foreign nonce/chain은 block한다.
Crash로 singleton intent, marker append, profile finalize 중 한쪽만 생긴 경우 exact pending baseline,
join intent, previous marker digest와 binding body에서만 reconcile한다. Captured legacy artifact mismatch,
missing/extra artifact, invalid prior marker, 자기 binding body drift 또는 finalized checkpoint가 canonical
project join-chain의 ancestor가 아닌 경우는 mutation 0
`PROJECT_STATE_ROLLBACK_DETECTED`/`SCOPED_KEY_MIGRATION_REQUIRED`다.

Symlink alias와 case-spelling alias는 같은 resolved directory FD로 수렴하므로 같은 identity다.
같은 filesystem에서 directory를 move해도 file ID/generation이 유지되면 같은 project다. Directory를
삭제하고 같은 path를 다시 만들거나 APFS clone/cross-device copy로 새 inode가 생기면 새 project
identity이며 old receipt를 재사용하지 않는다. Existing embedded `.samvil` state가 다른 filesystem
anchor를 주장하면 자동 adopt하지 않고 `PROJECT_IDENTITY_MISMATCH`로 block한다. Explicit project
import/adoption은 별도 signed lifecycle contract다. Public receipt에는 raw volume/file ID/path 대신
tokenized digest만 남긴다.

Idempotency와 persistence key는 `(canonical_project_identity, transition_id)`다. 현재 PR #13의
global `transition_receipts.transition_id`, `events.id`, `pending_project_events.event_id`와
`event-{transition_id}` assumption을 그대로 stable 계약으로 채택하지 않는다. Schema migration은
다음을 한 SQLite transaction과 fsynced pre-migration backup으로 수행한다.

- `sessions`에 canonical project identity를 materialize한다.
- history가 있는 resolvable project마다 ordered legacy DB rows와 project-local artifact-set digest를
  bind한 profile별 `LEGACY_LINEAGE_BASELINE_PENDING`을 nonce 없이 만든다. Project first-open의
  resource-locked singleton nonce/marker와 per-profile history-binding CAS join, profile finalize 전에는
  해당 profile의 새 transition/project write를 허용하지 않는다.
- transition receipt는 composite key `(project_identity, transition_id)`를 사용한다.
- DB event/pending event는 composite `(project_identity, public_event_id)` 또는 equivalent scoped
  storage key를 사용하고 project-local JSONL의 public event id는 `event-{transition_id}`를 유지할
  수 있다.
- old row는 `session_id → resolved project root FD → project identity`로 backfill한다. Resolvable
  row는 scoped table로 옮기고, missing/inaccessible/recreated/mismatched root 또는 scoped-key body
  collision row는 fsynced backup과 byte-preserving read-only `legacy_unscoped_*` quarantine table에
  source PK/body/digest/reason을 그대로 보존한다. 모든 old row가 migrated 또는 quarantined로 exact
  accounted되면 host schema와 unaffected project는 전진할 수 있다. Quarantined row는 normal lookup,
  replay, DB-loss reconstruction에 절대 참여하지 않으며, 같은 public transition/event id 요청만
  project-local artifact와 explicit adoption proof로 유일하게 scope될 때까지
  `SCOPED_KEY_MIGRATION_REQUIRED`로 block한다. 삭제된 과거 프로젝트 하나가 다른 project/profile의
  install이나 새 unrelated transition id를 막지 않는다.
- row counts, canonical receipt/event digests, foreign keys와 `integrity_check`가 exact한 뒤에만
  schema version을 전진시킨다. Response-loss retry는 migration journal과 observed schema로 same
  result에 수렴한다.
- DB-loss reconstruction도 project-local JSONL/claim/marker와 canonical project identity를 함께
  사용한다. Canonical project journal chain과 joined profile binding을 먼저 검증하고, absent/ancestor
  profile checkpoint는 local artifacts가 body까지 exact 제공하는 record만 idempotent materialize해
  fast-forward한다. Digest만 있고 body가 없거나 chain이 분기되면 block한다. Global transition/event
  ID만으로 다른 root의 row를 adopt하지 않는다.

---

## 8. Common terminal states

모든 workstream의 사용자-facing 결과는 다음 enum으로 정규화한다.

| State | Contract |
|---|---|
| `CURRENT` | target release receipt, core, activation, runtime과 accepted high-water가 일치하며 write 0 |
| `COMMITTED` | on-disk target, 새 runtime identity, atomic installed-release receipt/accepted high-water pair, 이를 bind한 durable commit receipt/ready token/serving intent와 capability receipt가 모두 증명됨 |
| `RC_PROMOTED_STABLE` | RC와 exact-equal `promotion_reused_subject_closure`를 유지한 채 verified stable release receipt/high-water만 durable promotion함 |
| `PENDING_RESTART` | operation-qualified pending state. Install/update는 target disk cutover 완료+old runtime active, rollback/uninstall은 deactivation epoch/admission fence 완료+reverse cutover pending+payload/backup preserved |
| `DEFERRED_TO_V433` | P0에서 legacy state를 진단했지만 protected-scope mutation 없이 v4.33 bootstrap으로 넘김 |
| `LEGACY_RISK_OBSERVED` | 이미 배포된 old updater의 destructive behavior를 격리 fixture에서 재현한 evidence-only 결과; supported PASS가 아님 |
| `STALE_CATALOG_RISK_OBSERVED` | stale marketplace catalog가 raw host install/update를 우회시키는 것을 재현한 evidence-only 결과; supported PASS가 아님 |
| `STALE_HOST_MEMORY_RISK_OBSERVED` | refresh 전 실행된 Claude process의 process-local marketplace memo가 disk pause catalog를 우회함을 재현한 evidence-only 결과; supported PASS가 아님 |
| `PINNED_SOURCE_RISK_OBSERVED` | historical tag/commit 또는 fork/local source pin을 원격으로 revoke할 수 없음을 재현한 evidence-only 결과; supported PASS가 아님 |
| `HOST_TOPOLOGY_RISK_OBSERVED` | 공식 지원 밖 scope/config-root/managed topology의 host-native refresh 영향을 자동 보존 증명할 수 없음을 기록한 evidence-only 결과 |
| `BLOCKED_USER_STATE` | modified, foreign, ambiguous ownership이며 mutation 0 |
| `BLOCKED_ENVIRONMENT` | network, disk, permission, unsupported host이며 mutation 0 |
| `RECOVERED_PREVIOUS` | 실패 뒤 byte와 metadata가 pre-state로 복구됨 |
| `ROLLED_BACK` | 명시적 rollback 뒤 target previous runtime, process quiescence와 project compatibility까지 증명됨 |
| `UNINSTALLED` | transaction-owned Codex activation 제거, relevant process 0, trust-history tombstone과 every touched data의 remaining-reader/export proof가 증명됨 |
| `UNINSTALLED_DATA_RETAINED` | explicit consent 뒤 activation은 제거됐지만 forward-only project/DB data와 compatible reinstall/export payload를 보존하고 경고 receipt를 남김 |
| `RECOVERY_REQUIRED` | old/new 어느 쪽도 자동 증명할 수 없어 추가 mutation 중단 |

`mutation 0`은 active profile, install root, project, repository 같은 protected scopes의
persistent mutation 0을 뜻한다. Attested verifier를 받기 위한 private temporary download는
허용하되 cleanup과 receipt가 필요하다. `setup-codex.sh --check`는 더 강한 계약으로 temp와
network activity도 0이다.

`RECOVERY_REQUIRED`는 concurrent user edit 같은 의도적 adversarial fixture에서는 올바른
결과가 될 수 있다. clean 또는 supported legacy fixture에서 발생하면 release blocker다.

---

## 9. Workstreams

### P0 — v4.32.3 distribution bridge

목적은 아직 bridge를 설치하지 않은 구 updater 사용자까지 개발 중 v4.33 tree에서
격리하는 것이다.

Outputs:

- reviewed v4.32.2-version no-write updater fuse, immutable default-main quarantine,
  default-branch identity monitor
- immutable original rollback anchor와 parent=fuse/tree=original Stage R forward-restoration commit
- historical skill/hook/MCP/setup/root-host-instruction path를 모두 덮는 passive fuse overlay
- reviewed Claude marketplace/clone consumer host matrix와 future-host external watcher
- main-based clone/in-place rsync를 사용하지 않는 authorized external acquisition과 installed
  bridge write-0 guard/defer command
- deterministic tracked-only Release bundle
- reviewed distribution-ledger 기반 signed v4.32.2 provenance/residue catalog
- verified bridge MCP wheel, complete platform dependency wheels, Python runtime, runtime builder
- out-of-band-rooted Ed25519 canary authorization policy, hardened Mach-O native verifier loader
  closure and descriptor-pinned supervised runner boundary
- single-tenant disposable VM/dedicated UID canary enclave, registry write-gate, post-gate writable-FD
  proof, sealed rollback snapshot/moved-original/target and durable serving-intent gate-release boundary
- fail-once/response-loss까지 검증한 resumable Release publisher
- true no-write `setup-codex.sh --check`
- verified stable source와 explicit contributor `--dev` 분리
- `default main quarantine + explicit release/v4-stable Release` flow
- old `/samvil:update` first hop과 Release-owned write-gated/no-replace registry transaction을 분리한 상태 계약
- every plugin hook/MCP verifier-first route
- `darwin-arm64` clean-profile merge 전 candidate canary와 publish 전 exact draft-assets canary

Exit gate:

- exact v4.32.2 straggler의 installed old updater는 successful version discovery에서 fuse
  default-feed version check no-op이고 development integration/main tree를 받을 수 없음.
  Discovery failure/clone success 조합은 `LEGACY_RISK_OBSERVED`지만 clone source는 passive
  fuse로 제한됨
- v4.32.2 declared compatibility floor 또는 marketplace-feature floor부터 switch cutoff까지 every
  installable OS/architecture/platform artifact/package가 ledger+digest+class-mapping smoke를 통과하고,
  every distinct semantic×platform class/scope/config-root lineage가 cold/stale-disk/
  stale-process-memory catalog, source-ref, manual/auto update, two-restart matrix를 통과하고,
  stale/pinned/unsupported residual은 typed risk receipt로 분리됨
- all pre-refresh Claude process 0 뒤 `REFRESHED_PAUSE_COLD` new-install not-found와 actual
  two-process `STALE_HOST_MEMORY_RISK_OBSERVED` result classification/recovery input이 분리 증명됨
- propagation-only abort와 semantic-fuse/unknown default-main Stage R single-ref compensation이
  no-ref/explicit-main consumer receipt까지 isolated repository에서 증명됨
- default fuse checkout의 actual supported host first-open과 legacy setup/sync 명령은 inert-control
  대비 SAMVIL-attributable network/temp/profile/project/chain-marker mutation 0이고 passive
  `DEFERRED_TO_V433`만 노출함
- bridge-owned updater의 모든 failure point에서 current cache hash가 동일함
- stable updater가 prerelease를 선택하지 않음
- published bridge every-fixed-subject set과 source tree identity가 일치함
- supported v4.32.2 current root가 signed legacy catalog exact match 뒤 protected-scope mutation 0
  `DEFERRED_TO_V433`로 종료함
- every hook/MCP에서 runtime/network/profile/project write 전에 absolute Python
  `-I -S -B` stdlib verifier가 실행됨
- destructive legacy updater는 supported safe-upgrade path로 안내되지 않음
- production runner가 actual profile에서 opaque host updater를 호출하지 않음
- canary authorization forgery/wrong audience/revoked key/verifier-loader injection/direct-runner bypass가
  Python/protected mutation 전에 차단되고, single-tenant UID admission freeze와 held-FD/sealed-target/
  serving-intent gate-release fault matrix가 exact supported build에서 수렴함
- exact `EMPTY_READY` darwin-arm64 candidate acquisition/restart/MCP canary가 merge 전에,
  exact draft-assets canary가 public publish 전에 PASS하지 못하면 bridge user rollout을 열지
  않고 existing 사용자는 default-main quarantine 뒤에 둠

### P1 — Codex native core closure

Outputs:

- native plugin surface
- stage catalog and same-task driver
- idempotent stage transition controller
- canonical project identity adapter와 global→project-scoped receipt/event schema migration
- current-HEAD Desktop retry evidence
- honest capability reporting

Exit gate:

- current-HEAD Codex Desktop actual runtime에서 표시명이 resolved project root basename/path와
  다른 temporary project를 열고 `get_stage_envelope → begin_stage →
  commit_stage_transition(fixed transition_id) → same transition_id retry`를 exact 순서로 실행함
- 첫 commit과 retry receipt가 canonical bytes로 완전히 동일함
- 해당 canonical project identity에 대한 DB event, canonical JSONL event, claim, marker revision은
  각각 exactly once이고 journal cleanup도 중복 없이 일치함. 같은 display label을 가진 다른
  root와 충돌하거나 label을 filesystem authority로 사용하지 않음
- 같은 display label을 가진 두 temporary canonical roots에서 envelope/begin/commit/retry를
  interleave함. Idempotency key는 `(canonical_project_identity, transition_id)`이며 같은 caller ID를
  두 roots에서 재사용해도 project/run identity는 distinct, 각 retry receipt는 byte-identical,
  각 DB/JSONL/claim/marker는 exactly once, cross-root write/receipt leakage는 0임. 같은 project에서
  같은 ID와 다른 request body/run identity는 typed conflict와 mutation 0임
- fresh DB뿐 아니라 current PR #13 global-key DB를 migration한 fixture에서도 같은 caller ID를 두
  roots에 재사용할 수 있고, old global row count/digest 보존, scoped receipt/event/pending-event
  exactly-once, DB-loss reconstruction과 response-loss retry가 증명됨. Symlink/case alias는 same
  project, directory delete+same-path recreate와 cross-device/APFS clone은 new project로 분류됨
- actual running process identity가 tested commit/tree와 바인딩됨
- installer/release gaps가 stable PASS로 표시되지 않음

### P2 — Immutable Release Core

Outputs:

- release index schema
- exact dependency lock
- content-addressed core artifact
- expanded cross-version historical legacy provenance catalog
- v4.33 supported-platform runtime subject-set generalization
- exact supported Codex CLI/Desktop host identity and adapter/schema set
- archive safety validator
- artifact attestation policy

Exit gate:

- tracked files만 포함됨
- `.git`, venv, cache, project `.samvil`, untracked file이 0임
- version, commit, tree, asset, dependency identities가 일치함
- same version/different digest가 차단됨
- 지원 platform 목록과 offline 정책이 release index에 명시됨
- supported Codex CLI/Desktop version/build/bundle digest와 config/MCP/approval schema adapter set이
  release index에 exact 명시되고 unknown identity는 mutation 권한을 얻지 못함

### P3 — Transactional Profile Installer

Outputs:

- read-only inventory and planner
- provenance classifier
- secure profile lock and durable journal
- verified backup and content-addressed activation
- platform write-gate, post-gate writable-FD proof and immutable rollback snapshot
- external Codex CLI postcondition adapter
- observable-state recovery
- redacted user receipt and opt-in support bundle

Exit gate:

- 모든 mutation 앞에 durable intent가 있음
- 모든 journal/action/CLI 경계의 exception, SIGTERM, SIGKILL, ENOSPC가 수렴함
- pre-opened writable FD를 immutable flag가 revoke한다고 가정하지 않고 post-gate inventory와
  snapshot/source equality로 race를 검출하며 unsupported gate/seal은 pre-cutover block됨
- user/Claude/personal-skill scope가 보존됨
- restart 전에는 `COMMITTED`가 불가능함
- startup attestation 뒤 durable commit receipt/ready token/serving intent 전 normal tool
  advertisement와 stateful tool/project/DB write가 0임
- serving intent가 durable해진 뒤 failure는 automatic rollback 대신 roll-forward 또는
  `RECOVERY_REQUIRED`로 수렴함
- concurrent user edit를 rollback이 덮어쓰지 않음

### P4 — Runtime and cross-host compatibility

Outputs:

- runtime health identity extension
- pending transaction self-attestation
- old/new Claude and Codex shared DB matrix
- legacy Claude holdback과 host manual/auto refresh characterization matrix
- pre-refresh Claude process quiescence와 cold-process marketplace memo invalidation matrix
- exact Codex CLI version/Desktop app build/bundle digest와 config/MCP/approval adapter-schema matrix
- future Codex CLI/Desktop release watcher and rollout kill-switch
- CLI/Desktop profile split detection
- trusted project config-layer inventory
- per-project first-open recovery contract

Exit gate:

- old Claude + new Codex, new Claude + old Codex read/write 검증
- release index의 supported Codex CLI/Desktop identity와 exact adapter/schema mapping만 profile
  mutation 가능하고 unknown/drift identity는 pre-mutation `BLOCKED_ENVIRONMENT`임
- 새 Codex CLI/Desktop release는 isolated install/restart/MCP/project compatibility suite와 exact
  mapping receipt 전 supported set에 들어가지 않으며 watcher가 v4.33 rollout을 hold함. 이미
  자동 업데이트된 unknown host behavior를 소급 차단할 수 있다고 주장하지 않음
- 두 host의 same-project transition이 중복되지 않음
- 한 host rollback 후 다른 host가 계속 안전하게 동작함
- Desktop restart 뒤 root/core/activation/transaction identity가 일치함
- Desktop/MCP startup과 concurrent first tool request에서 serving intent 전 normal advertisement/
  write 0, intent 뒤 exact capability receipt가 증명됨
- exact refreshed empty/pause catalog와 official `source.ref` absent lineage에서 모든 pre-refresh
  Claude process가 종료된 뒤 시작한 cold process인 `REFRESHED_PAUSE_COLD` exact v4.32.2 fixture가
  manual refresh, auto-update scheduler의 deterministic 0--600초 경계 실행, 두 번의 complete
  Claude restart 뒤에도 installed SAMVIL root/cache, selection, global settings/MCP row, running
  legacy runtime 변경 0임. Marketplace source checkout/catalog의 expected quarantine 전환은
  별도 digest로 기록함
- stale pre-switch catalog entry, refresh failure, 30초 recent-cache skip, auto-update fixture는
  install 또는 downgrade 가능성을 `STALE_CATALOG_RISK_OBSERVED`로 기록하며 holdback PASS에
  포함하지 않음
- refresh 전 process A가 old installable row를 memoize하고 process B가 disk catalog를 exact
  pause로 refresh한 뒤 A가 install을 시도하는 two-process actual fixture를 실행함. Cached entry,
  resolved install location의 pre/post inode/tree, installed tree digest, executable/auto-loaded
  surface와 settings/selection mutation을 inert original-tree control과 비교함. Exact
  `BASELINE_EQUIVALENT_OLD_ACTIVE` 또는 `PASSIVE_ONLY_NO_WORSE`만
  `STALE_HOST_MEMORY_RISK_OBSERVED`와 P5 recovery input으로 넘기며, switch-attributable active/hybrid,
  downgrade/uninstall, 추가 settings/selection mutation 또는 class 불명은
  `SEMANTIC_FUSE_OR_UNKNOWN`으로 Stage A/bridge merge를 차단하고 live면 Stage R을 실행함
- v4.33 Codex bootstrap은 installed Claude SAMVIL root/cache, selection, global settings/MCP row를
  변경하지 않고 Codex native activation/runtime만 독립적으로 증명함
- arbitrary project config coverage를 universal green으로 과장하지 않음

### P5 — Lifecycle and release evidence

Outputs:

- one-command user bootstrap
- no-gh/no-auth/no-TTY/no-system-Python self-contained online bootstrap and verified offline bundle
- install, repeat, update, rollback, uninstall, reinstall, downgrade policy
- RC→stable reused-subject-closure release-receipt promotion and persistent accepted-release high-water
- durable opened-project/shared-DB compatibility ledger and post-use rollback preflight
- active-runtime rollback/uninstall quiescence and restart reconciliation
- stale catalog/process-memory residual classification and v4.33 recovery handoff
- RC/stable publisher choreography
- machine-readable acceptance evidence
- canary and stable decision checklist

Exit gate:

- clean, legacy, hybrid, modified, foreign fixture가 예상 terminal state로 수렴함
- blocked fixture에서 scoped Merkle digest가 동일함
- RC와 stable core archive digest가 byte-identical함
- RC와 stable index, provenance, attestation은 각자의 ref, commit, channel을 가리키며 서로
  다른 release identity를 가짐
- approved RC→stable promotion은 current on-disk core/runtime/activation/profile identity가 RC
  installed receipt와 exact equal하고 `promotion_reused_subject_closure` equality도 증명한 뒤
  payload/profile/activation/restart mutation 0으로 verified stable receipt/high-water만 durable하게
  전진하며 response-loss retry가 같은 receipt로 수렴함. Closure drift는 normal verified update로
  라우팅됨
- 일반 install/update는 runtime attestation 뒤 release-acceptance intent를 먼저 durable하게 쓰고,
  installed release receipt와 monotonically advanced high-water를 atomic pair로 확정한 다음 두 digest를
  bind한 commit receipt→ready token→serving intent 순서로만 진행함. Acceptance 뒤 crash는 old release
  automatic rollback 없이 exact roll-forward 또는 `RECOVERY_REQUIRED`로 수렴함
- normal uninstall 뒤 trust-history tombstone/high-water가 남고 reinstall-old/replayed signed
  release가 차단됨. Purge/downgrade는 explicit authorization 없이는 불가능함
- online public asset fixture는 `gh` absent, GitHub auth absent, stdin closed/no TTY와 system Python
  absent에서도 exact-version self-contained bootstrap 한 명령으로 성공함. Outer download는
  private temp, pinned digest/code-signature, no pipe-to-shell이며 protected scope는 verification 뒤에만
  열림
- verified warm-offline bundle은 network 0으로 같은 transaction을 완료함. Cold-offline/no-bundle은
  temp와 protected-scope mutation 0 `BLOCKED_ENVIRONMENT`; mid-download network cut은 partial temp를
  지우고 protected-scope digest unchanged receipt로 끝남
- pre-runtime failure rollback과 post-`COMMITTED` user rollback이 분리되고, post-use rollback은
  every opened project/shared DB의 target-old-runtime compatibility proof가 없으면 mutation 전에 block됨
- active CLI/Desktop/MCP가 있으면 rollback/uninstall은 deactivation epoch를 전진시키고 request
  admission을 fence한 뒤 payload/backup을 보존한 `PENDING_RESTART` reason으로 끝나며 relevant
  process 0/new-session proof와 post-drain ledger/consent 재검증 뒤에만
  planned operation에 따라 `ROLLED_BACK`/`UNINSTALLED`/`UNINSTALLED_DATA_RETAINED`가 됨
- uninstall preflight는 every opened project/shared-DB ledger entry를 분류함. Missing/inaccessible
  entry는 pre-mutation block, backward-readable 또는 completed export는 normal `UNINSTALLED`,
  forward-only data는 default block임. Explicit retain-data consent가 있으면 compatible
  reinstall/export payload와 trust-history를 삭제하지 않고 `UNINSTALLED_DATA_RETAINED`로 끝나며
  exact unreadable scope와 recovery command를 receipt에 남김
- `UNINSTALLED_DATA_RETAINED`는 same/newer compatible release의 verified reinstall로
  `COMMITTED`까지 round-trip함. Failed/replayed/wrong-release reinstall은 retained data/payload/
  trust-history를 byte-identical하게 보존하고 mutation 0 또는 `RECOVERY_REQUIRED`로 끝남
- Codex CLI와 Desktop actual-runtime evidence는 current v4.33 stable asset을 가리키고,
  Claude holdback evidence는 signed legacy catalog/quarantine identity와 unchanged legacy
  runtime을 가리킴
- `REFRESHED_PAUSE_COLD` Claude holdback fixture는 all pre-refresh process 0, default quarantine,
  manual/auto refresh, 두 번의 restart 뒤에도 installed SAMVIL root/cache, selection, global
  settings/MCP row, running runtime을 유지하고 v4.33 Codex activation은 그 상태와 독립적으로
  정상 동작함. Running old process memo residual은 별도 typed receipt와 recovery handoff를 가짐
- stable tag, Release, asset, index digest가 일치함
- startup→commit receipt→ready token→serving intent 각 경계의 SIGKILL/ENOSPC/response-loss가
  intent 전에는 capability-closed safe reconcile되고, intent 뒤에는 first serving receipt가
  유실돼도 automatic rollback 0임

---

## 10. Transaction boundary

Profile installer의 공통 상태 머신은 다음이다.

```text
PLANNED
  → PREPARED
  → BACKUP_VERIFIED
  → PAYLOAD_VERIFIED
  → CUTOVER_INTENT
  → CUTOVER_RECONCILING
  → ON_DISK_VERIFIED
  → PENDING_RESTART
  → ATTESTATION_ONLY_RUNTIME
  → RUNTIME_ATTESTED
  → RELEASE_ACCEPTANCE_INTENT_DURABLE
  → INSTALLED_RELEASE_RECEIPT_AND_HIGH_WATER_DURABLE
  → COMMIT_RECEIPT_DURABLE(bind installed-receipt/high-water digests)
  → READY_TOKEN_DURABLE
  → SERVING_INTENT_DURABLE
  → TOOL_SERVING_VERIFIED
  → COMMITTED

Failure:
  ROLLBACK_INTENT
    → ROLLBACK_RECONCILING
    → ROLLED_BACK | RECOVERY_REQUIRED
```

Recovery는 journal phase 문자열만 믿지 않고 현재 관찰 상태를 다시 inventory하여
결정한다.

- 모든 resource가 pre-state면 rollback 완료
- 모든 resource가 target-state이고 activation decision이 durable하면 roll-forward
- 알려진 transaction intermediate면 마지막 durable decision에 따라 reconcile
- foreign fingerprint, concurrent owned-key edit, backup 변조가 있으면
  `RECOVERY_REQUIRED`

`ATTESTATION_ONLY_RUNTIME`부터 serving intent 전까지 normal tool advertisement와
state/project/shared-DB write는 0이다. Commit receipt+ready token은 serving intent를 쓸 권한만
연다. Serving intent가 durable해진 transaction은 capability/first-response receipt가 아직 없어도
automatic rollback할 수 없으며 exact roll-forward 또는 `RECOVERY_REQUIRED`만 허용한다.

`RELEASE_ACCEPTANCE_INTENT_DURABLE` 뒤에는 accepted high-water를 낮추는 automatic rollback이
없다. Installed receipt/high-water atomic commit, 그 pair를 bind한 commit receipt, ready token의
순서를 건너뛴 observed state는 capability closed다. Response-loss retry는 같은 release/closure와
trust-ledger generation으로만 수렴한다.

Every first project/shared-DB write 전에는 canonical resource identity에 귀속된 compatibility
ledger에 tokenized project filesystem/DB identity, compatibility epoch, pre/post schema, minimum
reader/writer version, release/transaction/profile/host identity와 backward-compatibility proof를 먼저
durable하게 기록한다. Profile-local ledger는 이 resource-scoped ledger의 index/cache일 뿐 정본이
아니다. 모든 supported writer는 write 직전 resource epoch를 CAS로 확인하고 bounded lease를 얻으며,
commit 직전에도 epoch/generation을 재검증한다. Raw absolute path는 user receipt에 쓰지 않는다.
Resource ledger/lock을 완전하게 기록하거나 공유할 수 없으면 project/DB write를 열지 않는다.

Rollback/uninstall처럼 compatibility를 낮출 수 있는 operation은 affected every resource의 write
fence를 먼저 획득해 새 supported-writer lease를 막고 기존 lease를 drain한다. 그 same resource
lock/CAS critical section 안에서 ledger/current schema/data/consent digest를 재검증하고 reverse
cutover intent를 publish한다. 다른 Codex profile, Desktop, Claude 또는 offline/legacy writer가 이
resource lease에 참여하지 못하거나 exclusive OS/database lock과 process/FD quiescence로 배제되지
않으면 host/profile mutation 전에 block한다. 단순 host process 종료나 profile-local epoch만으로
shared DB quiescence를 주장하지 않는다.

- Serving intent 전 failure rollback: project write 0이므로 host/profile pre-state로 automatic recovery 가능
- `COMMITTED` 뒤 explicit rollback: ledger의 every touched project/DB가 target old runtime과 exact
  compatible하거나 signed migration-back plan이 있을 때만 진행. Missing, moved, inaccessible,
  forward-only entry 하나라도 있으면 host/profile mutation 전에 block
- Uninstall preflight도 every touched ledger entry를 읽는다. No-write ledger 또는 every data set이
  remaining host에서 backward-readable/portable하거나 verified export가 끝났을 때만 normal removal을
  허용한다. Missing/inaccessible entry는 block한다. Forward-only data는 기본 block이며, 사용자가
  exact affected scope와 reinstall requirement를 보고 explicit retain-data authorization을 승인한
  경우에만 activation을 제거한다. 이 경우 compatible runtime payload, transaction backup,
  trust-history와 export path를 보존하고 `UNINSTALLED_DATA_RETAINED`로 끝낸다.
- Rollback/uninstall 시작 시 durable deactivation intent와 ready-token revocation을 먼저 fsync하고
  profile deactivation epoch만 먼저 전진시켜 해당 profile의 process/request admission을 fence함.
  Active process/detached child가 0으로 증명된 뒤에만 affected canonical resource lock을 획득하고
  compatibility epoch를 전진시켜 write admission을 fence함. 모든 tool admission은 project/DB 접근 전에
  current activation+deactivation epoch를 확인하고, resource fence가 시작된 write는 resource epoch도
  확인해 old epoch lease를 거부함. Existing resource lease를 drain한 뒤 same resource lock/CAS 안에서
  ledger, current data와 retain-data consent digest를 다시 검증하고 그 후에만 reverse cutover함.
  Nonparticipating legacy/offline writer를 exclusive하게 배제할 수 없으면 pre-mutation block함
- Active CLI/Desktop/MCP 또는 detached child가 있으면 payload/backup을 지우지 않고 reason-coded
  `PENDING_RESTART`로 끝냄. Complete process quiescence와 restart/new-session reconcile 뒤에만
  `ROLLED_BACK`/`UNINSTALLED`/`UNINSTALLED_DATA_RETAINED`

Rollback/uninstall deactivation state machine은 다음이다.

```text
DEACTIVATION_PLANNED
  → DEACTIVATION_INTENT_DURABLE(profile epoch + 1, operation, preflight/consent digest)
  → REQUEST_ADMISSION_FENCED
  ├─ active process/detached child present
  │    → PENDING_RESTART_PRE_CUTOVER(payload/backup preserved, activation unchanged)
  │    → PROCESS_QUIESCENCE_VERIFIED_ON_RESUME
  │    → RESOURCE_WRITE_FENCES_ACQUIRED(resource epochs + lease set)
  └─ process quiescence already verified
       → RESOURCE_WRITE_FENCES_ACQUIRED(resource epochs + lease set)
  → OLD_EPOCH_LEASES_DRAINED
  → LEDGER_AND_CONSENT_REVALIDATED_UNDER_RESOURCE_CAS
  → REVERSE_CUTOVER_INTENT
  → REVERSE_CUTOVER_VERIFIED
  → RESOURCE_WRITERS_REOPENED_AT_NEW_EPOCH
  ├─ rollback
  │    → PREVIOUS_RUNTIME_ATTESTATION_ONLY
  │    → PREVIOUS_RUNTIME_ATTESTED_AT_NEW_PROFILE_EPOCH
  │    → PREVIOUS_READY_TOKEN_DURABLE
  │    → PROFILE_ADMISSION_REOPENED_AT_NEW_EPOCH
  │    → ROLLED_BACK
  └─ uninstall
       → PROFILE_ADMISSION_DISABLED_DURABLE
       → UNINSTALLED | UNINSTALLED_DATA_RETAINED

Abort before resource fence:
  PROFILE_DEACTIVATION_ABORT_INTENT_DURABLE(unchanged activation + current resource epochs)
    → UNCHANGED_PROFILE_AND_RESOURCE_STATE_REVERIFIED
    → CURRENT_RUNTIME_ATTESTATION_ONLY_AT_NEW_PROFILE_EPOCH
    → CURRENT_RUNTIME_ATTESTED_AT_NEW_PROFILE_EPOCH
    → CURRENT_READY_TOKEN_DURABLE
    → PROFILE_ADMISSION_REOPENED_AT_NEW_EPOCH
    → CURRENT | RECOVERY_REQUIRED

Abort after resource fence but before reverse cutover:
  DEACTIVATION_ABORT_INTENT_DURABLE(unchanged activation + new resource epoch)
    → UNCHANGED_RESOURCE_STATE_REVERIFIED
    → RESOURCE_WRITERS_REOPENED_AT_NEW_EPOCH
    → CURRENT_RUNTIME_ATTESTATION_ONLY_AT_NEW_PROFILE_EPOCH
    → CURRENT_RUNTIME_ATTESTED_AT_NEW_PROFILE_EPOCH
    → CURRENT_READY_TOKEN_DURABLE
    → PROFILE_ADMISSION_REOPENED_AT_NEW_EPOCH
    → CURRENT | RECOVERY_REQUIRED
```

Revoke/epoch advance 뒤 admission path가 stale profile 또는 resource epoch를 받으면 typed not-ready와
write 0이다. Existing lease는 epoch-bound journal/ledger update를 끝내거나 cancel receipt를 남긴 뒤
drain된다. Drain 중 새 project/DB write가 생겼거나 consent/ledger digest가 달라지면 reverse cutover
전에 plan을 폐기하고 다시 사용자 승인을 받는다. Revalidation 뒤 reverse cutover 전 concurrent
write도 같은 resource CAS/generation mismatch로 차단된다. Response loss는 same deactivation/resource
epoch와 operation identity로 idempotent하게 수렴한다. Epoch fencing을 우회하는 detached 또는
nonparticipating writer는 automatic cutover 대신 pre-mutation block, `PENDING_RESTART` 또는
`RECOVERY_REQUIRED`다.

Resource fence는 terminal 뒤 영구히 남지 않는다. Reverse cutover가 exact post-state로 검증되면
새 compatibility epoch와 허용 writer-version set을 durable하게 publish하고 그 epoch에서 supported
writer lease를 다시 연 뒤 terminal receipt를 쓴다. Drift/사용자 취소로 cutover 전에 plan을
폐기할 때 resource fence 전이면 activation/data와 current resource epochs unchanged를 재검증하고
current runtime을 새 profile epoch에서 attestation-only로 검증해 new ready token을 durable하게 만든
뒤 profile admission을 reopen한다. Resource fence 뒤면 같은 resource lock
아래 unchanged state를 재검증하고 monotonic new resource epoch로 writer를 reopen한 뒤 profile
쪽도 같은 current-runtime attestation→new ready→admission reopen 순서를 수행한다. Resource/profile
reopen receipt 또는 new-epoch ready token 중 하나라도 없으면 `CURRENT`가 아니다. Abort attestation/
ready/reopen failure는 unchanged payload/backup을 보존한 capability-closed `RECOVERY_REQUIRED`다.
Epoch를 되감지 않는다. Fence release/reopen receipt를 durable하게 만들 수 없으면 다른 host writer를
임의로 열지 않고 `RECOVERY_REQUIRED`로 남긴다. Local profile의 restart fence는 별도다.
Pre-cutover `PENDING_RESTART`에서는 shared-resource fence나 resource epoch advance를 아직 시작하지
않으므로 compatible한 다른 host는 unchanged current resource epoch에서 계속 동작할 수 있다.
Resume은 process 0과 unchanged activation/payload/backup/deactivation intent를
먼저 증명한 뒤 resource fence를 새로 획득하고 ledger/consent를 다시 읽어야 하며, old pre-restart
revalidation 결과를 재사용하지 않는다.

Rollback success는 resource cutover만으로 완료되지 않는다. Previous runtime을 normal capability가
닫힌 attestation-only mode로 새 profile epoch에서 검증하고, exact previous activation/receipt에 묶인
ready token을 durable하게 만든 뒤 profile admission을 reopen해야 `ROLLED_BACK`다. Attestation/ready/
reopen 실패는 previous payload와 backup을 보존하고 profile capability closed
`RECOVERY_REQUIRED`다. Uninstall은 반대로 disabled profile-admission receipt가 terminal 선행조건이며
normal ready token을 다시 만들지 않는다.

RC→stable reused-subject-closure promotion은 별도 transaction이다.

```text
RC_PROMOTION_PLANNED
  → STABLE_INDEX_ATTESTED
  → CURRENT_RC_INSTALLED_STATE_EQUAL
  → REUSED_SUBJECT_CLOSURE_EQUAL
  → PROMOTION_INTENT_DURABLE
  → STABLE_RELEASE_RECEIPT_DURABLE
  → HIGH_WATER_ADVANCED
  → RC_PROMOTED_STABLE
```

이 path의 current core/runtime/activation/profile identity, installed/reused fixed subjects,
runtime/wheel/builder/launcher manifests, dependency lock,
activation schema와 approval-policy renderer mutation은 0이다. Malformed stable identity, modified RC
receipt/current state/closure, stable→RC downgrade는 promotion intent 전에 block한다. Response loss/retry는 같은
stable receipt/high-water identity로 idempotent하게 수렴한다.

---

## 11. Ownership rules

`owned`와 `exclusive`를 구분한다.

- `owned`: SAMVIL이 생성했다는 provenance가 증명됨
- `exclusive`: 다른 profile이나 host가 소비하지 않는다는 것까지 증명됨

Default Codex profile upgrade는 profile-local resource만 변경한다. shared home, Claude
cache, 다른 `CODEX_HOME`, project data는 변경하지 않는다.

Legacy resource 자동 처리에는 다음 중 하나가 필요하다.

- signed historical provenance catalog exact match
- prior installer receipt exact match

경로명, `samvil`이라는 registration name, version 문자열, local Git tag는 충분한
증거가 아니다.

---

## 12. User experience contract

### 12.1 Fresh install

```text
SAMVIL 4.33.0 설치 준비 완료

- 새 Codex profile: 안전하게 준비됨
- 개인 스킬: 변경하지 않음
- Claude Code: 변경하지 않음
- 기존 SAMVIL 설치: 없음
```

재시작이 필요하면:

```text
상태: PENDING_RESTART (INSTALL)

Codex를 완전히 종료한 뒤 다시 실행해 주세요.
새 MCP가 확인되기 전에는 설치 완료로 표시하지 않습니다.
```

### 12.2 Verified update

```text
SAMVIL 4.33.0 업데이트 준비 완료

- 기존 Codex 설정: 안전하게 확인됨
- 개인 스킬: 변경하지 않음
- Claude Code: 변경하지 않음
- 이전 SAMVIL 상태 백업: 완료
```

Desktop 또는 old MCP가 실행 중이면:

```text
상태: PENDING_RESTART (UPDATE)

Codex를 완전히 종료한 뒤 다시 실행해 주세요.
새 MCP 확인 전까지 이전 설치는 보존됩니다.
```

Fresh install과 update 모두 재시작한 MCP가 receipt와 같은 identity를 보고한 뒤에만 완료한다.

Rollback이 process admission fence 뒤, resource cutover 전에 재시작을 기다리면:

```text
상태: PENDING_RESTART (ROLLBACK)

Codex와 연결된 MCP를 완전히 종료해 주세요.
이전 버전과 데이터 백업은 그대로 보존되며, 공유 프로젝트 writer가 남아 있으면 롤백하지 않습니다.
```

Uninstall이면:

```text
상태: PENDING_RESTART (UNINSTALL)

Codex와 연결된 MCP를 완전히 종료해 주세요.
재시작 확인 뒤 SAMVIL activation만 제거합니다. 프로젝트 데이터와 trust history는 자동 삭제하지 않습니다.
```

Forward-only data를 보존하는 uninstall이면 `PENDING_RESTART (UNINSTALL_RETAIN_DATA)`와 affected
scope/reinstall requirement를 함께 보여 준다. 다른 profile/Claude/legacy writer가 resource fence에
참여하지 못하면 `BLOCKED_USER_STATE (SHARED_RESOURCE_WRITER_ACTIVE)`로 끝내고 종료할 process와
재시도 명령만 안내한다. Operation 종류가 없는 generic `PENDING_RESTART` copy는 허용하지 않는다.

### 12.3 Modified or foreign state

```text
안전을 위해 업데이트를 중단했습니다.
아무 파일도 변경하지 않았습니다.

원인: 사용자가 수정했거나 소유권이 불명확한 Codex 설정
```

### 12.4 Existing projects

Host upgrade는 project file을 변경하지 않는다. 프로젝트를 처음 열 때 해당
프로젝트만 compatibility check와 recovery를 수행한다. 한 프로젝트가 blocked여도
다른 프로젝트와 host install은 유지한다.

### 12.5 Legacy updater users

- exact v4.32.2 사용자는 bridge를 별도로 설치하지 않는다.
- old updater가 조회하는 GitHub default branch는 manifest version을 `4.32.2`로 유지한
  quarantine fuse이므로 successful version discovery의 정상 v4.32.2 fixture는
  `CURRENT == LATEST`에서 plugin/cache mutation 0으로 끝난다.
- 기존 updater는 GitHub 조회 실패 시 `LATEST=unknown`으로도 clone을 계속할 수 있다. 이
  residual path는 no-write라고 주장하지 않고 `LEGACY_RISK_OBSERVED`로 검증하며, 그래서
  사용자에게 old updater를 실행하지 말라고 명시한다.
- exact refreshed quarantine catalog는 SAMVIL installable entry가 없지만, 신규 raw marketplace
  install의 mutation 0 not-found PASS는 모든 pre-refresh Claude process가 종료된 뒤 시작한 cold
  process의 `REFRESHED_PAUSE_COLD`에만 적용한다. Marketplace source checkout 자체의 expected
  refresh는 별도 receipt로 기록한다. Pre-switch stale catalog, refresh failure, recent-cache skip은
  `STALE_CATALOG_RISK_OBSERVED`, 실행 중 process의 old memo는
  `STALE_HOST_MEMORY_RISK_OBSERVED`이며 universal no-write로 주장하지 않는다.
- Discovery-failure old clone이 fuse를 받으면 automatic hook/MCP surface는 passive로 수렴하지만
  old rename/delete risk 자체는 `LEGACY_RISK_OBSERVED`다. 신규 설치는 v4.33 bootstrap 공개
  전까지 공식적으로 일시 중단하고 raw marketplace install/update를 안내하지 않는다.
- corrupt/unknown/older state에는 이 no-op을 과장하지 않으며 old updater 실행을 안내하지
  않는다.
- v4.33 공식 전환은 version-independent bootstrap 명령을 primary path로 사용한다.
- v4.33 stable 뒤에도 legacy quarantine default는 별도 sunset proof 전까지 유지한다.
- clean bridge acquisition은 release machinery canary이며 existing-user migration prerequisite가
  아니다.

---

## 13. Verification program

### 13.1 Commit gate

각 commit은 하나의 불변조건만 구현한다.

1. focused failure test RED 확인
2. 최소 implementation
3. focused tests GREEN
4. 관련 fixture GREEN
5. `bash scripts/pre-commit-check.sh` 전체 PASS
6. 한글 한 줄 commit message

`--no-verify`, weakened assertion, timing threshold 완화, flaky retry로 gate를 통과시키지
않는다.

### 13.2 PR gate

- 전체 unit/property tests
- isolated profile integration tests
- pairwise user-state matrix
- process, filesystem, network failure injection
- privacy and redaction tests
- RC→stable promotion response-loss/retry, stable→RC replay rejection and accepted-high-water tests
- 일반 install/update의 release-acceptance intent, atomic installed-receipt/high-water pair,
  pair-bound commit receipt 각 경계의 SIGKILL/ENOSPC/response-loss와 old-release replay tests
- RC→stable reused-subject-closure drift rejection and normal-update routing tests
- RC promotion current core/runtime/rendered-approval/profile drift rejection tests
- uninstall/reinstall/downgrade tombstone, active-runtime/detached-child and project-ledger
  rollback/uninstall allow-block-retain-data tests
- deactivation epoch advance, revoke 전/후 concurrent admission, old-epoch lease drain, detached child,
  post-drain ledger/consent drift와 response-loss fencing tests
- canonical project/shared-DB resource epoch/lease/CAS, 다른 Codex profile/Claude writer가
  revalidation과 reverse cutover 사이에 쓰는 race, nonparticipating legacy/offline writer
  pre-mutation block tests
- reverse-cutover success와 pre-cutover abort 각각의 monotonic resource-epoch reopen,
  reopen receipt ENOSPC/SIGKILL/response-loss, local `PENDING_RESTART` 중 compatible other-host writer
  continuation tests
- active pre-resource-fence cancel은 resource epoch/write availability unchanged + new profile epoch
  current-runtime attestation/ready/admission reopen, post-resource-fence cancel은 unchanged data +
  monotonic resource writer reopen 뒤 같은 current-runtime attestation/ready/profile reopen으로 분리되고
  각 receipt 누락·ENOSPC·SIGKILL·response-loss 시 `CURRENT`를 거부하는 tests
- active runtime/detached child는 activation unchanged pre-cutover `PENDING_RESTART`, restart 뒤
  process 0→fresh resource-fence acquisition→ledger/consent revalidation→cutover 순서를 강제하고
  restart 전 reverse cutover/terminal receipt를 거부하는 tests
- rollback cutover 뒤 previous-runtime attestation-only→new-epoch ready→profile-admission reopen 전
  `ROLLED_BACK` 거부, 각 경계 failure capability-closed recovery와 uninstall admission-disabled
  terminal separation tests
- exact Codex CLI/Desktop identity/schema matrix and new-host watcher unknown-identity block tests
- two-process stale marketplace memo actual fixture and cold-process invalidation proof
- current-HEAD Desktop에서 display label != canonical project path인 actual fixed-transition retry,
  byte-identical receipts와 DB/JSONL/claim/marker exactly-once proof
- same display label/two canonical roots interleaved transition actual fixture with distinct identities,
  same caller transition ID scoped per project, per-root exactly-once and cross-root write/leakage 0
- current PR #13 global transition/event-key DB → scoped-key migration, resolvable-row advance와
  missing/recreated/orphan row byte-preserving quarantine, quarantined public-id localized block,
  unrelated project/transition continuation, symlink/case alias, delete+same-path recreate, APFS
  clone/cross-device copy와 DB-loss reconstruction tests
- existing written project의 ordered DB/JSONL/claim/marker `legacy_profile_history_digest`, profile pending
  baseline→resource-locked singleton nonce/marker→per-profile binding join→profile CAS finalize,
  A→B→A/B→A→B/concurrent two-`CODEX_HOME` ordering과 stale joined-profile catch-up, exact repeat,
  same-profile different-history,
  각 경계 crash/response-loss와 captured-history drift/collision block tests
- same-anchor APFS project snapshot rollback(local marker old/profile DB new), profile/shared DB
  rollback(local marker new/DB old)의 canonical-superset catch-up, exact journaled one-side-ahead crash
  reconcile와 divergent lineage `PROJECT_STATE_ROLLBACK_DETECTED` mutation-0 tests
- joined profiles의 A→B→A/B→A→B alternating normal transitions, concurrent head CAS, foreign-profile
  canonical-record catch-up/reconstruction, same project+transition ID same-body canonical receipt replay와
  different-body `TRANSITION_ID_CONFLICT` exactly-once tests
- transition intent→profile pending rows→project JSONL/claim side-effect fsync→signed journal/head commit
  point→profile finalize 각 경계 ENOSPC/SIGKILL/response-loss, head-before-side-effect rejection과
  pre-head prepared-side-effect reconcile tests
- forged hash-valid join/transition extension, raw/software key substitution, signing-broker code identity/
  descriptor swap, wrong project/head/profile, join nonce replay/expiry, key epoch rollback/revocation,
  old+new dual-sign rotation과 recovery authorization tests
- foreign device-root self-authorized later join, insufficient/stale countersign quorum, wrong current
  head/root-set/key epochs/revocation generation, threshold downgrade, same-device new-profile join과
  single-root sequential peer revocation→1-of-1 takeover, every root-set mutation pre-change quorum,
  no-surviving-root offline-key/guardian/account-authority recovery, user-presence-only/foreign writable-copy
  recovery rejection과 explicit import-fork tests
- rogue device-root/profile-key pin substitution, mutable trust-ledger replacement, Keychain access-group/
  application-label collision, copied profile/anchor mismatch, head/generation rollback, broker code-directory
  drift와 device-root old+new dual-sign rotation tests
- trust-ledger successor staging→Keychain pending CAS→ledger file/dir fsync→anchor finalize 각 경계의
  SIGKILL/ENOSPC/CAS failure/response-loss, exact old-file abort와 exact successor-file finalize recovery tests
- project `ROOT_SET_MUTATION_INTENT`→affected anchor overlap prepare receipts→project root-set head commit→
  anchor finalize→separate old-root retirement 각 경계 fault injection, pre-head all-old abort/post-head
  all-new roll-forward, B prepare→offline→A abort/write-continue→B return, B prepare→A commit/write-continue→
  B return, never-return+signed quarantine, `ROOT_SET_MUTATION_SETTLED` response-loss가 global write를
  막지 않음, mixed/offline/stale profile catch-up와 concurrent rotation/revocation CAS tests
- three-angle independent review:
  - transaction/security
  - real-user state coverage
  - cross-host/release lifecycle

P1/P2 finding이 있으면 수정 후 전체 review를 반복한다.

모든 자동 fixture는 격리된 temporary `HOME`, `CODEX_HOME`, project root를 사용한다.
실제 사용자 profile과 literal user-owned path는 읽기, 쓰기, stage 대상에서 제외한다.

### 13.3 RC gate

- exact prerelease asset 사용
- actual Codex CLI and Claude repeated runtime proof
- actual Codex Desktop restart proof
- attestation-only startup, serving-intent-before-first-tool barrier와 post-intent no-auto-rollback proof
- public online asset with `gh` absent, auth absent, no TTY and system Python absent → self-contained
  exact-version bootstrap success
- verified warm-offline bundle → network 0 success; cold-offline/no-bundle → pre-mutation
  `BLOCKED_ENVIRONMENT`
- mid-download network cut → partial-temp cleanup and protected-scope mutation 0
- actual cross-device boundary
- all journal phases SIGKILL and ENOSPC
- rollback, uninstall, retained-data uninstall, reinstall
- pre-serving-intent failure rollback vs post-`COMMITTED` project-ledger rollback block/allow matrix
- active Desktop/CLI/MCP rollback/uninstall → deactivation epoch advance, request-admission fence,
  ready revoke, old-epoch operation drain, post-drain ledger/consent revalidation, reason-coded
  `PENDING_RESTART`, process-quiescent terminal proof
- active-process × explicit retain-data uninstall → operation-qualified `PENDING_RESTART` →
  quiescent `UNINSTALLED_DATA_RETAINED`
- uninstall trust-history retention, tombstone tamper and reinstall-old replay rejection
- uninstall project-ledger normal/block/explicit-retain-data matrix and retained payload/export proof
- retained-data uninstall → compatible reinstall `COMMITTED` round-trip; failed/replayed reinstall
  retained data/payload/trust-history unchanged

### 13.4 Stable gate

- RC evidence와 stable index가 가리키는 `promotion_reused_subject_closure` exact equality
- stable index, provenance, attestation은 final `release/v4-stable` commit과 stable tag를 가리킴
- exact RC-installed fixture가 current on-disk core/runtime/rendered approval/profile identity와
  installed receipt equality, stable index/provenance와 reused-subject closure를 검증한 뒤
  payload/profile/activation/restart mutation 0 `RC_PROMOTED_STABLE`로 stable receipt/high-water만
  전진함. Response-loss retry, malformed stable, modified RC receipt/closure와 stable→RC downgrade가
  expected result로 수렴하고 current-state/closure drift는 normal verified update로 라우팅됨
- default `main`, `release/v4-stable`과 holdback 뒤 newly published allowlisted ref의 empty/pause
  marketplace catalog가 exact approved identity를 유지함. All pre-switch Claude processes가 종료된
  뒤 시작한 `REFRESHED_PAUSE_COLD` process에서만 신규 raw install이 not-found이며, existing exact
  v4.32.2는 manual refresh, auto-update 경계 실행, 두 번의 complete restart 뒤 installed SAMVIL
  root/cache, selection, global settings/MCP row, running runtime이 unchanged임. Marketplace source
  checkout/catalog 전환은 별도 expected digest로 기록함
- stale catalog entry, refresh failure, recent-cache skip과 explicit `main`/`release/v4-stable`, historical
  tag/commit, fork/local custom-ref fixture의 observed behavior가 `STALE_CATALOG_RISK_OBSERVED`,
  `PINNED_SOURCE_RISK_OBSERVED` 또는 unsupported receipt로 분리되고 stable PASS에 섞이지 않음
- refresh 전 process-local memo를 유지한 running Claude fixture의 installed bytes와 mutation이
  `STALE_HOST_MEMORY_RISK_OBSERVED`로 분리되고 fuse-only라고 미리 가정하지 않으며, exact
  cached source/install-location/tree 결과와 v4.33 recovery handoff가 stable decision에 포함됨
- exact stable draft assets의 clean/proven-legacy v4.33 bootstrap, restart, actual MCP canary가
  public publish 전에 PASS. P0 bridge gate에서는 default-main fuse no-op/diagnosis와
  `EMPTY_READY` clean bridge canary를 분리함
- exact stable draft public online bootstrap이 `gh`/auth/TTY/system Python 없이 성공하고,
  verified warm-offline은 network 0 성공, cold-offline/no-bundle과 mid-download cut은 각각
  pre-mutation block 및 temp-cleanup/protected-digest-unchanged로 수렴함
- exact stable draft asset을 설치·재시작한 current supported Codex Desktop actual runtime에서
  display label != canonical project path fixture의 `get_stage_envelope → begin_stage → fixed-id
  commit → same-id retry`를 다시 실행함. 두 receipt canonical bytes가 동일하고
  DB/JSONL/claim/marker event가 exactly once이며 receipt가 exact stable release identity에 바인딩됨
- 같은 display label의 두 canonical temporary roots에서 transition을 interleave해 distinct
  project/run identity를 확인함. Same caller transition ID를 두 roots에서 재사용해도 project-scoped
  idempotency, 각 retry byte equality, per-root event exactly once와 cross-root write/receipt leakage 0을
  exact stable draft Desktop runtime에서 재검증함
- current PR #13 global-key DB snapshot을 scoped schema로 fail-safe migration한 뒤에도 위 same-ID
  two-root proof가 통과하고 old row count/digest, foreign keys와 reconstruction identity가 보존됨.
  Symlink/case alias는 same project, delete+same-path recreate와 cross-device/APFS clone은 new project로
  수렴하며 inaccessible/mismatched old root는 old DB를 보존한 pre-mutation block임
- 위 holdback 상태에서 v4.33 bootstrap은 Claude plugin을 update/migrate하지 않고 Codex native
  activation/runtime만 current stable asset으로 수렴함
- public stable URL은 publish 뒤 discovery, digest, repeat-current만 재검증
- normal uninstall 뒤 accepted-release tombstone/high-water가 유지되고 old signed release reinstall은
  explicit downgrade/purge authorization 없이 차단됨
- exact stable runtime uninstall은 project/shared-DB ledger의 backward-readable/exported 상태만
  normal `UNINSTALLED`, missing/inaccessible/forward-only는 default pre-mutation block, explicit
  retain-data consent는 compatible reinstall/export payload를 보존한
  `UNINSTALLED_DATA_RETAINED`로 수렴함
- exact stable retained-data uninstall은 compatible reinstall로 `COMMITTED` round-trip하며 failed,
  replayed 또는 wrong-release reinstall은 retained data/payload/trust-history를 변경하지 않음
- stable updater가 prerelease를 선택하지 않음
- exact `release/v4-stable` SHA, tag, Release, asset, index equality
- evidence artifact에 secret과 개인 절대경로 0

---

## 14. Evidence contract

각 acceptance receipt는 최소한 다음을 포함한다.

```text
schema version
test case ID
verification kind
operation
terminal state and reason codes
release identity
redacted environment identity
fixture axes
transaction ID and attempt
redacted display label and redacted canonical project identity as distinct fields
canonical project identity schema/filesystem-anchor digest and alias/recreation disposition
transition/event storage schema, migration journal and pre/post row/digest integrity verdict
fixed transition ID, first/retry canonical receipt digests and byte-equality verdict
project lineage head/generation, joined-profile binding-set digest, signer key/epoch/revocation and
join-authorization verdict
DB/JSONL/claim/marker side-effect cardinality
cross-root write cardinality and interleaving identity
pending operation, pending phase, pre identity and target identity
acquisition mode, outer bootstrap identity/digest and prerequisite verdict
network/temp cleanup events and protected-scope digest verdict
pre/post scoped Merkle digests
runtime attestation
commit receipt, ready token and serving-intent identity
first tool-serving phase and rollback eligibility
installed release receipt and accepted release high-water identity
current installed-state equality verdict for RC promotion
opened-project/shared-DB compatibility ledger digest
uninstall ledger disposition, retained-data scope and reinstall/export identity
deactivation reason, active-operation drain and process-quiescence identity
deactivation epoch, admission-fence and post-drain ledger/consent revalidation identity
privacy verdict
tested commit/tree
release decision
```

Private transaction journal과 user receipt를 분리한다.

- journal: rollback 원문, local-only, mode `0600`
- backup directory: mode `0700`
- user receipt: absolute path, config value, personal skill name 제외
- support bundle: 명시적 export만 가능하며 path와 secret을 redaction

실제 runtime receipt와 review evidence는 release core payload 밖의 sidecar artifact로
보관한다. evidence-only 갱신이 core bytes를 바꿀 수 없도록 runtime bundle은 explicit
allowlist로 만든다.

Runtime evidence는 readiness check와 분리한다. screenshot 또는 성공 exit code만으로
actual-runtime PASS를 만들 수 없다.

Default-main quarantine transition, quarantine monitor, no-write canary처럼 remote state 뒤에 생기는 receipt도
release evidence sidecar다. Tracked catalog/index/core에 동적 주입하지 않고 release decision이
별도로 소비한다.

---

## 15. Review and stop rules

다음 중 하나면 현재 workstream을 멈추고 다음 단계로 진행하지 않는다.

- 같은 root cause가 두 번 반복됨
- supported fixture가 `RECOVERY_REQUIRED`로 종료됨
- blocked fixture에서 scoped digest가 바뀜
- RC와 stable `promotion_reused_subject_closure`가 다름
- runtime identity가 installed receipt와 다름
- installed release receipt가 accepted high-water보다 먼저 보이거나 commit receipt가 두 digest를
  bind하지 않음
- serving intent 전 normal advertisement/state/project write가 관찰되거나 intent 뒤 automatic
  rollback이 시도됨
- deactivation/resource epoch 뒤 stale process가 새 tool/write lease를 얻거나 resource lock/CAS 아래
  post-drain ledger/consent revalidation 없이 reverse cutover가 진행됨
- global→project-scoped transition/event migration에서 row/digest/foreign-key identity가 보존되지 않음
- project-local marker와 profile/shared-DB monotonic lineage가 journal로 설명되지 않게 감소·분기함
- shared DB compatibility가 증명되지 않음
- default `main` quarantine 또는 explicit `release/v4-stable` stable topology가 깨짐
- persisted evidence가 current tested commit/tree를 가리키지 않음

어려움, 테스트 시간, PR 크기는 gate 완화 사유가 아니다.

---

## 16. Implementation order

이 문서 승인 뒤에도 전체 프로그램 implementation plan을 한 번에 만들지 않는다.

1. v4.32.3 bridge sub-spec 승인
2. bridge implementation plan
3. bridge TDD implementation and release
4. PR #13 integration retarget and closure
5. Release Core sub-spec → plan → implementation
6. Installer sub-spec → plan → implementation
7. Runtime Compatibility sub-spec → plan → implementation
8. Lifecycle/Release sub-spec → plan → implementation
9. RC
10. stable

각 sub-project는 spec review가 끝난 뒤에만 자기 implementation plan을 갖는다.

---

## 17. Program completion

프로그램은 다음 조건을 모두 만족할 때만 완료다.

1. `release/v4-stable`이 exact approved stable tree이고 GitHub default `main`은 exact reviewed
   quarantine-fuse lineage다.
2. v4.33 stable Release asset과 attestation이 공개 검증된다.
3. 지원되는 online 신규/proven-legacy host는 preinstalled `gh`, GitHub auth, TTY와 system Python
   없이 공식 명령 한 번으로 전환되고, verified warm-offline bundle도 한 명령으로 network 0
   전환된다. Cold-offline/no-bundle은 변경 없이 정확히 차단된다.
4. Desktop 사용자는 재시작 전 `PENDING_RESTART`, 재시작 직후 attestation-only를 거쳐 durable
   serving intent 뒤 capability가 열린 다음 `COMMITTED`를 본다.
5. modified, foreign, unsupported 사용자는 mutation 0으로 차단된다.
6. Claude, 개인 skills, 다른 profiles, project data가 각 계약에 따라 보존된다.
7. rollback, uninstall, retained-data uninstall, reinstall이 deactivation epoch, request-admission
   fence, old-epoch operation drain, post-drain ledger/consent revalidation, process-quiescence와 every touched project/shared-DB compatibility ledger의 allow/block/
   explicit-consent disposition을 포함한 actual runtime으로 증명되고 retained-data reinstall은
   `COMMITTED` round-trip과 failed/replay unchanged를 가짐.
8. actual Codex CLI와 Desktop receipt는 v4.33 stable asset identity와 일치하고, Claude
   holdback receipt는 signed legacy catalog/quarantine identity와 unchanged legacy runtime을
   증명한다.
9. stable installed-release receipt와 accepted-release high-water/tombstone이 exact current이고,
   RC promotion은 current installed-state와 reused-subject closure equality를 증명하며 stale catalog/process-memory residual은
   supported PASS와 분리된 recovery input으로 남는다.
10. Exact stable draft asset을 설치한 Codex Desktop actual runtime의 display-label/canonical-path
    mismatch와 same-label/two-root same-caller-ID interleaved fixed-transition retry receipt가 각각
    byte-identical/exactly-once/cross-root-write-and-receipt-leakage-0이며 published stable release identity와 같은
    core/activation/runtime identity를 가리킨다.
