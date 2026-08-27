"use client";

import { useState } from "react";
import MapExplorer from "@/components/MapExplorer";
import GlassPanel from "@/components/GlassPanel";
import DashboardPanel from "@/components/panels/DashboardPanel";
import ApprovePanel from "@/components/panels/ApprovePanel";
import WhatifPanel from "@/components/panels/WhatifPanel";

type PanelKey = "dashboard" | "approve" | "whatif";

const MENU: { key: PanelKey; label: string }[] = [
  { key: "dashboard", label: "대시보드" },
  { key: "approve", label: "원클릭 승인" },
  { key: "whatif", label: "What-if 시뮬레이터" },
];

const PANEL_TITLE: Record<PanelKey, string> = {
  dashboard: "아쿠아가드 골든타임 대시보드",
  approve: "원클릭 승인",
  whatif: "What-if 예측 시뮬레이터",
};

export default function HomePage() {
  const [active, setActive] = useState<PanelKey | null>(null);

  return (
    <div className="relative h-full w-full">
      <MapExplorer />

      {/* 지도가 메인 화면 — 메뉴는 더 이상 페이지를 이동시키지 않고 지도 위에
          글라스 톤 패널을 띄운다/닫는다(토글). 로고는 흰색 워드마크라 밝은 지도
          위에서 안 보이니 네이비 배경 박스에 넣어 항상 대비를 확보한다. */}
      <div className="pointer-events-none absolute inset-x-0 top-0 z-20 flex items-center gap-3 p-4">
        <div className="pointer-events-auto flex items-center rounded-xl border border-white/10 bg-[#0a1638] px-3 py-2 shadow-lg">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/aquaguard-logo.png" alt="Aqua Guard.AI" width={554} height={125} className="h-7 w-auto" />
        </div>
        <div className="pointer-events-auto flex gap-1.5 rounded-xl border border-white/10 bg-slate-900/40 p-1.5 shadow-lg backdrop-blur-xl">
          {MENU.map((item) => (
            <button
              key={item.key}
              onClick={() => setActive((cur) => (cur === item.key ? null : item.key))}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                active === item.key ? "bg-sky-500/60 text-white" : "text-slate-300 hover:bg-white/10 hover:text-white"
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
              {active === "dashboard" && <DashboardPanel onOpenApprove={() => setActive("approve")} />}
              {active === "approve" && <ApprovePanel />}
              {active === "whatif" && <WhatifPanel />}
            </GlassPanel>
          </div>
        </div>
      )}
    </div>
  );
}
