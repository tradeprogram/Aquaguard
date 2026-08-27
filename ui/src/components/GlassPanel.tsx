"use client";

import type { ReactNode } from "react";

interface GlassPanelProps {
  title: string;
  onClose: () => void;
  children: ReactNode;
}

export default function GlassPanel({ title, onClose, children }: GlassPanelProps) {
  return (
    <div className="flex h-[72vh] max-h-[820px] w-[70vw] max-w-[1000px] flex-col overflow-hidden rounded-2xl border border-white/15 bg-slate-950/60 shadow-2xl backdrop-blur-xl">
      <div className="flex items-center justify-between border-b border-white/10 bg-slate-950/40 px-4 py-3 backdrop-blur-xl">
        <span className="text-base font-semibold text-sky-300">{title}</span>
        <button onClick={onClose} aria-label="패널 닫기" className="text-lg text-slate-400 hover:text-slate-200">
          ✕
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-4 py-4">{children}</div>
    </div>
  );
}
