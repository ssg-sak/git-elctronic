/**
 * 추천 점수 가중치 — 루트 AGENTS.md "핵심 도메인 규칙"에 고정된 값.
 * 팀 합의 없이 변경 금지.
 */
export const SCORE_WEIGHTS = {
  /** 충전 가능성 */
  availability: 0.4,
  /** 상태 정보 신뢰도 */
  reliability: 0.2,
  /** 이동시간 */
  travelTime: 0.15,
  /** 충전기 수 및 대기 위험 */
  waitRisk: 0.15,
  /** 주차·운영·주변 편의성 */
  convenience: 0.1,
} as const;

/** 상태 갱신 경과 시간(분) → 신뢰도 등급 */
export function reliabilityGrade(minutesSinceUpdate: number): "높음" | "보통" | "확인필요" {
  if (minutesSinceUpdate <= 5) return "높음";
  if (minutesSinceUpdate <= 15) return "보통";
  return "확인필요";
}

// TODO(backend): 항목별 점수 계산 함수 구현 (충전 가능성, 이동시간, 대기 위험, 편의성)
// TODO(backend): 실패 위험도(낮음/보통/높음) 산출 함수 구현
