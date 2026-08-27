import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import ChatWidget from "@/components/ChatWidget";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// Vercel이 배포마다 VERCEL_URL(예: aquaguard-xyz.vercel.app)을 자동으로 넣어줘서
// 최종 도메인을 몰라도 OG 이미지 절대경로가 정확히 만들어진다(Next.js 권장 패턴).
export const metadata: Metadata = {
  metadataBase: new URL(process.env.VERCEL_URL ? `https://${process.env.VERCEL_URL}` : "http://localhost:3000"),
  title: "AquaGuard AI — 골든타임 대시보드",
  description: "재해연쇄·골든타임 대응 에이전트 (아쿠아가드)",
  openGraph: {
    title: "AquaGuard AI — 골든타임 대시보드",
    description: "재해연쇄·골든타임 대응 에이전트 (아쿠아가드)",
    type: "website",
  },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="ko"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="h-full flex flex-col bg-slate-950 text-slate-100">
        <main className="min-h-0 flex-1">{children}</main>
        <ChatWidget />
      </body>
    </html>
  );
}
