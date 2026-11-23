---
title: "Building effective agents"
url: https://www.anthropic.com/research/building-effective-agents
published: 2024-12-19
source: local/research/building-effective-agents.md
topics: [agent-architecture, tools]
concepts: [augmented-llm, workflow-vs-agent, prompt-chaining, routing, parallelization, orchestrator-workers, evaluator-optimizer, aci]
---

# Building effective agents (2024-12-19)

> **한 줄 요약:** 성공한 에이전트는 복잡한 프레임워크가 아니라 단순하고 조합 가능한 패턴으로 만들어졌다. 가장 단순한 해법에서 시작하고, 효과가 증명될 때만 복잡도를 올려라.

⚠️ 원문 상단에 "도구 환경이 2024년 12월 이후 많이 바뀌었다"는 안내가 붙어 있다. 현재 방식은 [Managed Agents](managed-agents.md)를 볼 것.

## 핵심 주장

1. **Workflow와 Agent를 구분한다.** 둘 다 "agentic system"이지만 구조가 다르다.
   - **Workflow:** LLM과 도구가 미리 정해진 코드 경로를 따라 움직인다.
   - **Agent:** LLM이 스스로 진행 과정과 도구 사용을 결정한다.
2. **가장 단순한 것부터 시작한다.** 에이전트는 지연 시간과 비용을 내주고 성능을 얻는 거래다. 많은 경우 단일 LLM 호출에 검색(retrieval)과 예시를 붙이는 것만으로 충분하다.
3. **프레임워크는 조심해서 쓴다.** 추상화 층이 프롬프트와 응답을 가려 디버깅이 어려워진다. LLM API를 직접 쓰는 것부터 권한다. 쓰더라도 내부 동작은 이해하고 써야 한다.
4. **에이전트 3원칙**
   - 설계를 **단순하게** 유지한다.
   - 계획 단계를 드러내 **투명하게** 만든다.
   - 도구 **문서화와 테스트**로 ACI(agent-computer interface)를 잘 만든다.

## 패턴 6가지 (단순 → 복잡)

| 패턴 | 구조 | 언제 쓰나 | 예시 |
|---|---|---|---|
| **Augmented LLM** (기본 블록) | LLM + 검색 · 도구 · 메모리 | 모든 패턴의 바탕 | MCP로 도구 연결 |
| **Prompt chaining** | 단계별 순차 호출, 중간에 검사(gate) | 고정된 하위 작업으로 깔끔히 나뉠 때 | 개요 작성 → 기준 검사 → 본문 작성 |
| **Routing** | 입력을 분류해 전문 처리로 보냄 | 범주가 뚜렷하고 분류가 정확할 때 | 쉬운 질문은 작은 모델, 어려운 질문은 큰 모델 |
| **Parallelization** | 동시 실행 후 합침 (sectioning / voting) | 속도가 필요하거나 여러 관점이 필요할 때 | 가드레일 분리, 여러 프롬프트로 취약점 검토 |
| **Orchestrator-workers** | 중앙 LLM이 작업을 동적으로 나눠 맡기고 합침 | 하위 작업을 미리 예측할 수 없을 때 | 여러 파일을 고치는 코딩, 다중 출처 검색 |
| **Evaluator-optimizer** | 생성 ↔ 평가 피드백 루프 | 평가 기준이 명확하고 반복 개선이 효과 있을 때 | 문학 번역, 다회 검색 |
| **Agent** | 환경 피드백을 받으며 도구를 반복 사용 | 단계 수를 예측할 수 없는 열린 문제 | SWE-bench 코딩, computer use |

- **Parallelization과 Orchestrator-workers의 차이:** 모양은 비슷하다. 핵심 차이는 하위 작업을 미리 정하느냐(병렬화), 입력을 보고 orchestrator가 그때그때 정하느냐다.
- **Agent의 조건:** 매 단계 환경에서 "ground truth"(도구 결과, 코드 실행 결과)를 받아 진행을 판단해야 한다. 최대 반복 횟수 같은 종료 조건을 둔다. 자율성이 높은 만큼 비용과 오류 누적 위험이 있으니 샌드박스 테스트와 가드레일이 필요하다.

## 실전 팁

- **도구 정의에도 프롬프트만큼 공을 들인다.** HCI에 들이는 노력만큼 ACI에도 투자하라.
- **모델이 쓰기 쉬운 형식을 고른다.** 생각할 토큰을 충분히 주고, 인터넷 텍스트에 흔한 형식에 가깝게 만든다. 줄 수 세기나 JSON 안 코드 이스케이프 같은 "형식 부담"을 없앤다.
- **Poka-yoke:** 실수하기 어렵게 인자를 바꾼다. SWE-bench 에이전트를 만들 때 상대 경로 실수가 생기자 **절대 경로만 받도록 바꿨고, 이후 실수가 사라졌다.** 이 작업에서 전체 프롬프트보다 도구 최적화에 더 많은 시간을 썼다.
- **에이전트가 특히 잘 맞는 분야:** 고객 지원과 코딩. 대화와 행동이 함께 필요하고, 성공 기준이 명확하고, 피드백 루프가 있고, 사람의 감독이 들어가는 일이다.

## 이후 흐름

- 2025-06 [멀티 에이전트 리서치 시스템](multi-agent-research-system.md): orchestrator-workers 패턴을 실제 제품(Research)에 적용했다.
- 2026-04 [Managed Agents](managed-agents.md): 하네스 자체가 모델 발전에 따라 낡는다는 전제로 인터페이스 중심 설계로 이동했다.
- 2026-09 Claude Code Projects: coordinator + threads 구조가 같은 패턴을 제품 기능으로 만든 것이다.

## 원문

- [Building effective agents](https://www.anthropic.com/research/building-effective-agents) · Erik S., Barry Zhang
