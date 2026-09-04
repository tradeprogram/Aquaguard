"use client";

import { useState } from "react";
import MapExplorer, { type EvacuationRoute } from "@/components/MapExplorer";
import GlassPanel from "@/components/GlassPanel";
import DashboardPanel from "@/components/panels/DashboardPanel";
import EvacuationPanel from "@/components/panels/EvacuationPanel";
import IsolationPanel from "@/components/panels/IsolationPanel";
import WhatifPanel from "@/components/panels/WhatifPanel";
import ModelPerformancePanel from "@/components/panels/ModelPerformancePanel";
import ApprovePanel from "@/components/panels/ApprovePanel";
import ValidationPanel from "@/components/panels/ValidationPanel";

type PanelKey = "dashboard" | "evacuation" | "isolation" | "whatif" | "performance" | "validation" | "approve";
type Mode = "citizen" | "gov";

// 시민용 기능(내 위치 기반 대피 안내)과 관공서용 기능(관 대응 비교·피해비용·모델 성능
// 증빙·원클릭 승인)이 한 메뉴에 섞여 있으면 "이거 누구 쓰라고 만든 거야?"가 돼버린다.
// 그래서 화면을 모드로 나눈다 — 기본은 시민 모드(배포 대상), 관공서 모드는 옆의
// 작은 토글로만 들어간다. 대시보드는 두 모드 모두에 있지만 DashboardPanel이
// mode를 받아 관 대응 비교(GoldenTimeCounter)·예상 피해비용(Module G)은 관공서
// 모드에서만 보여준다 — 나머지(산사태·홍수 확률, 지하차도, 노출자산, 대피 경로)는
// 시민에게도 그대로 유의미해서 공유한다.
const MENU: Record<Mode, { key: PanelKey; label: string }[]> = {
  citizen: [
    { key: "dashboard", label: "위험 현황" },
    { key: "evacuation", label: "대피소 찾기" },
    { key: "isolation", label: "고립마을 위험" },
  ],
  gov: [
    { key: "dashboard", label: "대시보드" },
    { key: "performance", label: "모델 성능" },
    { key: "validation", label: "검증 (Predicted vs Observed)" },
    { key: "whatif", label: "What-if 시뮬레이터" },
    { key: "approve", label: "원클릭 승인" },
  ],
};

const PANEL_TITLE: Record<Mode, Partial<Record<PanelKey, string>>> = {
  citizen: {
    dashboard: "우리 동네 위험 현황",
    evacuation: "대피소 찾기",
    isolation: "고립마을 위험 (독창성 축 4)",
  },
  gov: {
    dashboard: "아쿠아가드 골든타임 대시보드",
    performance: "모델 성능 검증 (Module A/B)",
    validation: "검증 (§5 Module V) — Predicted vs Observed",
    whatif: "What-if 예측 시뮬레이터",
    approve: "원클릭 승인 (§5 Module O)",
  },
};

export default function HomePage() {
  const [mode, setMode] = useState<Mode>("citizen");
  const [active, setActive] = useState<PanelKey | null>(null);
  // 대피소 찾기(§6.9)에서 고른 경로 — EvacuationPanel과 MapExplorer가 형제 컴포넌트라
  // 여기서 상태를 끌어올려 양쪽에 내려준다(HANDOFF.md §6.9 "권장" 방식).
  const [evacuationRoute, setEvacuationRoute] = useState<EvacuationRoute | null>(null);
  // §6.8 폴백 ① — "지도에서 선택" 모드와, 클릭으로 받은 좌표도 같은 방식으로 연결.
  const [pickingOrigin, setPickingOrigin] = useState(false);
  const [pickedOrigin, setPickedOrigin] = useState<[number, number] | null>(null);
  // §7 IsolationPanel↔MapExplorer도 형제 컴포넌트라 같은 방식으로 상태를 끌어올린다.
  const [isolatedAreas, setIsolatedAreas] = useState<GeoJSON.FeatureCollection | null>(null);
  const [focusBbox, setFocusBbox] = useState<{ bbox: [number, number, number, number]; nonce: number } | null>(null);

  return (
    <div className="relative h-full w-full">
      <MapExplorer
        route={evacuationRoute}
        pickOrigin={pickingOrigin}
        onOriginPicked={(coord) => {
          setPickedOrigin(coord);
          setPickingOrigin(false);
        }}
        isolatedAreas={isolatedAreas}
        focusBbox={focusBbox}
      />

      {/* 지도가 메인 화면 — 메뉴는 더 이상 페이지를 이동시키지 않고 지도 위에
          글라스 톤 패널을 띄운다/닫는다(토글). 로고는 흰색 워드마크라 밝은 지도
          위에서 안 보이니 네이비 배경 박스에 넣어 항상 대비를 확보한다. */}
      <div className="pointer-events-none absolute inset-x-0 top-0 z-20 flex items-center gap-3 p-4">
        <div className="pointer-events-auto flex items-center rounded-xl border border-white/10 bg-[#050b1f] px-3 py-2 shadow-lg">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/aquaguard-logo.png" alt="Aqua Guard.AI" width={554} height={125} className="h-7 w-auto" />
        </div>
        <div className="pointer-events-auto flex gap-1.5 rounded-xl border border-white/20 bg-slate-950/85 p-1.5 shadow-lg backdrop-blur-xl">
          {MENU[mode].map((item) => (
            <button
              key={item.key}
              onClick={() => setActive((cur) => (cur === item.key ? null : item.key))}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                active === item.key ? "bg-sky-500/70 text-white" : "text-slate-200 hover:bg-white/15 hover:text-white"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>

        {/* 관공서 모드는 기본이 아니다 — 배지처럼 눈에 띄지 않게, 하지만 명확히 다른
            색(호박색)으로 둬서 "지금 관공서 화면을 보고 있다"는 걸 착각하지 않게 한다. */}
        <div className="pointer-events-auto ml-auto flex gap-1 rounded-xl border border-white/20 bg-slate-950/85 p-1 shadow-lg backdrop-blur-xl">
          {(["citizen", "gov"] as const).map((m) => (
            <button
              key={m}
              onClick={() => {
                setMode(m);
                setActive(null);
              }}
              className={`rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition-colors ${
                mode === m
                  ? m === "gov"
                    ? "bg-amber-500/70 text-white"
                    : "bg-sky-500/70 text-white"
                  : "text-slate-300 hover:bg-white/15 hover:text-white"
              }`}
            >
              {m === "citizen" ? "시민 모드" : "관공서 모드"}
            </button>
          ))}
        </div>
      </div>

      {active && (
        <div className="pointer-events-none absolute inset-0 z-20 flex items-start justify-center pt-24">
          <div className="pointer-events-auto">
            <GlassPanel title={PANEL_TITLE[mode][active] ?? ""} onClose={() => setActive(null)}>
              {active === "dashboard" && <DashboardPanel mode={mode} />}
              {active === "performance" && <ModelPerformancePanel />}
              {active === "validation" && <ValidationPanel />}
              {active === "evacuation" && (
                <EvacuationPanel
                  onSelectRoute={setEvacuationRoute}
                  onRequestMapPick={() => setPickingOrigin(true)}
                  mapPickedOrigin={pickedOrigin}
                />
              )}
              {active === "isolation" && (
                <IsolationPanel
                  onResult={(r) => setIsolatedAreas(r?.isolated_areas ?? null)}
                  onFocusCluster={(bbox) => {
                    // 패널이 화면을 넓게 덮고 있으면 지도가 이동해도 가려서 안 보이므로
                    // (2026-09-03 사용자 피드백 — "눌러도 아무 반응 없음"), 클릭 즉시
                    // 패널을 닫아 이동한 결과가 바로 보이게 한다.
                    setFocusBbox({ bbox, nonce: Date.now() });
                    setActive(null);
                  }}
                />
              )}
              {active === "whatif" && <WhatifPanel />}
              {active === "approve" && <ApprovePanel />}
            </GlassPanel>
          </div>
        </div>
      )}
    </div>
  );
}
