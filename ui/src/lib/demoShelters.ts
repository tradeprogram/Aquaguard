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

export type RegionKey = "sancheong" | "sancheong_all" | "gangnam" | "seocho";

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
  // searchAddress=경상남도 산청군 → 104곳 전부. 고립분석을 군 전체로 돌리는 시나리오용
  // (2026-09-21 실측: 도로 1.4만·건물 11만, 캐시 후 계산 약 5초 — module_e_routing/README.md).
  // 경로 안내(EvacuationPanel)는 이 중 출발지에서 가까운 곳만 네이버로 조회한다.
  sancheong_all: {
    label: "산청군 전체",
    shelters: [
      { id: "K001", name: "가계마을회관2", lon: 128.08145, lat: 35.36157, capacity: 200 },
      { id: "K002", name: "가마실권역농촌체험마을", lon: 127.89146, lat: 35.50429, capacity: 200 },
      { id: "K003", name: "간공마을회관", lon: 128.04309, lat: 35.38704, capacity: 200 },
      { id: "K004", name: "갈티마을회관", lon: 127.92674, lat: 35.29361, capacity: 200 },
      { id: "K005", name: "거림마을회관", lon: 127.72265, lat: 35.28231, capacity: 200 },
      { id: "K006", name: "계남경로당", lon: 128.00665, lat: 35.36106, capacity: 200 },
      { id: "K007", name: "구사경로당", lon: 127.89877, lat: 35.23218, capacity: 200 },
      { id: "K008", name: "구평보건진료소", lon: 127.848, lat: 35.53151, capacity: 200 },
      { id: "K009", name: "금만경로당", lon: 127.90361, lat: 35.25492, capacity: 200 },
      { id: "K010", name: "금서면문화복지회관", lon: 127.8625, lat: 35.41741, capacity: 200 },
      { id: "K011", name: "길리마을회관", lon: 127.91736, lat: 35.26822, capacity: 200 },
      { id: "K012", name: "내대마을경로당", lon: 127.74531, lat: 35.27792, capacity: 200 },
      { id: "K013", name: "내대보건진료소", lon: 127.74623, lat: 35.27715, capacity: 200 },
      { id: "K014", name: "내부마을회관", lon: 127.90164, lat: 35.42257, capacity: 200 },
      { id: "K015", name: "내원마을회관", lon: 127.79437, lat: 35.31155, capacity: 200 },
      { id: "K016", name: "대둔마을회관", lon: 128.03881, lat: 35.33721, capacity: 200 },
      { id: "K017", name: "대포곶감마을회관", lon: 127.82917, lat: 35.29611, capacity: 200 },
      { id: "K018", name: "대포마을회관", lon: 127.82916, lat: 35.29611, capacity: 200 },
      { id: "K019", name: "덕산고등학교", lon: 127.83413, lat: 35.27559, capacity: 200 },
      { id: "K020", name: "덕산중학교", lon: 127.83368, lat: 35.27581, capacity: 200 },
      { id: "K021", name: "덕산초등학교", lon: 127.83684, lat: 35.27873, capacity: 200 },
      { id: "K022", name: "덕촌마을회관", lon: 127.88459, lat: 35.41819, capacity: 200 },
      { id: "K023", name: "도전마을회관", lon: 128.01701, lat: 35.33699, capacity: 200 },
      { id: "K024", name: "도평마을회관", lon: 127.94609, lat: 35.27555, capacity: 200 },
      { id: "K025", name: "마흘마을회관", lon: 127.94383, lat: 35.30868, capacity: 200 },
      { id: "K026", name: "만암경로당", lon: 127.96007, lat: 35.47188, capacity: 200 },
      { id: "K027", name: "명동마을회관", lon: 127.95462, lat: 35.31938, capacity: 200 },
      { id: "K028", name: "명상마을회관", lon: 127.83763, lat: 35.34174, capacity: 200 },
      { id: "K029", name: "명상마을회관", lon: 127.8376, lat: 35.34177, capacity: 200 },
      { id: "K030", name: "모고마을회관", lon: 127.88856, lat: 35.43074, capacity: 200 },
      { id: "K031", name: "모례마을회관", lon: 127.9844, lat: 35.39745, capacity: 200 },
      { id: "K032", name: "모례마을회관", lon: 127.98436, lat: 35.39754, capacity: 200 },
      { id: "K033", name: "방곡마을회관", lon: 127.7814, lat: 35.42328, capacity: 200 },
      { id: "K034", name: "방곡마을회관", lon: 127.78137, lat: 35.4233, capacity: 200 },
      { id: "K035", name: "방목경로당", lon: 127.93774, lat: 35.32397, capacity: 200 },
      { id: "K036", name: "방목회관", lon: 127.93774, lat: 35.32397, capacity: 200 },
      { id: "K037", name: "방화마을회관", lon: 128.08778, lat: 35.3402, capacity: 200 },
      { id: "K038", name: "배양마을회관", lon: 127.95666, lat: 35.29158, capacity: 200 },
      { id: "K039", name: "백운덕촌경로당", lon: 127.89127, lat: 35.27914, capacity: 200 },
      { id: "K040", name: "백운마을회관", lon: 127.88922, lat: 35.27256, capacity: 200 },
      { id: "K041", name: "백운마을회관", lon: 127.88894, lat: 35.27296, capacity: 200 },
      { id: "K042", name: "범학마을경로회관", lon: 127.91398, lat: 35.38911, capacity: 200 },
      { id: "K043", name: "법물보건진료소", lon: 128.00508, lat: 35.41137, capacity: 200 },
      { id: "K044", name: "북촌마을회관", lon: 127.84628, lat: 35.35693, capacity: 200 },
      { id: "K045", name: "사리마을회관", lon: 127.85137, lat: 35.27248, capacity: 200 },
      { id: "K046", name: "산청고등학교", lon: 127.87057, lat: 35.40975, capacity: 200 },
      { id: "K047", name: "산청고등학교", lon: 127.87109, lat: 35.40992, capacity: 200 },
      { id: "K048", name: "산청복음전문요야원", lon: 127.93145, lat: 35.33035, capacity: 200 },
      { id: "K049", name: "산청유치원", lon: 127.94999, lat: 35.33058, capacity: 200 },
      { id: "K050", name: "삼거마을회관", lon: 127.93232, lat: 35.49978, capacity: 200 },
      { id: "K051", name: "삼장면복지회관", lon: 127.8313, lat: 35.29786, capacity: 200 },
      { id: "K052", name: "상법마을회관", lon: 127.9615, lat: 35.46389, capacity: 200 },
      { id: "K053", name: "생초면종합복지회관", lon: 127.83651, lat: 35.49388, capacity: 200 },
      { id: "K054", name: "생초초등학교", lon: 127.83616, lat: 35.49475, capacity: 200 },
      { id: "K055", name: "생초초등학교", lon: 127.83621, lat: 35.49469, capacity: 200 },
      { id: "K056", name: "석대마을회관", lon: 127.92828, lat: 35.31047, capacity: 200 },
      { id: "K057", name: "석상마을회관", lon: 127.83351, lat: 35.32953, capacity: 200 },
      { id: "K058", name: "송정마을회관", lon: 127.85426, lat: 35.48732, capacity: 200 },
      { id: "K059", name: "시천면사무소", lon: 127.84034, lat: 35.27854, capacity: 200 },
      { id: "K060", name: "시천면행정복지센터", lon: 127.8405, lat: 35.27841, capacity: 200 },
      { id: "K061", name: "신기마을회관", lon: 127.9134, lat: 35.37323, capacity: 200 },
      { id: "K062", name: "신등119지역대", lon: 128.01079, lat: 35.37631, capacity: 200 },
      { id: "K063", name: "신등고등학교", lon: 128.01314, lat: 35.38789, capacity: 200 },
      { id: "K064", name: "신안초등학교", lon: 127.97231, lat: 35.30162, capacity: 200 },
      { id: "K065", name: "실매경로당", lon: 127.93421, lat: 35.49056, capacity: 200 },
      { id: "K066", name: "심거경로당", lon: 127.91996, lat: 35.36756, capacity: 200 },
      { id: "K067", name: "쌍효마을회관", lon: 127.8204, lat: 35.45884, capacity: 200 },
      { id: "K068", name: "양당마을회관", lon: 127.84603, lat: 35.2772, capacity: 200 },
      { id: "K069", name: "어천마을회관", lon: 127.91467, lat: 35.35828, capacity: 200 },
      { id: "K070", name: "연화마을회관", lon: 127.84076, lat: 35.27756, capacity: 200 },
      { id: "K071", name: "오부면사무소", lon: 127.86182, lat: 35.4587, capacity: 200 },
      { id: "K072", name: "오휴경로당", lon: 127.90397, lat: 35.51127, capacity: 200 },
      { id: "K073", name: "운곡경로당", lon: 127.89397, lat: 35.43737, capacity: 200 },
      { id: "K074", name: "운리마을회관", lon: 127.90004, lat: 35.31601, capacity: 200 },
      { id: "K075", name: "원방곡마을회관", lon: 127.88623, lat: 35.46923, capacity: 200 },
      { id: "K076", name: "입석마을경로당", lon: 127.91389, lat: 35.28567, capacity: 200 },
      { id: "K077", name: "자양마을회관", lon: 127.89264, lat: 35.25949, capacity: 200 },
      { id: "K078", name: "장란마을회관", lon: 128.03497, lat: 35.34281, capacity: 200 },
      { id: "K079", name: "장박마을회관", lon: 127.94215, lat: 35.5071, capacity: 200 },
      { id: "K080", name: "장재경로당", lon: 127.85688, lat: 35.44607, capacity: 200 },
      { id: "K081", name: "장천마을회관", lon: 127.99604, lat: 35.40246, capacity: 200 },
      { id: "K082", name: "제보경로당", lon: 128.08052, lat: 35.3729, capacity: 200 },
      { id: "K083", name: "제보마을경로당", lon: 128.08051, lat: 35.37291, capacity: 200 },
      { id: "K084", name: "주상마을회관", lon: 127.78622, lat: 35.45913, capacity: 200 },
      { id: "K085", name: "죽전노인회관", lon: 127.83627, lat: 35.34508, capacity: 200 },
      { id: "K086", name: "중방마을회관", lon: 127.8832, lat: 35.47019, capacity: 200 },
      { id: "K087", name: "중산보건진료소", lon: 127.75391, lat: 35.29268, capacity: 200 },
      { id: "K088", name: "중암경로당", lon: 127.83974, lat: 35.5119, capacity: 200 },
      { id: "K089", name: "중촌마을회관", lon: 127.89447, lat: 35.50677, capacity: 200 },
      { id: "K090", name: "지막마을회관", lon: 127.83542, lat: 35.40518, capacity: 200 },
      { id: "K091", name: "차황면복지회관", lon: 127.92741, lat: 35.46474, capacity: 200 },
      { id: "K092", name: "차황보건지소", lon: 127.92728, lat: 35.46474, capacity: 200 },
      { id: "K093", name: "창평마을회관", lon: 127.93555, lat: 35.46985, capacity: 200 },
      { id: "K094", name: "척지마을회관", lon: 127.94779, lat: 35.40402, capacity: 200 },
      { id: "K095", name: "척지마을회관", lon: 127.94776, lat: 35.40403, capacity: 200 },
      { id: "K096", name: "천평마을회관", lon: 127.8374, lat: 35.26763, capacity: 200 },
      { id: "K097", name: "특리마을회관", lon: 127.84822, lat: 35.44195, capacity: 200 },
      { id: "K098", name: "평촌마을회관", lon: 127.83028, lat: 35.34382, capacity: 200 },
      { id: "K099", name: "평촌마을회관", lon: 127.84591, lat: 35.41293, capacity: 200 },
      { id: "K100", name: "평촌마을회관", lon: 127.83027, lat: 35.34384, capacity: 200 },
      { id: "K101", name: "하능마을회관", lon: 128.06281, lat: 35.37387, capacity: 200 },
      { id: "K102", name: "한국선비문화연구원", lon: 127.84569, lat: 35.27548, capacity: 200 },
      { id: "K103", name: "화산마을회관", lon: 127.79495, lat: 35.45731, capacity: 200 },
      { id: "K104", name: "후평마을회관", lon: 127.81782, lat: 35.23758, capacity: 200 },
    ],
    // 산청군을 감싸는 사각형 — 인접 시군(함양·진주·하동 등)이 일부 섞인다(README 한계 참조).
    isolationBbox: [127.72, 35.19, 128.12, 35.56],
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
