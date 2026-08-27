"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "대시보드" },
  { href: "/approve", label: "원클릭 승인" },
  { href: "/whatif", label: "What-if 시뮬레이터" },
];

export default function Nav() {
  const pathname = usePathname();
  return (
    <nav className="flex gap-1 border-b border-slate-800 bg-slate-950 px-4">
      {LINKS.map((link) => {
        const active = pathname === link.href;
        return (
          <Link
            key={link.href}
            href={link.href}
            className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
              active
                ? "border-sky-400 text-sky-300"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
