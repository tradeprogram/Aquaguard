"use client";

import { useState } from "react";

// Provenance 배지(§6.1)와 짝을 이루는 두 번째 채널 — 자세한 배경은 lib/provenance.ts.
// 배지가 "어떻게 산출됐는가"를 말한다면 이건 "그 산출에 어떤 가정이 얹혀 있는가"를
// 말한다. 접어두는 이유는 화면을 지키기 위해서가 아니라, 가정이 3~4개씩 붙는 값이
// 있어서 펼쳐두면 정작 숫자가 안 읽히기 때문이다. 개수는 항상 보이게 둔다.
export default function AssumptionNote({ items }: { items: string[] }) {
  const [open, setOpen] = useState(false);
  if (!items.length) return null;

  return (
    <div className="mt-1">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="inline-flex items-center gap-1 rounded-full border border-amber-700/40 bg-amber-950/40 px-1.5 py-0.5 text-[9px] font-medium text-amber-300 hover:bg-amber-900/40"
      >
        가정 {items.length}건 {open ? "▴" : "▾"}
      </button>
      {open && (
        <ul className="mt-1 space-y-0.5 border-l border-amber-800/40 pl-2">
          {items.map((text, i) => (
            <li key={i} className="text-[10px] leading-snug text-amber-200/80">
              {text}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
