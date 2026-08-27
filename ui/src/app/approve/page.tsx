"use client";

import { Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { SANGCHEONG_DEMO_INPUT } from "@/lib/api";
import ApprovePanel from "@/components/panels/ApprovePanel";

// 지도 위 글라스 패널이 기본 경로가 됐지만, 이 경로는 직접 링크·단독 테스트용으로 남겨둔다.
function ApproveContent() {
  const searchParams = useSearchParams();
  const alertId = searchParams.get("alert_id") ?? SANGCHEONG_DEMO_INPUT.alert_id;

  return (
    <div className="mx-auto max-w-2xl space-y-4 p-6">
      <Link href="/" className="text-xs text-sky-400 hover:text-sky-300">
        ← 지도로
      </Link>
      <h1 className="text-2xl font-bold">원클릭 승인</h1>
      <ApprovePanel alertId={alertId} />
    </div>
  );
}

export default function ApprovePage() {
  return (
    <Suspense fallback={<div className="p-6 text-slate-500">불러오는 중…</div>}>
      <ApproveContent />
    </Suspense>
  );
}
