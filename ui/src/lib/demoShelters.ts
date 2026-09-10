// 데모 지역별 대피소 목록 — HANDOFF.md §6.2. EvacuationPanel(경로 계산)·
// IsolationPanel(고립 분석)·MapExplorer(슬라이더 연동 고립 재계산, 지역 이동 버튼)가
// 모두 같은 목록을 기준으로 계산해야 앞뒤가 맞으므로 한 곳에서 관리한다.
//
// 2026-09-10 — 전부 산림청 산사태정보시스템(sansatai.forest.go.kr)의 "취약지역
// 대피소" 공개 API로 교체했다: GET /mhms_pub/mhms/shelter/shelterList.do?
// searchAddress=<주소>, 키 불필요, 좌표(evctnPlaceXcrd/Ycrd, EPSG:4326)까지 응답에
// 포함돼 있어 별도 지오코딩도 필요 없다. 산사태 전용 지정 대피소라 이 프로젝트
// 주제(산사태→홍수→고립)에 안전Dream/지진옥외대피소보다 더 맞는 데이터다.
// 이전에 썼던 "산청 상능마을회관"은 이 목록에 아예 없었다 — 상능마을 자체가
// 산사태 취약지역 대피소로 지정된 적이 없다는 뜻이라 교체 이유가 됐다(2026-09-09).
// 이 API는 수용인원 필드를 안 줘서 capacity는 여전히 자리표시값이다.
//
// HANDOFF §6.2: "손으로 넣은 대피소 후보 2~3곳...으로 파이프라인을 먼저 완성"은
// 실데이터 없을 때의 임시 단계일 뿐, 실데이터가 있으면 개수를 제한할 이유가 없다
// (§6.4 GET /shelters?bbox=... 자체가 "그 범위 안 전부"를 전제한 설계). 그래서 각
// 지역에서 검색된 대피소 전부(산청 8·강남 15·서초 20)를 그대로 담았다.
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
  // 고립 분석(§7)에 쓰는 조회 범위 — 대피소들 전체를 포함하는 bbox + 여유.
  isolationBbox: [number, number, number, number];
}

export const DEFAULT_REGION: RegionKey = "sancheong";

export const DEMO_REGIONS: Record<RegionKey, DemoRegion> = {
  // searchAddress=산청군 생비량면 → 8곳 전부.
  sancheong: {
    label: "산청 상능마을",
    shelters: [
      { id: "S001", name: "가계마을회관2", lon: 128.08145, lat: 35.36157, capacity: 200 },
      { id: "S002", name: "대둔마을회관", lon: 128.03881, lat: 35.33721, capacity: 200 },
      { id: "S003", name: "도전마을회관", lon: 128.01701, lat: 35.33699, capacity: 200 },
      { id: "S004", name: "방화마을회관", lon: 128.08778, lat: 35.3402, capacity: 200 },
      { id: "S005", name: "장란마을회관", lon: 128.03497, lat: 35.34281, capacity: 200 },
      { id: "S006", name: "제보경로당", lon: 128.08052, lat: 35.3729, capacity: 200 },
      { id: "S007", name: "제보마을경로당", lon: 128.08051, lat: 35.37291, capacity: 200 },
      { id: "S008", name: "하능마을회관", lon: 128.06281, lat: 35.37387, capacity: 200 },
    ],
    isolationBbox: [128.007, 35.327, 128.0978, 35.3839],
  },
  // searchAddress=서울특별시 강남구 → 15곳 전부.
  gangnam: {
    label: "서울 강남",
    shelters: [
      { id: "G001", name: "개원중학교", lon: 127.0715, lat: 37.49146, capacity: 200 },
      { id: "G002", name: "구룡중학교", lon: 127.05627, lat: 37.48605, capacity: 200 },
      { id: "G003", name: "구룡초등학교", lon: 127.05205, lat: 37.48081, capacity: 200 },
      { id: "G004", name: "대진초등학교", lon: 127.07813, lat: 37.49663, capacity: 200 },
      { id: "G005", name: "도곡1문화센터", lon: 127.03897, lat: 37.48829, capacity: 200 },
      { id: "G006", name: "서울로봇고등학교", lon: 127.08428, lat: 37.48074, capacity: 200 },
      { id: "G007", name: "세곡문화센터", lon: 127.10703, lat: 37.46908, capacity: 200 },
      { id: "G008", name: "세명초등학교", lon: 127.09088, lat: 37.46859, capacity: 200 },
      { id: "G009", name: "수서중학교", lon: 127.10263, lat: 37.49091, capacity: 200 },
      { id: "G010", name: "양전초등학교", lon: 127.07016, lat: 37.49039, capacity: 200 },
      { id: "G011", name: "언주초등학교", lon: 127.03723, lat: 37.48651, capacity: 200 },
      { id: "G012", name: "영희초등학교", lon: 127.08113, lat: 37.49176, capacity: 200 },
      { id: "G013", name: "중동고등학교", lon: 127.08063, lat: 37.49311, capacity: 200 },
      { id: "G014", name: "중동중학교", lon: 127.07823, lat: 37.4889, capacity: 200 },
      { id: "G015", name: "포이초등학교", lon: 127.05254, lat: 37.47569, capacity: 200 },
    ],
    isolationBbox: [127.0272, 37.4586, 127.117, 37.5066],
  },
  // searchAddress=서울특별시 서초구 → 20곳 전부.
  seocho: {
    label: "서울 서초",
    shelters: [
      { id: "C001", name: "내곡동주민센터", lon: 127.05835, lat: 37.44936, capacity: 200 },
      { id: "C002", name: "내곡중학교", lon: 127.05445, lat: 37.45199, capacity: 200 },
      { id: "C003", name: "다니엘학교", lon: 127.09229, lat: 37.46014, capacity: 200 },
      { id: "C004", name: "동덕여자고등학교", lon: 126.99281, lat: 37.47618, capacity: 200 },
      { id: "C005", name: "방배2동주민센터", lon: 126.98555, lat: 37.47979, capacity: 200 },
      { id: "C006", name: "방배3동주민센터", lon: 127.00002, lat: 37.47843, capacity: 200 },
      { id: "C007", name: "방배중학교", lon: 126.9985, lat: 37.49422, capacity: 200 },
      { id: "C008", name: "새쟁이마을경로당", lon: 127.06988, lat: 37.43505, capacity: 200 },
      { id: "C009", name: "서울고등학교", lon: 127.00468, lat: 37.48339, capacity: 200 },
      { id: "C010", name: "서울방일초등학교", lon: 126.99846, lat: 37.48538, capacity: 200 },
      { id: "C011", name: "서울서일초등학교", lon: 127.02303, lat: 37.48488, capacity: 200 },
      { id: "C012", name: "서울신중초등학교", lon: 127.01027, lat: 37.47984, capacity: 200 },
      { id: "C013", name: "서울양재초등학교", lon: 127.03154, lat: 37.47337, capacity: 200 },
      { id: "C014", name: "서울언남초등학교", lon: 127.06166, lat: 37.45389, capacity: 200 },
      { id: "C015", name: "서울우면초등학교", lon: 127.02378, lat: 37.46474, capacity: 200 },
      { id: "C016", name: "서울웹툰애니메이션고(서울전자고)", lon: 126.98871, lat: 37.46987, capacity: 200 },
      { id: "C017", name: "서초구립느티나무쉼터", lon: 127.05079, lat: 37.46186, capacity: 200 },
      { id: "C018", name: "서초구청", lon: 127.03241, lat: 37.48382, capacity: 200 },
      { id: "C019", name: "서초종합체육관", lon: 127.04219, lat: 37.4589, capacity: 200 },
      { id: "C020", name: "송동마을경로당", lon: 127.0171, lat: 37.46016, capacity: 200 },
    ],
    isolationBbox: [126.9755, 37.425, 127.1023, 37.5042],
  },
};

// 하위호환용 — 기존에 DEFAULT_REGION(산청) 목록을 직접 참조하던 코드가 있으면 이걸 쓴다.
export const DEMO_SHELTERS = DEMO_REGIONS[DEFAULT_REGION].shelters;
export const DEMO_ISOLATION_BBOX = DEMO_REGIONS[DEFAULT_REGION].isolationBbox;
