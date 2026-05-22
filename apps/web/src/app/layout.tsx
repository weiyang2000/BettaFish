import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "BettaFish SaaS Console",
  description: "Contract-first SaaS console for BettaFish engines, crawlers, and reports",
  icons: {
    icon: "/icon.svg"
  }
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
