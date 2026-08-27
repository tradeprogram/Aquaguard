"use client";

import { useState } from "react";
import MapExplorer, { type EvacuationRoute } from "@/components/MapExplorer";
import GlassPanel from "@/components/GlassPanel";
import DashboardPanel from "@/components/panels/DashboardPanel";
import EvacuationPanel from "@/components/panels/EvacuationPanel";
import IsolationPanel from "@/components/panels/IsolationPanel";
import WhatifPanel from "@/components/panels/WhatifPanel";
import ModelPerformancePanel from "@/components/panels/ModelPerformancePanel";

type PanelKey = "dashboard" | "evacuation" | "isolation" | "whatif" | "performance";

// 원클릭 승인(§5 Module O)은 지자체 담당자용 워크플로우라 시민 배포 화면에서는 뺐다
// (코드/라우트는 /approve에 그대로 남아있음 — 관 쪽 UI가 따로 필요해지면 재사용).
// 대신 이번에 늘어난 모듈(C/D는 대시보드 안에, E 확장·독창성 축4는 새 메뉴)을 죄다
// 노출시켜서 프로토타입만 보고도 전체 기능 범위가 감이 오게 했다.
const MENU: { key: PanelKey; label: string }[] = [
  { key: "dashboard", label: "대시보드" },
  { key: "performance", label: "모델 성능" },
  { key: "evacuation", label: "대피소 찾기" },
  { key: "isolation", label: "고립마을 위험" },
  { key: "whatif", label: "What-if 시뮬레이터" },
];

const PANEL_TITLE: Record<PanelKey, string> = {
  dashboard: "아쿠아가드 골든타임 대시보드",
  performance: "모델 성능 검증 (Module A/B)",
  evacuation: "대피소 찾기",
  isolation: "고립마을 위험 (독창성 축 4)",
  whatif: "What-if 예측 시뮬레이터",
};

export default function HomePage() {
  const [active, setActive] = useState<PanelKey | null>(null);
  // 대피소 찾기(§6.9)에서 고른 경로 — EvacuationPanel과 MapExplorer가 형제 컴포넌트라
  // 여기서 상태를 끌어올려 양쪽에 내려준다(HANDOFF.md §6.9 "권장" 방식).
  const [evacuationRoute, setEvacuationRoute] = useState<EvacuationRoute | null>(null);
  // §6.8 폴백 ① — "지도에서 선택" 모드와, 클릭으로 받은 좌표도 같은 방식으로 연결.
  const [pickingOrigin, setPickingOrigin] = useState(false);
  const [pickedOrigin, setPickedOrigin] = useState<[number, number] | null>(null);

  return (
    <div className="relative h-full w-full">
      <MapExplorer
        route={evacuationRoute}
        pickOrigin={pickingOrigin}
        onOriginPicked={(coord) => {
          setPickedOrigin(coord);
          setPickingOrigin(false);
        }}
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
          {MENU.map((item) => (
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
      </div>

      {active && (
        <div className="pointer-events-none absolute inset-0 z-20 flex items-start justify-center pt-24">
          <div className="pointer-events-auto">
            <GlassPanel title={PANEL_TITLE[active]} onClose={() => setActive(null)}>
              {active === "dashboard" && <DashboardPanel />}
              {active === "performance" && <ModelPerformancePanel />}
              {active === "evacuation" && (
                <EvacuationPanel
                  onSelectRoute={setEvacuationRoute}
                  onRequestMapPick={() => setPickingOrigin(true)}
                  mapPickedOrigin={pickedOrigin}
                />
              )}
              {active === "isolation" && <IsolationPanel />}
              {active === "whatif" && <WhatifPanel />}
            </GlassPanel>
          </div>
        </div>
      )}
    </div>
  );
}
