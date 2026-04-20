"use client";

import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Search,
  History,
  Wrench,
  XCircle,
  ClipboardList,
  Settings,
  Activity,
  FlaskConical,
} from "lucide-react";
import ThemeToggle from "./ThemeToggle";
import { cn } from "@/lib/utils";

const links = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/scan", label: "Scan Results", icon: Search },
  { href: "/history", label: "Scan History", icon: History },
  { href: "/trades", label: "Trade Builder", icon: Wrench },
  { href: "/rejections", label: "Rejections", icon: XCircle },
  { href: "/backtests", label: "Backtests", icon: FlaskConical },
  { href: "/audit", label: "Audit Trail", icon: ClipboardList },
  { href: "/settings", label: "Settings", icon: Settings },
];

export default function Sidebar() {
  const pathname = usePathname();

  function isActive(href: string) {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  }

  return (
    <aside className="flex w-64 flex-col border-r border-surface-3 bg-white dark:border-gray-700 dark:bg-gray-800">
      {/* Brand */}
      <div className="flex h-16 items-center justify-between border-b border-surface-3 px-5 dark:border-gray-700">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-700 dark:bg-brand-600">
            <Activity className="h-4 w-4 text-white" />
          </div>
          <div>
            <h1 className="text-sm font-bold tracking-tight text-gray-900 dark:text-gray-100">ECE</h1>
            <p className="text-[10px] font-medium text-gray-400 dark:text-gray-500">v0.2.0</p>
          </div>
        </div>
        <ThemeToggle />
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-0.5 px-3 py-4">
        {links.map((link) => {
          const Icon = link.icon;
          const active = isActive(link.href);
          return (
            <a
              key={link.href}
              href={link.href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all",
                active
                  ? "bg-brand-50 text-brand-700 shadow-sm dark:bg-brand-900/30 dark:text-brand-300"
                  : "text-gray-600 hover:bg-surface-2 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-700 dark:hover:text-gray-200"
              )}
            >
              <Icon className={cn("h-4 w-4 flex-shrink-0", active ? "text-brand-600 dark:text-brand-400" : "")} />
              {link.label}
              {active && (
                <span className="ml-auto h-1.5 w-1.5 rounded-full bg-brand-500" />
              )}
            </a>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="border-t border-surface-3 p-4 dark:border-gray-700">
        <p className="text-[10px] leading-tight text-gray-400 dark:text-gray-500">
          Decision-support only. No guaranteed profits. Verify all data
          independently.
        </p>
      </div>
    </aside>
  );
}
