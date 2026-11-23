---
title: "Scaling Managed Agents: Decoupling the brain from the hands"
url: https://www.anthropic.com/research/managed-agents
published: 2026-04-08
source: local/research/managed-agents.md
topics: [agent-architecture, context-management, security]
concepts: [harness, session-log, sandbox, brain-hands-decoupling, pets-vs-cattle, context-anxiety]
---

# Scaling Managed Agents: Decoupling the brain from the hands (2026-04-08)

> **한 줄 요약:** 하네스는 "Claude가 못 하는 것"에 대한 가정을 담고 있고, 그 가정은 모델이 좋아지면 낡는다. 그래서 Managed Agents는 특정 구현이 아니라 **오래 버틸 인터페이스**(session, harness, sandbox)를 설계했다.

## 핵심 주장

1. **하네스의 가정은 낡는다.** Sonnet 4.5는 컨텍스트 한계가 다가오면 작업을 서둘러 끝내는 "context anxiety"를 보여서, 하네스에 컨텍스트 리셋을 넣었다. 그런데 Opus 4.5에서는 그 행동이 사라져 리셋이 **쓸모없는 짐**이 됐다.
2. **운영체제처럼 추상화한다.** OS가 하드웨어를 process와 file로 추상화해 수십 년을 버틴 것처럼, 에이전트 구성요소를 세 가지 인터페이스로 가상화했다.

| 구성요소 | 역할 |
|---|---|
| **Session** | 일어난 모든 일의 추가 전용(append-only) 로그 |
| **Harness** | Claude를 호출하고 도구 호출을 인프라로 보내는 루프 ("뇌") |
| **Sandbox** | 코드를 실행하고 파일을 고치는 환경 ("손") |

3. **인터페이스 모양에는 의견이 있지만, 그 뒤에서 무엇이 돌든 상관하지 않는다.** Managed Agents는 "메타 하네스"다. Claude Code 같은 범용 하네스도, 특정 작업 전용 하네스도 올릴 수 있다.

## 설계 변화: 하나의 컨테이너 → 분리

```
 이전: 한 컨테이너 안에 전부           이후: 뇌 · 손 · 기록 분리
 ┌───────────────────────┐            Harness (뇌) ──execute()──▶ Sandbox (손)
 │ session + harness     │                │                      컨테이너 · MCP · 폰 · ...
 │ + sandbox + 자격증명   │                └─emitEvent()/getEvents()─▶ Session log (기록)
 └───────────────────────┘
 컨테이너 = 애완동물 🐶                  모두 가축 🐄 (죽으면 새로 띄움)
```

- **Pets vs cattle 문제:** 모든 것이 한 컨테이너에 있으면 컨테이너가 죽을 때 세션도 사라진다. 디버깅하려면 사용자 데이터가 든 컨테이너에 들어가야 했다.
- **손이 죽으면:** 하네스가 도구 호출 오류로 받아서 Claude에게 넘긴다. 다시 할지는 Claude가 정하고, 새 컨테이너는 `provision()`으로 띄운다.
- **뇌가 죽으면:** 세션 로그가 바깥에 있으니 `wake(sessionId)`, `getSession(id)`로 마지막 이벤트부터 재개한다.

## 보안 경계

- 한 컨테이너 설계에서는 프롬프트 인젝션이 Claude를 설득해 **같은 환경의 토큰을 읽게** 하기만 하면 됐다.
- 해결 방법은 **Claude가 만든 코드가 도는 샌드박스에서 토큰에 아예 닿지 않게 하는 것**이다.
  - Git: 샌드박스를 초기화할 때 토큰으로 clone하고 remote에 연결한다. 에이전트는 토큰을 직접 다루지 않는다.
  - MCP: OAuth 토큰은 vault에 두고, 전용 프록시가 세션 토큰으로 자격증명을 가져와 호출한다. 하네스도 자격증명을 모른다.
- "권한을 좁힌 토큰이면 안전하다"는 것도 Claude의 능력에 대한 가정이고, Claude는 점점 똑똑해진다.

## 세션 ≠ 컨텍스트 창

- compaction, 메모리 도구, 컨텍스트 다듬기(trimming)는 모두 **무엇을 버릴지 되돌릴 수 없게 결정**한다. 미래에 어떤 토큰이 필요할지는 알기 어렵다.
- Managed Agents에서는 **세션 로그가 컨텍스트 창 밖의 컨텍스트 객체** 역할을 한다. `getEvents()`로 필요한 구간을 다시 읽거나 되감아 볼 수 있다.
- 역할을 나눴다.
  - 세션: 복구 가능한 저장만 보장한다.
  - 하네스: 컨텍스트를 어떻게 구성할지(캐시 효율, context engineering)를 맡는다. 미래 모델에 무엇이 필요할지 모르니 이 부분은 바꿀 수 있게 둔다.

## 성과: 많은 뇌, 많은 손

- **많은 뇌:** 컨테이너는 필요할 때만 띄운다. 그래서 첫 토큰까지 걸리는 시간(TTFT)이 **p50 약 60%, p95 90% 이상 감소**했다. 고객 VPC에 연결할 때 네트워크를 피어링할 필요도 없어졌다.
- **많은 손:** 모든 손이 `execute(name, input) → string` 하나로 통일된다. 컨테이너, MCP 서버, 폰, 심지어 게임 에뮬레이터도 같은 방식으로 다룬다. 뇌끼리 손을 넘겨줄 수도 있다.

## 연결

- 출발점: [Building effective agents](building-effective-agents.md). 에이전트 = 루프 안에서 도구를 쓰는 LLM.
- 같은 문제를 다르게 푼 예: [멀티 에이전트 리서치 시스템](multi-agent-research-system.md). 긴 작업을 외부 메모리와 새 서브에이전트로 풀었다.
- 원문이 언급하는 관련 글 (아직 위키에 없음):
  - [Effective context engineering for AI agents](https://www.anthropic.com/research/effective-context-engineering-for-ai-agents)
  - [Effective harnesses for long-running agents](https://www.anthropic.com/research/effective-harnesses-for-long-running-agents)
  - [Harness design for long-running application development](https://www.anthropic.com/research/harness-design-long-running-apps)

## 원문

- [Scaling Managed Agents: Decoupling the brain from the hands](https://www.anthropic.com/research/managed-agents) · Lance Martin, Gabe Cemaj, Michael Cohen
- [Managed Agents 문서](https://platform.claude.com/docs/en/managed-agents/overview)
