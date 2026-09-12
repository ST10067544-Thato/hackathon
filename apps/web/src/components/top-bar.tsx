"use client";

/** Brand bar shared by every page: the mark, the wordmark, and where to go. */
import { usePathname } from "next/navigation";
import { SocialDogLogo } from "@/components/social-dog-logo";

const LINKS = [
  { href: "/creator", label: "Social inbox" },
  { href: "/", label: "Incidents" },
];

export function TopBar() {
  const pathname = usePathname();

  return (
    <header className="sd-topbar">
      <a className="sd-brand" href="/creator">
        <SocialDogLogo size={34} />
        <span className="sd-wordmark">
          social <span className="sd-wordmark-accent">dog</span>
        </span>
      </a>
      <nav className="sd-nav">
        {LINKS.map((link) => (
          <a key={link.href} href={link.href} aria-current={pathname === link.href ? "page" : undefined}>
            {link.label}
          </a>
        ))}
      </nav>
    </header>
  );
}
