"use client";

import { usePathname } from "next/navigation";
import ThemeToggle from "./ThemeToggle";

const links = [
  { href: "/", label: "Dashboard", icon: "📊" },
  { href: "/scan", label: "Scan Results", icon: "🔍" },
  { href: "/history", label: "Scan History", icon: "📈" },
  { href: "/trades", label: "Trade Builder", icon: "📐" },
  { href: "/rejections", label: "Rejections", icon: "🚫" },
  { href: "/audit", label: "Audit Trail", icon: "📋" },
  { href: "/settings", label: "Settings", icon: "⚙️" },
];

export default function Sidebar() {
  const pathname = usePathname();

  function isActive(href: string) {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  }

  return (
    <aside className="flex w-64 flex-col border-r border-surface-3 bg-white dark:border-gray-700 dark:bg-gray-800">
      <div className="flex h-16 items-center justify-between border-b border-surface-3 px-6 dark:border-gray-700">
        <div className="flex items-center">
          <h1 className="text-lg font-bold text-brand-800 dark:text-brand-300">ECE</h1>
          <span className="ml-2 text-xs text-gray-500 dark:text-gray-400">v0.1.0</span>
        </div>
        <ThemeToggle />
      </div>
      <nav className="flex-1 space-y-1 px-3 py-4">
        {links.map((link) => (
          <a
            key={link.href}
            href={link.href}
            className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition ${
              isActive(link.href)
                ? "bg-brand-50 text-brand-700 dark:bg-brand-900/30 dark:text-brand-300"
                : "text-gray-700 hover:bg-surface-2 hover:text-brand-700 dark:text-gray-300 dark:hover:bg-gray-700 dark:hover:text-brand-300"
            }`}
          >
            <span>{link.icon}</span>
            {link.label}
          </a>
        ))}
      </nav>
      <div className="border-t border-surface-3 p-4 dark:border-gray-700">
        <p className="text-[10px] leading-tight text-gray-400 dark:text-gray-500">
          Decision-support only. No guaranteed profits. Verify all data
          independently.
        </p>
      </div>
    </aside>
  );
}
