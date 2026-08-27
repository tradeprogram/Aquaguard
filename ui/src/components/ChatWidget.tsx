"use client";

import { useEffect, useRef, useState } from "react";
import { sendChatMessage } from "@/lib/api";

interface ChatMessage {
  role: "user" | "bot";
  text: string;
}

const GREETING: ChatMessage = {
  role: "bot",
  text: "안녕하세요! Aqua Guard.AI예요. 골든타임, 대피소, 산사태·침수 상황에 대해 물어보세요.",
};

export default function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([GREETING]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [messages, open]);

  const send = async () => {
    const text = input.trim();
    if (!text || sending) return;
    setMessages((prev) => [...prev, { role: "user", text }]);
    setInput("");
    setSending(true);
    try {
      const reply = await sendChatMessage(text);
      setMessages((prev) => [...prev, { role: "bot", text: reply }]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "bot", text: "죄송해요, 지금은 응답을 가져올 수 없어요. 서버가 켜져 있는지 확인해주세요." },
      ]);
    } finally {
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
            {sending && (
              <div className="flex justify-start">
                <div className="max-w-[85%] rounded-lg border border-white/10 bg-white/10 px-3 py-2 text-sm text-slate-400 backdrop-blur-sm">
                  ···
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
              disabled={sending}
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
