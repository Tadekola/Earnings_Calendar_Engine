import { cn } from "@/lib/utils";

function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "animate-pulse-subtle rounded-md bg-surface-3 dark:bg-gray-700",
        className
      )}
      {...props}
    />
  );
}

function CardSkeleton() {
  return (
    <div className="rounded-lg border border-surface-3 bg-white p-6 shadow-sm dark:border-gray-700 dark:bg-gray-800">
      <Skeleton className="h-5 w-32 mb-4" />
      <Skeleton className="h-4 w-full mb-2" />
      <Skeleton className="h-4 w-3/4" />
    </div>
  );
}

function KPICardSkeleton() {
  return (
    <div className="rounded-lg border border-surface-3 bg-white p-6 shadow-sm text-center dark:border-gray-700 dark:bg-gray-800">
      <Skeleton className="h-9 w-16 mx-auto mb-2" />
      <Skeleton className="h-3 w-20 mx-auto" />
    </div>
  );
}

function TableRowSkeleton({ cols = 5 }: { cols?: number }) {
  return (
    <tr>
      {Array.from({ length: cols }).map((_, i) => (
        <td key={i} className="py-3 pr-4">
          <Skeleton className="h-4 w-full" />
        </td>
      ))}
    </tr>
  );
}

export { Skeleton, CardSkeleton, KPICardSkeleton, TableRowSkeleton };
