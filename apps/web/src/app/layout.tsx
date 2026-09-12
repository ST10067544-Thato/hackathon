import type { Metadata } from "next";
import { Providers } from "@/components/providers";
import { TopBar } from "@/components/top-bar";
import "@copilotkit/react-core/v2/styles.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "social dog — your social inbox, triaged",
  description:
    "Agents that watch your connected accounts, triage the comments, and draft what comes next. Nothing gets posted without you.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // `dark` switches CopilotKit's chat to its dark token set; globals.css then
  // repaints those tokens in the social dog palette.
  return (
    <html lang="en" className="dark">
      <head>
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800&family=Spline+Sans+Mono:wght@400;500;600&display=swap"
          rel="stylesheet"
        />
        {/* The dog, inlined so the tab icon needs no extra request or asset file. */}
        <link
          rel="icon"
          href={
            "data:image/svg+xml," +
            encodeURIComponent(
              `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 1280">
                <rect width="1280" height="1280" rx="300" fill="#000"/>
                <rect x="265" y="320" width="155" height="370" rx="77" fill="#A6632B"/>
                <rect x="860" y="320" width="155" height="370" rx="77" fill="#A6632B"/>
                <ellipse cx="640" cy="472" rx="248" ry="225" fill="#C6843F"/>
                <rect x="424" y="396" width="198" height="144" rx="54" fill="#171310"/>
                <rect x="668" y="396" width="198" height="144" rx="54" fill="#171310"/>
                <rect x="608" y="440" width="74" height="34" rx="17" fill="#171310"/>
                <rect x="600" y="640" width="80" height="172" rx="40" fill="#FF5C78"/>
                <ellipse cx="640" cy="600" rx="122" ry="80" fill="#FAECCB"/>
                <ellipse cx="640" cy="585" rx="43" ry="31" fill="#2B1B0C"/>
              </svg>`,
            )
          }
        />
      </head>
      <body>
        <Providers>
          <TopBar />
          {children}
        </Providers>
      </body>
    </html>
  );
}
