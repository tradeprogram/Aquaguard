import Link from "next/link";
import WhatifPanel from "@/components/panels/WhatifPanel";

// 지도 위 글라스 패널이 기본 경로가 됐지만, 이 경로는 직접 링크·단독 테스트용으로 남겨둔다.
export default function WhatIfPage() {
  return (
    <div className="mx-auto max-w-2xl space-y-4 p-6">
      <Link href="/" className="text-xs text-sky-400 hover:text-sky-300">
        ← 지도로
      </Link>
      <h1 className="text-2xl font-bold">What-if 예측 시뮬레이터</h1>
      <WhatifPanel />
    </div>
  );
}
