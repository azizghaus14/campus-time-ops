import type { Metadata } from "next";
import { Inter } from "next/font/google";

import Shell from "@/components/shell";

import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });

export const metadata: Metadata = {
  title: "Campus Time Ops",
  description: "AI agents that re-plan APU's live timetable, with a human approving every step.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`dark ${inter.variable}`}>
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
