import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title: "K8s DevOps Assistant",
  description: "AI-powered Kubernetes assistant — ask a question or paste an error.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body
        className={`${inter.variable} font-sans antialiased`}
        style={{
          backgroundColor: "#09090B",
          color: "#FAFAFA",
          minHeight: "100vh",
        }}
      >
        {children}
      </body>
    </html>
  );
}
