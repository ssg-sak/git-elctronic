/** 충전 실패 위험도 등급 */
export type FailureRisk = "낮음" | "보통" | "높음";

/** 상태 정보 신뢰도 등급 (statUpdatedAt 경과 시간 기준) */
export type ReliabilityGrade = "높음" | "보통" | "확인필요";

/** 충전기 상태 코드 (한국환경공단 stat 필드) */
export enum ChargerStat {
  CommunicationError = 1,
  Available = 2, // 충전대기
  Charging = 3,
  Suspended = 4, // 운영중지
  UnderInspection = 5, // 점검중
  Unknown = 9,
}

export interface Charger {
  chgerId: string;
  chgerType: string;
  output: string;
  stat: ChargerStat;
  /** API가 제공한 충전기 상태 시각 (statUpdDt) */
  statUpdatedAt: string;
  /** 우리 서버가 API를 조회한 시각 */
  fetchedAt: string;
}

export interface Station {
  statId: string;
  statNm: string;
  addr: string;
  lat: number;
  lng: number;
  useTime: string;
  busiNm: string;
  parkingFree: boolean;
  chargers: Charger[];
  totalCount: number;
  availableCount: number;
  chargingCount: number;
  brokenCount: number;
}

/** 추천 결과 항목 (백엔드 → 프론트엔드) */
export interface StationRecommendation {
  station: Station;
  score: number;
  failureRisk: FailureRisk;
  reliability: ReliabilityGrade;
  /** 실시간 교통 반영 예상 이동시간 (초) */
  travelTimeSec: number;
  distanceMeters: number;
  estimatedArrival: string;
  /** 사람이 읽을 수 있는 추천 이유 */
  reason: string;
}
