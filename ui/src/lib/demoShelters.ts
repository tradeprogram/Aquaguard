// 산청 상능마을 데모 대피소 3곳 — HANDOFF.md §6.2. EvacuationPanel(경로 계산)·
// IsolationPanel(고립 분석)·MapExplorer(슬라이더 연동 고립 재계산)가 모두 같은
// 대피소 목록을 기준으로 계산해야 앞뒤가 맞으므로 한 곳에서 관리한다.
export interface DemoShelter {
  id: string;
  name: string;
  lon: number;
  lat: number;
  capacity: number;
}

export const DEMO_SHELTERS: DemoShelter[] = [
  { id: "S001", name: "산청 상능마을회관", lon: 128.057, lat: 35.349, capacity: 200 },
  { id: "S002", name: "생비량초등학교", lon: 128.052, lat: 35.353, capacity: 300 },
  { id: "S003", name: "산청군청 대피소", lon: 127.900325, lat: 35.40737, capacity: 500 },
];

// 고립 분석(§7)에 쓰는 조회 범위 — 데모 대피소들 주변 산청 상능마을 일대.
export const DEMO_ISOLATION_BBOX: [number, number, number, number] = [128.045, 35.343, 128.065, 35.358];
