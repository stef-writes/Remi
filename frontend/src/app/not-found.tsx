import Link from "next/link";

export default function NotFound() {
  return (
    <div className="h-full flex items-center justify-center">
      <div className="text-center space-y-3">
        <h1 className="text-lg font-semibold text-fg">Page not found</h1>
        <p className="text-sm text-fg-muted">
          The page you are looking for does not exist.
        </p>
        <Link href="/" className="text-xs text-accent hover:underline">
          Back to home
        </Link>
      </div>
    </div>
  );
}
