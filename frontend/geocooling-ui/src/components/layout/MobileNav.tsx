"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

type MobileNavigationItem = {
  href: string;
  label: string;
  icon: string;
};

const navigation: MobileNavigationItem[] = [
  {
    href: "/",
    label: "Accueil",
    icon: "▦",
  },
  {
    href: "/brain",
    label: "Brain",
    icon: "◆",
  },
  {
    href: "/historian",
    label: "Courbes",
    icon: "⌁",
  },
  {
    href: "/hardware",
    label: "Matériel",
    icon: "◉",
  },
  {
    href: "/alarms",
    label: "Alarmes",
    icon: "!",
  },
];

function isActive(
  pathname: string,
  href: string,
): boolean {
  if (href === "/") {
    return pathname === "/";
  }

  return (
    pathname === href ||
    pathname.startsWith(`${href}/`)
  );
}

export function MobileNav() {
  const pathname = usePathname();

  return (
    <nav
      className="gc-mobile-nav"
      aria-label="Navigation mobile"
    >
      {navigation.map((item) => {
        const active = isActive(
          pathname,
          item.href,
        );

        return (
          <Link
            key={item.href}
            href={item.href}
            className={
              active
                ? "gc-mobile-nav__link is-active"
                : "gc-mobile-nav__link"
            }
            aria-current={
              active ? "page" : undefined
            }
          >
            <span aria-hidden="true">
              {item.icon}
            </span>

            <small>{item.label}</small>
          </Link>
        );
      })}
    </nav>
  );
}
