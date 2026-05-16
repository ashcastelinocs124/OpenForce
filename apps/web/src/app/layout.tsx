import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Openforce — AI CRM Autopilot",
  description: "AI-proposed Salesforce updates from your inbox.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-50 text-slate-900">{children}</body>
    </html>
  );
}
