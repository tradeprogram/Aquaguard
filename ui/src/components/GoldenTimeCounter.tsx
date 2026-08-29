import type { ModuleOData } from "@/lib/types";
import ProvenanceBadge from "@/components/ProvenanceBadge";

function fmt(iso: string | undefined) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("ko-KR", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function GoldenTimeCounter({ data }: { data: ModuleOData }) {
  const hours = Math.floor(data.golden_time_saved_min / 60);
  const minutes = Math.round(data.golden_time_saved_min % 60);

  return (
    <div className="rounded-xl border border-emerald-800/50 bg-emerald-950/30 p-6">
      <p className="text-sm text-emerald-300/80">골든타임 비교 (§9 데모 시나리오)</p>
      <p className="mt-1 text-4xl font-bold text-emerald-300">
        {hours}시간 {minutes}분 확보
      </p>
      <div className="mt-4 grid grid-cols-2 gap-4 text-sm">
        <div>
          <p className="flex items-center gap-1.5 text-slate-400">
            실제 타임라인 (관 대응) <ProvenanceBadge kind="OBSERVED" />
          </p>
          <p className="mt-1 text-slate-200">
            신고 {fmt(data.timeline_actual.report_start)} → 경보 {fmt(data.timeline_actual.warning_escalated)}
          </p>
        </div>
        <div>
          <p className="flex items-center gap-1.5 text-slate-400">
            에이전트 타임라인 <ProvenanceBadge kind="MODEL" />
          </p>
          <p className="mt-1 text-slate-200">
            탐지 {fmt(data.timeline_agent.detected)} → 발송 {fmt(data.timeline_agent.alert_sent)}
          </p>
        </div>
      </div>
    </div>
  );
}
