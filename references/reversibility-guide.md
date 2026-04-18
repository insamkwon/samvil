# Reversibility Awareness Guide (v2.5.0+, Manifesto v3 P10)

> 되돌릴 수 있는 행동은 빠르게, 없는 행동은 신중히. 사용자 승인 필수.

---

## 🟢 Reversible Actions (즉시 진행)

Circuit Breaker만 적용. 사용자 매번 확인 불필요.

- 파일 수정 (git으로 롤백 가능)
- `.samvil/state.json` 업데이트
- `.samvil/events.jsonl` 로그 기록
- `.samvil/qa-results.json` 업데이트
- `.samvil/progress.md` 업데이트
- seed 버전 내부 저장
- Local git commit (git reset으로 복원 가능)
- Interview state 업데이트

## 🟡 Semi-reversible (일부 정보 소실, 주의)

한 번의 확인 권장. Auto-approve 옵션 가능.

- `git commit` (amend는 가능하지만 번거로움)
- seed.json 덮어쓰기 (백업 없을 경우)
- node_modules 재설치 (시간 비용)
- MCP DB 스키마 migration (체크포인트 복구 가능)

## 🔴 Irreversible Actions (사용자 명시적 승인 필수)

**반드시 AskUserQuestion으로 확인 받고 진행.** 승인 없이 절대 실행 금지.

| 행동 | 왜 irreversible |
|------|----------------|
| `samvil-deploy` (Vercel/Railway/Coolify) | 공개 URL, DNS 반영 |
| `git push` | 원격 히스토리에 기록 |
| `git push --force` | 원격 히스토리 덮어쓰기 (**매우 위험**) |
| GitHub Issue 생성 | 알림 발송, 관심자 노출 |
| Slack 메시지 전송 | 즉시 다른 사람 노출 |
| DB migration (production) | 데이터 변경 가능 |
| API key rotation | 이전 키 즉시 무효화 |
| `rm -rf` / `git clean -fdx` | 파일 복구 불가 |
| 도메인/DNS 변경 | 외부 트래픽 영향 |
| 결제 관련 API 호출 | 실제 돈 이동 |

### 사용자 승인 표준 형식

```
⚠️ [SAMVIL] Irreversible action 예정:
   - 액션: <설명>
   - 영향: <범위>
   - 되돌리기: <불가 or 복잡한 절차>

계속할까요?
  [A] 진행
  [B] 취소
  [C] 시뮬레이션만 (dry-run)
```

### Auto-approve 패턴 (신중히)

- `samvil-build`가 파일 수정하는 건 기본 auto (범위: 프로젝트 내부, reversible)
- Deploy/push 등은 **절대 auto-approve 금지**

---

## 📋 스킬별 Irreversibility 체크리스트

### samvil-deploy
- `vercel --prod` / `railway up` → 사용자 승인 필수
- Dry-run 옵션 제공 (preview deploy)
- URL 반환 후 확인 질문: "접속 확인하셨나요?"

### samvil-scaffold
- `create-next-app` → 파일 시스템 변경 (reversible via rm)
- 기존 디렉토리 덮어쓰기 → 확인 필수

### samvil-build
- 파일 생성/수정 → reversible
- `npm install` → reversible (node_modules 삭제)
- package.json 수정 → reversible

### samvil-evolve
- seed.json 덮어쓰기 → seed-version 백업 (reversible)
- wonder/reflect 결과 기록 → reversible

### samvil-update
- plugin cache 삭제 → irreversible 하지만 재다운로드 가능
- 사용자 확인 후 진행 (현재 구현됨)

---

## 🧪 Testing Irreversibility

- 각 irreversible action마다 `--dry-run` 플래그 지원 고려
- 배포 전 `gh run list`로 이전 배포 상태 확인 (이미 learnings에 있음)
- 중요 파일 수정 전 `git diff` 먼저 제시

---

## 📎 관련

- Manifesto v3 P10 (Reversibility Awareness)
- 동호님 개인 CLAUDE.md "Executing actions with care" 섹션 (상속)
- learnings/patterns.md "배포 전 gh run list 확인" (인용)
