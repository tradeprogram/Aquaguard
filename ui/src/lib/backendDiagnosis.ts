import { API_BASE } from "./api";

// 백엔드 호출이 실패했을 때, 무엇이 문제인지 실제로 확인하고 안내한다.
//
// 2026-09-06에 배포 서버가 8월 29일 코드에 멈춰 있어서 PR #1이 추가한 엔드포인트
// 3개가 404를 내고 있었는데, 화면에는 "백엔드(VWorld 연동)가 켜져 있는지
// 확인해주세요"라고 떠서 진단이 두 번 헛돌았다. 서버는 멀쩡히 살아 있었고 VWorld도
// 정상이었으며, 실제 원인은 배포가 뒤처진 것이었다.
//
// 그래서 문구를 고정 문자열로 두지 않고 /health를 실제로 찔러 구분한다:
//   서버가 안 뜸        → 서버를 띄우라고 안내
//   떴는데 라우트가 없음 → 배포가 뒤처졌다고 안내 (git pull + 재시작)
//   라우트도 있는데 실패 → 그 요청 자체의 문제 (외부 API·데이터 등)

export interface BackendHealth {
  status: string;
  commit: string | null;
  routes: string[];
  module_sources?: Record<string, "real" | "example">;
  mock_mode?: boolean;
}

/** 실패한 요청의 경로를 받아, 원인을 확인해 사람이 읽을 수 있는 문구를 만든다. */
export async function diagnoseFailure(feature: string, requiredPath: string): Promise<string> {
  let health: BackendHealth | null = null;
  try {
    const res = await fetch(`${API_BASE}/health`, { cache: "no-store" });
    if (res.ok) health = await res.json();
  } catch {
    health = null;
  }

  if (!health) {
    return API_BASE.includes("localhost")
      ? `${feature} 실패 — 백엔드가 응답하지 않습니다. "python -m uvicorn api_server:app --port ${
          new URL(API_BASE).port || "8000"
        }"로 띄워주세요.`
      : `${feature} 실패 — 백엔드 서버가 응답하지 않습니다(${API_BASE}). 서버가 실행 중인지 확인해주세요.`;
  }

  // 서버는 살아 있는데 그 엔드포인트가 없다 = 돌고 있는 코드가 뒤처졌다.
  //
  // commit을 "그러니까 업데이트하세요"의 근거로 쓰면 안 된다 — api_server의
  // _deployed_commit()은 요청받을 때마다 .git/HEAD를 읽으므로 **작업트리**의 커밋이지
  // 프로세스가 적재한 코드가 아니다. git pull만 하고 재시작을 안 하면 commit은 최신인데
  // routes에는 새 엔드포인트가 없는 상태가 된다(2026-09-20 로컬 재현). routes가 유일하게
  // 믿을 수 있는 신호이고, 그래서 문구도 "재시작"을 먼저 말한다.
  if (Array.isArray(health.routes) && !health.routes.includes(requiredPath)) {
    return (
      `${feature} 실패 — 백엔드는 살아 있지만 ${requiredPath} 엔드포인트가 없습니다. ` +
      `돌고 있는 프로세스가 옛 코드입니다 — 서버에서 재시작해주세요` +
      `(파일은 ${health.commit ?? "버전 불명"}까지 받아져 있는데 프로세스가 그걸 안 읽었을 수 있습니다).`
    );
  }

  return (
    `${feature} 실패 — 엔드포인트는 있으나 요청이 처리되지 않았습니다` +
    `(백엔드 ${health.commit ?? "버전 불명"}). 외부 API 키나 대상 지역 데이터를 확인해주세요.`
  );
}
