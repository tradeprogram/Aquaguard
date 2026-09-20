import { SANGCHEONG_DEMO_INPUT, triggerAlert, type TriggerInput } from "./api";

// 화면은 사전계산 스냅샷을 **자기 오리진**에서 읽어 즉시 뜬다(api.ts의 getDemoEnvelope).
// 그런데 원클릭 승인은 백엔드의 alert_store에 그 경보가 있어야 동작한다 — 승인은
// 상태를 바꾸는 일이라 반드시 서버가 해야 하기 때문이다.
//
// 스냅샷만 읽으면 서버는 그 경보를 본 적이 없다. 그래서 위험현황을 방금 돌렸는데도
// 승인 화면이 404를 받아 "먼저 시나리오를 실행하세요"를 띄웠다(2026-09-21 실측).
// 챗봇도 같은 이유로 컨텍스트 없이 답했다(그쪽은 서버가 스냅샷을 직접 읽도록 고쳤다).
//
// 그래서 스냅샷으로 화면을 띄운 직후, 같은 입력을 백엔드에도 한 번 보낸다.
// **화면은 이걸 기다리지 않는다** — 서버도 같은 스냅샷으로 답하므로 금방 끝나고,
// 늦더라도 지도가 뜨는 속도에 영향을 주지 않는다.

type Registration = "idle" | "pending" | "ready" | "failed";

let state: Registration = "idle";
let inFlight: Promise<boolean> | null = null;

/** 이 세션에서 사용자가 시나리오를 돌렸는가. 서버 등록 성공 여부와는 별개다. */
export function scenarioRan(): boolean {
  return state !== "idle";
}

export function registrationState(): Registration {
  return state;
}

/** 백엔드에 경보를 등록한다. 이미 등록됐으면 아무것도 하지 않는다. */
export function registerScenario(input: TriggerInput = SANGCHEONG_DEMO_INPUT): Promise<boolean> {
  if (state === "ready") return Promise.resolve(true);
  if (inFlight) return inFlight;
  state = "pending";
  inFlight = triggerAlert(input)
    .then(() => {
      state = "ready";
      return true;
    })
    .catch(() => {
      // 서버가 죽었거나 느린 경우다. 실패를 기억해 두되 다음 시도는 막지 않는다 —
      // 승인 화면이 3초마다 새로고침하므로 그때 다시 붙을 수 있다.
      state = "failed";
      return false;
    })
    .finally(() => {
      inFlight = null;
    });
  return inFlight;
}

/** 실시간 경로(triggerAlert)로 돌았을 때처럼, 이미 서버에 등록된 것이 확실한 경우. */
export function markScenarioRegistered(): void {
  state = "ready";
}

/**
 * 등록이 끝나길 기다린다. 아직 시나리오를 안 돌렸으면 기다리지 않는다.
 * 반환값은 "서버가 이 경보를 알고 있다고 믿을 만한가".
 */
export async function whenRegistered(): Promise<boolean> {
  if (state === "idle") return false;
  if (inFlight) return inFlight;
  return state === "ready";
}
