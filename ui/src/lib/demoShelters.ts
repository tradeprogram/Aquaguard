// 데모 지역별 대피소 목록 — HANDOFF.md §6.2. EvacuationPanel(경로 계산)·
// IsolationPanel(고립 분석)·MapExplorer(슬라이더 연동 고립 재계산, 지역 이동 버튼)가
// 모두 같은 목록을 기준으로 계산해야 앞뒤가 맞으므로 한 곳에서 관리한다.
export interface DemoShelter {
  id: string;
  name: string;
  lon: number;
  lat: number;
  capacity: number;
}

export type RegionKey = "sancheong" | "gangnam" | "seocho";

export interface DemoRegion {
  label: string;
  shelters: DemoShelter[];
  // 고립 분석(§7)에 쓰는 조회 범위 — 대피소들 주변 일대.
  isolationBbox: [number, number, number, number];
}

export const DEFAULT_REGION: RegionKey = "sancheong";

export const DEMO_REGIONS: Record<RegionKey, DemoRegion> = {
  sancheong: {
    label: "산청 상능마을",
    shelters: [
      { id: "S001", name: "산청 상능마을회관", lon: 128.057, lat: 35.349, capacity: 200 },
      { id: "S002", name: "생비량초등학교", lon: 128.052, lat: 35.353, capacity: 300 },
      { id: "S003", name: "산청군청 대피소", lon: 127.900325, lat: 35.40737, capacity: 500 },
    ],
    isolationBbox: [128.045, 35.343, 128.065, 35.358],
  },
  // 2026-09-07 — 서울시 지진안전포털(news.seoul.go.kr, 강남구 필터)에서 실제 지정
  // 옥외대피소 중 3곳을 확인 후 VWorld 지오코딩으로 좌표 변환. safetydata.go.kr
  // 전국 API(DSSP-IF-00103)는 강남구를 아직 커버 안 해서(2026-09-03 확인) 이쪽으로 대체.
  gangnam: {
    label: "서울 강남",
    shelters: [
      { id: "G01", name: "중대부속고등학교 운동장", lon: 127.05169, lat: 37.49184, capacity: 200 },
      { id: "G02", name: "수서초등학교 운동장", lon: 127.10166, lat: 37.49082, capacity: 200 },
      { id: "G03", name: "중동고등학교 운동장", lon: 127.08078, lat: 37.49305, capacity: 200 },
    ],
    isolationBbox: [127.03, 37.48, 127.11, 37.5],
  },
  // 2026-09-09 — 같은 방식(서울시 지진안전포털, 서초구 필터)으로 확인. 2026-09-07
  // 팀 커밋(a778b95c)이 "서울 AOI = 강남구+서초구"로 공식 확정한 것과 일치하는 지역.
  seocho: {
    label: "서울 서초",
    shelters: [
      { id: "C01", name: "서초초등학교 운동장", lon: 127.02403, lat: 37.49969, capacity: 200 },
      { id: "C02", name: "반포초등학교 운동장", lon: 126.99062, lat: 37.50273, capacity: 200 },
      { id: "C03", name: "이수초등학교 운동장", lon: 126.98406, lat: 37.47819, capacity: 200 },
    ],
    isolationBbox: [126.978, 37.472, 127.03, 37.509],
  },
};

// 하위호환용 — 기존에 DEFAULT_REGION(산청) 목록을 직접 참조하던 코드가 있으면 이걸 쓴다.
export const DEMO_SHELTERS = DEMO_REGIONS[DEFAULT_REGION].shelters;
export const DEMO_ISOLATION_BBOX = DEMO_REGIONS[DEFAULT_REGION].isolationBbox;
