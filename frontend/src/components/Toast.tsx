"use client";

import { toast as sonnerToast } from "sonner";

type ToastType = "success" | "error" | "info";

export function useToast() {
  const toast = (message: string, type: ToastType = "info") => {
    switch (type) {
      case "success":
        sonnerToast.success(message);
        break;
      case "error":
        sonnerToast.error(message);
        break;
      default:
        sonnerToast.info(message);
    }
  };
  return { toast };
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
