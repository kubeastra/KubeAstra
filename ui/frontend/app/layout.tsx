import type { Metadata } from "next";
import { Inter, Fira_Code } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const firaCode = Fira_Code({ subsets: ["latin"], variable: "--font-mono", weight: ["300", "400", "500"] });

export const metadata: Metadata = {
  title: "KubeAstra — Astra Intent",
  description: "AI-powered Kubernetes assistant — ask a question or paste an error. KubeAstra routes to the right tool automatically.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body
        className={`${inter.variable} ${firaCode.variable} font-sans antialiased`}
        style={{
          backgroundColor: "#07091A",
          color: "#E2E8F0",
          minHeight: "100vh",
        }}
      >
        {children}
      </body>
    </html>
  );
}
