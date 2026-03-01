import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { TopNav } from "@/components/TopNav";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "ClauseLens",
  description: "Legal contract risk review and clause parsing",
};

export const viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className={inter.className}>
        <div className="min-h-screen bg-background">
          <TopNav />
          <main className="container mx-auto min-w-0 px-3 py-4 sm:px-4 sm:py-6 max-w-7xl">{children}</main>
        </div>
      </body>
    </html>
  );
}
