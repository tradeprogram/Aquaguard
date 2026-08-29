"use client";

import { useEffect, useRef, useState } from "react";
import { SANGCHEONG_DEMO_INPUT, sendChatMessage } from "@/lib/api";
import { useSlowLoading } from "@/lib/useSlowLoading";

interface ChatMessage {
  role: "user" | "bot";
  text: string;
}

const GREETING: ChatMessage = {
  role: "bot",
  text: "안녕하세요! Aqua Guard.AI예요. 골든타임, 대피소, 산사태·침수 상황에 대해 물어보세요.",
};

// 한 틱에 몇 글자씩 보여줄지 — 800자짜리 답변도 3초 안팎에 다 나오도록 튜닝한 값
const TYPE_CHARS_PER_TICK = 4;
const TYPE_TICK_MS = 15;

export default function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([GREETING]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [typing, setTyping] = useState<{ text: string; shown: number } | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const typeIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const { slow, start, stop } = useSlowLoading();

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [messages, open, typing]);

  // 위젯이 닫히거나 언마운트될 때 타이핑 타이머가 계속 도는 걸 막는다.
  useEffect(() => {
    return () => {
      if (typeIntervalRef.current) clearInterval(typeIntervalRef.current);
    };
  }, []);

  const busy = sending || typing !== null;

  // 답변 전체를 받은 뒤, 실제로 타이핑하듯 몇 글자씩 끊어서 보여준다.
  // 완성되면 그때 messages 배열에 최종본을 편입시킨다.
  //
  // shown을 setTyping의 함수형 업데이터(prev => ...) 안에서 계산하지 않고 이 클로저
  // 변수로 직접 추적한다 — React Strict Mode(dev)는 setState 함수형 업데이터를 순수성
  // 검증을 위해 일부러 두 번 호출하는데, 예전엔 그 업데이터 안에서 setMessages(부작용)를
  // 같이 호출해서 완료 시 봇 답변이 두 번 추가되는 버그가 있었다(실측 확인됨).
  const playTyping = (text: string) => {
    if (typeIntervalRef.current) clearInterval(typeIntervalRef.current);
    let shown = 0;
    setTyping({ text, shown: 0 });
    typeIntervalRef.current = setInterval(() => {
      shown = Math.min(text.length, shown + TYPE_CHARS_PER_TICK);
      if (shown >= text.length) {
        if (typeIntervalRef.current) clearInterval(typeIntervalRef.current);
        typeIntervalRef.current = null;
        setTyping(null);
        setMessages((msgs) => [...msgs, { role: "bot", text }]);
        return;
      }
      setTyping({ text, shown });
    }, TYPE_TICK_MS);
  };

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    setMessages((prev) => [...prev, { role: "user", text }]);
    setInput("");
    setSending(true);
    start();
    try {
      // 이 데모는 산청 시나리오 하나만 다루므로, 대시보드/승인 패널에서 이미 실행됐을
      // 수 있는 그 alert_id를 그대로 컨텍스트로 넘긴다 — 아직 시나리오를 안 돌렸다면
      // 백엔드에서 alert_store에 없는 id로 조회돼 조용히 무시되고 일반 답변만 온다.
      // 인사말은 실제 대화 턴이 아니므로 히스토리에서 제외한다.
      const history = messages.slice(1);
      const reply = await sendChatMessage(text, SANGCHEONG_DEMO_INPUT.alert_id, history);
      playTyping(reply);
    } catch {
      playTyping("죄송해요, 지금은 응답을 가져올 수 없어요. 서버가 켜져 있는지 확인해주세요.");
    } finally {
      stop();
      setSending(false);
    }
  };

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col items-end gap-3">
      {open && (
        <div className="flex h-[43.2rem] max-h-[85vh] w-[30rem] max-w-[90vw] flex-col overflow-hidden rounded-2xl border border-white/10 bg-slate-900/40 shadow-2xl backdrop-blur-xl">
          <div className="flex items-center justify-between border-b border-white/10 bg-slate-950/30 px-4 py-3 backdrop-blur-xl">
            <span className="text-base font-semibold text-sky-300">Aqua Guard.AI</span>
            <button
              onClick={() => setOpen(false)}
              aria-label="챗봇 닫기"
              className="text-lg text-slate-400 hover:text-slate-200"
            >
              ✕
            </button>
          </div>
          <div ref={listRef} className="flex-1 space-y-2 overflow-y-auto px-4 py-3">
            {messages.map((m, i) => (
              <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[85%] whitespace-pre-wrap rounded-lg border px-3 py-2 text-sm backdrop-blur-sm ${
                    m.role === "user"
                      ? "border-sky-300/20 bg-sky-500/60 text-white"
                      : "border-white/10 bg-white/10 text-slate-100"
                  }`}
                >
                  {m.text}
                </div>
              </div>
            ))}
            {typing && (
              <div className="flex justify-start">
                <div className="max-w-[85%] whitespace-pre-wrap rounded-lg border border-white/10 bg-white/10 px-3 py-2 text-sm text-slate-100 backdrop-blur-sm">
                  {typing.text.slice(0, typing.shown)}
                  <span className="ml-0.5 inline-block animate-pulse">▍</span>
                </div>
              </div>
            )}
            {sending && !typing && (
              <div className="flex justify-start">
                <div className="max-w-[85%] rounded-lg border border-white/10 bg-white/10 px-3 py-2 text-sm text-slate-400 backdrop-blur-sm">
                  {slow ? "서버 깨우는 중… (최대 1분)" : "···"}
                </div>
              </div>
            )}
          </div>
          <div className="flex items-center gap-2 border-t border-white/10 bg-slate-950/20 px-3 py-3 backdrop-blur-xl">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") send();
              }}
              placeholder="메시지를 입력하세요"
              className="min-w-0 flex-1 rounded-full border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-1 focus:ring-sky-400"
            />
            <button
              onClick={send}
              disabled={busy}
              aria-label="메시지 전송"
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-sky-300/20 bg-sky-500/60 text-white shadow-md backdrop-blur-sm transition-transform hover:scale-105 hover:bg-sky-400/70 disabled:opacity-50"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">
                <path d="M12 19V5M5 12l7-7 7 7" />
              </svg>
            </button>
          </div>
        </div>
      )}
      <button
        onClick={() => setOpen((v) => !v)}
        aria-label="Aqua Guard.AI 챗봇 열기"
        className="flex h-[4.5rem] w-[4.5rem] items-center justify-center rounded-full border border-sky-300/20 bg-sky-500/60 text-xl font-bold text-white shadow-2xl ring-4 ring-sky-300/20 backdrop-blur-xl transition-transform hover:scale-105 hover:bg-sky-400/70"
      >
        AI
      </button>
    </div>
  );
}
