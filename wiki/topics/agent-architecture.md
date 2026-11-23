---
title: "에이전트 설계 (Agent architecture)"
posts: [building-effective-agents, multi-agent-research-system, managed-agents]
updated: 2026-11-12
---

# 에이전트 설계

Anthropic이 에이전트를 어떻게 만들라고 말해왔는지, 그 생각이 어떻게 바뀌어 왔는지 정리한 페이지.

## 흐름 한눈에

```
 2024-12  Building effective agents
          "단순한 패턴부터. 복잡도는 증명될 때만."
          → 6가지 패턴 정리 (chaining · routing · parallel · orchestrator-workers · evaluator · agent)
              │
              ▼ orchestrator-workers를 실제 제품에
 2025-06  Multi-agent research system
          "성능 = 토큰을 충분히 쓰게 하는 것. 대신 15배 비싸다."
          → 리드 + 병렬 서브에이전트, 외부 메모리, 새 서브에이전트로 인계
              │
              ▼ 하네스 자체가 낡는다는 깨달음
 2026-04  Managed Agents
          "구현 말고 인터페이스를 설계하라."
          → session · harness · sandbox 분리, 뇌와 손 분리
              │
              ▼ 제품 기능으로
 2026-09  Claude Code Projects (claude.com 발표, 아직 위키에 없음)
          → coordinator + threads, 프로젝트 메모리
```

## 변하지 않은 원칙

| 원칙 | 2024 | 2025 | 2026 |
|---|---|---|---|
| **단순하게 시작** | "가장 단순한 해법부터" | 질문 20개로 바로 평가 시작 | 하네스의 가정을 계속 의심하라 |
| **도구(ACI)가 핵심** | 프롬프트보다 도구 최적화에 더 많은 시간 | 도구 설명이 나쁘면 완전히 엉뚱한 길로 감 | 모든 손을 `execute()` 하나로 통일 |
| **환경에서 ground truth** | 매 단계 도구 결과로 진행 판단 | interleaved thinking으로 결과 평가 | 실패도 도구 오류로 Claude에게 전달 |

## 바뀐 생각

| 주제 | 이전 | 이후 |
|---|---|---|
| **복잡도** | 멀티 에이전트는 꼭 필요할 때만 (2024) | 가치가 높은 병렬 작업에는 멀티 에이전트가 압도적이다 (2025, 90.2% 향상) |
| **긴 작업의 컨텍스트** | 요약하고 외부 메모리에 저장한 뒤 새 서브에이전트로 넘김 (2025) | 버리지 말고 세션 로그에 다 남긴 뒤 필요한 구간만 다시 읽음 (2026) |
| **하네스** | 모델의 약점을 보완하는 장치 | 모델이 좋아지면 짐이 된다. 바꿀 수 있게 분리해야 한다 (context anxiety 사례) |
| **보안** | 샌드박스에서 테스트, 가드레일 | 토큰이 샌드박스에서 아예 닿지 않는 구조 |

## 패턴 고르기 (요약)

```
 단일 LLM 호출 + 검색 + 예시로 충분한가? ── 예 ──▶ 그걸로 끝
   │ 아니오
   ▼
 하위 작업을 미리 정할 수 있나?
   ├─ 예, 순서대로 ────────▶ Prompt chaining
   ├─ 예, 종류별로 ────────▶ Routing
   ├─ 예, 동시에 ──────────▶ Parallelization
   └─ 아니오 ──▶ 작업이 나뉘나? ── 예 ──▶ Orchestrator-workers (멀티 에이전트)
                      │ 아니오
                      ▼
                 열린 문제 ──▶ Agent (루프 + 도구 + 종료 조건)

 + 평가 기준이 명확하면 어디든 Evaluator-optimizer 루프를 덧붙일 수 있음
```

## 관련 글

- [Building effective agents](../posts/building-effective-agents.md) (2024-12-19)
- [How we built our multi-agent research system](../posts/multi-agent-research-system.md) (2025-06-13)
- [Scaling Managed Agents](../posts/managed-agents.md) (2026-04-08)
- 아직 위키에 없음: Effective context engineering (2025-09), Effective harnesses for long-running agents (2025-11), Harness design for long-running apps (2026-03)
