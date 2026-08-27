import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Nav from "@/components/Nav";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "AquaGuard AI — 골든타임 대시보드",
  description: "재해연쇄·골든타임 대응 에이전트 (아쿠아가드)",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="ko"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="h-full flex flex-col bg-slate-950 text-slate-100">
        <Nav />
        <main className="min-h-0 flex-1">{children}</main>
      </body>
    </html>
  );
}
