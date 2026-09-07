import type { Provenance } from "@/components/ProvenanceBadge";

// §6.1 배지를 explain() 결과에 연결한다(트랙② 요청 7).
//
// 쟁점은 트랙②가 정확히 짚었다 — "노출 건물 1,723건"과 "피해액 41.4억"은 성격이
// 다르다. 전자는 실측 건물 footprint에 위험 폴리곤을 교차시킨 공간연산 결과지만,
// 후자는 그 위에 필지 단위 주용도 조인(동 단위 아님)과 1동=1세대 가정을 얹은 값이다.
// 그런데 배지는 하나뿐이라 무엇을 고르든 한쪽이 왜곡된다:
//
//   전부 MODEL로 표기 → 피해액에 얽힌 가정이 화면에서 사라진다. 심사에서 가장
//                        공격받기 쉬운 지점을 우리가 숨긴 꼴이 된다.
//   가정이 하나라도 있으면 ASSUMPTION → 거의 모든 값이 ASSUMPTION이 되어 배지가
//                        정보를 잃는다. 실측 건물 수까지 가정값으로 읽힌다.
//
// 그래서 배지를 하나가 아니라 두 채널로 나눈다:
//   ① 출처 배지  — 이 값이 어떻게 산출됐는가 (MODEL / RULE / OBSERVED ...)
//   ② 가정 표시  — 그 산출에 몇 개의 가정이 얹혀 있는가, 무엇인지
//
// 이러면 "MODEL · 가정 2건"처럼 읽혀서, 계산 성격과 불확실성을 각각 정직하게
// 말할 수 있다. 가정 목록은 explain()이 이미 들고 있는 문구를 그대로 쓴다 —
// UI가 새로 문장을 지어내면 모듈이 실제로 한 가정과 어긋날 수 있다.

export interface ProvenanceInfo {
  kind: Provenance;
  assumptions: string[];
}

/** Module O 봉투 meta.explains의 모양(계약 밖 부가 정보라 전부 optional). */
export interface ModuleExplains {
  d?: {
    buffer_is_assumption?: boolean;
    use_type_join?: { is_assumption?: boolean; assumption?: string; mapping_available?: boolean };
    is_model?: boolean;
  };
  g?: {
    detail?: {
      housing?: { assumption?: string };
      buildings?: { unknown_excluded?: number; excluded_total?: number };
    };
  };
}

/** 노출자산(Module D) — 공간연산 결과. 점 버퍼·주용도 조인이 가정으로 얹힌다. */
export function exposureProvenance(explains?: ModuleExplains): ProvenanceInfo {
  const d = explains?.d;
  const assumptions: string[] = [];
  if (d?.buffer_is_assumption) {
    assumptions.push("위험 폴리곤이 없어 점 좌표를 반경 버퍼로 대체");
  }
  if (d?.use_type_join?.is_assumption && d.use_type_join.assumption) {
    assumptions.push(d.use_type_join.assumption);
  }
  if (d?.use_type_join && d.use_type_join.mapping_available === false) {
    assumptions.push("건축물대장 주용도 매핑을 못 읽어 용도가 전부 '미상'");
  }
  return { kind: "MODEL", assumptions };
}

/** 피해액(Module G) — D의 가정을 그대로 물려받고 세대수·제외 규칙이 더 얹힌다. */
export function damageCostProvenance(explains?: ModuleExplains): ProvenanceInfo {
  const assumptions = [...exposureProvenance(explains).assumptions];
  const detail = explains?.g?.detail;
  if (detail?.housing?.assumption) {
    assumptions.push(detail.housing.assumption);
  }
  const excluded = detail?.buildings?.excluded_total;
  if (typeof excluded === "number" && excluded > 0) {
    assumptions.push(`공식 침수 단가가 없는 비주거·용도 미상 ${excluded.toLocaleString()}동을 산정에서 제외`);
  }
  return { kind: "MODEL", assumptions };
}
