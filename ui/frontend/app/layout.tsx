import type { Metadata } from "next";
import { IBM_Plex_Sans, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";

const plexSans = IBM_Plex_Sans({ subsets: ["latin"], weight: ["300", "400", "500", "600", "700"], variable: "--font-sans" });
const plexMono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["300", "400", "500", "600"], variable: "--font-mono" });

export const metadata: Metadata = {
  title: "KubeAstra — Astra Intent",
  description: "AI-powered Kubernetes assistant — ask a question or paste an error. KubeAstra routes to the right tool automatically.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body
        className={`${plexSans.variable} ${plexMono.variable} font-sans antialiased`}
        style={{
          backgroundColor: "var(--paper)",
          color: "var(--ink)",
          minHeight: "100vh",
        }}
      >
        {children}
      </body>
    </html>
  );
}
