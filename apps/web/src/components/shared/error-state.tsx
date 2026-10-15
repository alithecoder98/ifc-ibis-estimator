import { Button } from "@/components/ui/button";

// The one error-display shape used across every list/panel in the app (plain
// message + an optional retry button wired to the query's own refetch) -
// pulled out once more than a dozen call sites needed the exact same markup.
export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex items-center gap-3" role="alert">
      <p className="text-sm text-red-600">{message}</p>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}
