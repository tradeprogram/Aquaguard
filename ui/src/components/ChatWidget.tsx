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
        <div className="flex h-[50rem] max-h-[85vh] w-[42rem] max-w-[90vw] flex-col overflow-hidden rounded-xl border border-slate-700 bg-slate-900 shadow-2xl">
          <div className="flex items-center justify-between border-b border-slate-800 bg-slate-950 px-5 py-4">
            <span className="text-lg font-semibold text-sky-300">Aqua Guard.AI</span>
            <button
              onClick={() => setOpen(false)}
              aria-label="챗봇 닫기"
              className="text-xl text-slate-400 hover:text-slate-200"
            >
              ✕
            </button>
          </div>
          <div ref={listRef} className="flex-1 space-y-3 overflow-y-auto px-5 py-4">
            {messages.map((m, i) => (
              <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[85%] whitespace-pre-wrap rounded-lg px-4 py-3 text-base ${
                    m.role === "user" ? "bg-sky-600 text-white" : "bg-slate-800 text-slate-100"
                  }`}
                >
                  {m.text}
                </div>
              </div>
            ))}
            {sending && (
              <div className="flex justify-start">
                <div className="max-w-[85%] rounded-lg bg-slate-800 px-4 py-3 text-base text-slate-400">···</div>
              </div>
            )}
          </div>
          <div className="flex items-center gap-3 border-t border-slate-800 px-4 py-4">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") send();
              }}
              placeholder="메시지를 입력하세요"
              className="min-w-0 flex-1 rounded-md border border-slate-700 bg-slate-950 px-4 py-3 text-base text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
            />
            <button
              onClick={send}
              disabled={sending}
              className="rounded-md bg-sky-600 px-5 py-3 text-base font-medium text-white hover:bg-sky-500 disabled:opacity-50"
            >
              전송
            </button>
          </div>
        </div>
      )}
      <button
        onClick={() => setOpen((v) => !v)}
        aria-label="Aqua Guard.AI 챗봇 열기"
        className="flex h-24 w-24 items-center justify-center rounded-full bg-sky-500 text-2xl font-bold text-white shadow-2xl ring-4 ring-sky-400/40 transition-transform hover:scale-105 hover:bg-sky-400"
      >
        AI
      </button>
    </div>
  );
}
