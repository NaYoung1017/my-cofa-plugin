# my-cofa-plugin

Cofa 기반 AI 활용 실무 과제(제한 시간, Codex)용 개인 작업 키트.
**정답 코드·예상 문제·도메인 지식은 없다.** 어떤 과제가 나와도 같은 절차로 일하기 위한 규칙·스킬·기록 양식·점검 도구만 담았다.

## 설계 원칙

Cofa는 결과물뿐 아니라 프롬프트·AI 대화·검증 기록을 보고, 제출 뒤 설명이 실제 구현과 맞는지 대조한다(기술·의도·인지). 그래서 이 키트는:

1. **결정은 사용자가 한다.** AI는 선택지와 추천을 내고 멈춘다.
2. **구현 전에 확인한다.** 할 일 / 파일 / 원리(예시 값으로 따라가기) / 확인 방법을 보고 OK를 받은 뒤에만 코드를 쓴다.
3. **담당자 질문 → 요구 → 결정 → 코드 → 검증**을 ID로 잇는다 (Q → R → D → 코드 → V).
4. **돌린 것만 말한다.** 실행하지 않은 검증은 NOT_RUN, 검사 0건은 통과가 아니다.
5. **결정마다 선택·대안·이유·적용 조건·한계를 남긴다.** 제출 뒤 설명의 재료다.
6. **문제는 숨기지 않는다.** 데이터 이슈·모르는 것은 개수와 상관없이 전부 영향도 순으로 보여주고, 영향도 높음은 사용자가 처리를 정한다.
7. **원본은 고치지 않는다.** 과제 데이터·README·형식 파일은 읽기만 하고 산출물은 새 파일로 만든다.
8. **작업이 끝날 때마다 다음 단계를 추천한다.** 실행 여부는 사용자가 정한다.

## 설치 (과제 작업 폴더에서)

```bash
git clone --depth 1 https://github.com/NaYoung1017/my-cofa-plugin /tmp/kit && bash /tmp/kit/install.sh
```

`git clone`이 막히면:

```bash
mkdir -p /tmp/kit && curl -fsSL https://codeload.github.com/NaYoung1017/my-cofa-plugin/tar.gz/refs/heads/main | tar xz -C /tmp/kit --strip-components=1 && bash /tmp/kit/install.sh
```

설치 스크립트는 복사만 한다: `.agents/skills/cofa-*`, `.codex/agents/cofa-*.toml`, `cofa-notes/` 양식(없는 것만), `.cofa/tools/`.
- **과제 원본은 수정하지 않는다.** 복사 전에 원본 파일 지문(`.cofa/originals.sha256`)을 찍어 두고, `check.py`가 원본 변경을 잡는다.
- 과제에 `AGENTS.md`가 없으면 키트 규칙으로 만든다. 있으면 원본은 그대로 두고, 원본 내용 + 키트 규칙으로 `AGENTS.override.md`를 만든다(Codex가 우선 읽는 파일). 과제가 준 `AGENTS.override.md`가 이미 있으면 아무것도 바꾸지 않고, 첫 요청에 `.cofa/RULES.md`를 읽게 하라고 안내한다.
- `~/.codex`, Codex 설정, 네트워크, git 커밋은 건드리지 않는다.

설치 뒤 Codex를 다시 열고 `/skills`에서 `cofa-*`가 보이는지 확인한다.
안 보이면 `.agents/skills/cofa-start/SKILL.md 읽고 그대로 따라 해`처럼 파일을 직접 읽게 한다.
키트를 못 쓰면 첫 요청: `코드 쓰기 전에 README를 사실/가정/모르는 것으로 나누고, 담당자에게 물을 질문 3개를 뽑아줘. 결정은 내가 할 테니 선택지만 주고 멈춰.`

## 흐름

```
cofa-start → cofa-interview ⇄ cofa-align → cofa-plan → [cofa-build 반복 (+cofa-delegate)] → cofa-verify → cofa-explain
                              └──────────── cofa-decide (결정이 생길 때마다) ────────────┘
```

| 스킬 | 언제 | 사용자가 하는 일 | 남는 기록 |
|---|---|---|---|
| `$cofa-start` | 시작 직후 | 문제 정의 한 문장 직접 쓰기 | `BRIEF.md` v0 |
| `$cofa-interview` | 질문 만들 때 / 답 받았을 때 | 질문 골라서 직접 보내기, 답 붙여넣기 | `INTERVIEW.md` |
| `$cofa-align` | 인터뷰 후, 새 답, 중간 점검 | 방향 승인 / 범위 조정 선택 | `BRIEF.md` v1… |
| `$cofa-plan` | 코드 쓰기 전 | 방식 A/B/C 중 고르기, 계획 승인 | `PLAN.md` |
| `$cofa-build` | 작업 하나마다 | 브리핑 보고 OK | 커밋, `EXPLAIN.md` 동작 지도 |
| `$cofa-delegate` | 큰 작업을 나눌 때 | 서브에이전트 생성 승인 | `SUBAGENTS.md` |
| `$cofa-verify` | 제출 전 | 화면 직접 확인 | `VERIFY.md` |
| `$cofa-decide` | 결정마다 (다른 스킬이 호출) | 기록 확인 | `DECISIONS.md` |
| `$cofa-explain` | 제출 직전 | 막힌 부분 내 말로 다시 쓰기 | `EXPLAIN.md`, 제출 문서 보정 |

## 180분 운영표 (기준)

| 시간 | 단계 |
|---|---|
| 0–10 | 설치, `$cofa-start` |
| 10–40 | `$cofa-interview` ⇄ `$cofa-align` (35분쯤 v1 승인) |
| 40–55 | `$cofa-plan` — 방식 선택, 계획 승인 |
| 55–150 | `$cofa-build` 반복. 중간쯤 `$cofa-align` 중간 점검 |
| 150–165 | `$cofa-verify` — 이후 기능 추가 금지 |
| 165–180 | `$cofa-explain`, 제출 문서 정리, 제출 |

## 서브에이전트

메인 세션이 총괄이다. 서브에이전트는 두 역할만 있고, `$cofa-delegate` 점검을 통과하고 사용자가 OK할 때만 만든다.

| 역할 | 하는 일 |
|---|---|
| `cofa-data` | 데이터 요약·불일치 찾기 (읽기 전용, 처리 방법은 선택지로만) |
| `cofa-builder` | 승인된 작업 카드 하나를 카드의 파일 안에서 구현 |

상한: 동시 2개(역할별 1개), 세션 6회. 서브에이전트는 다른 에이전트를 만들지 않고 결정하지 않는다. 결과는 메인이 다시 실행해 확인한다.

## 도구 (`.cofa/tools/`, Python 표준 라이브러리)

- `profile.py <파일들>` — 인코딩·구분자·행/열·빈 값·형식 섞임·범위·이상값·키 후보·파일 간 키 겹침. 개인정보로 보이는 열은 값을 가린다. 읽은 행 0건이면 exit 2.
- `check.py` — 원본 파일 변경, 문제 정의, 처리 안 된 모르는 것·데이터 이슈(영향도 높음이면 실패), 계획 승인, 요구 상태, 검증 기록, 제출물 존재·형식, 결정 기록, 비밀키, 커밋된 민감 파일 점검. 문제 항목은 전부 출력한다. exit 0 정상 / 1 실패 있음 / 2 검사한 항목 0개.

## 하지 않는 것

- 과제를 대신 풀거나 방식을 대신 고르기
- 예상 질문·모범 답안 만들기 (제출 뒤 서술형에서는 키트를 쓰지 않는다)
- Codex 설정 변경, 권한 우회 옵션, git push, 외부 전송

## 라이선스

Cofa·KRAFTON·SK hynix 개인 준비용
