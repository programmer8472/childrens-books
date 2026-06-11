export default function HomePage() {
  return (
    <div className="flex h-full min-h-[60vh] flex-col items-center justify-center px-6 py-24 text-center">
      <p className="text-5xl mb-4">📖</p>
      <h1 className="text-lg font-semibold text-gray-200 mb-1">
        Select a book to view its pipeline
      </h1>
      <p className="text-sm text-gray-500 max-w-sm">
        Pick a run from the list on the left to see exactly where it is, watch
        live progress, and cancel it if needed — or create a new book.
      </p>
    </div>
  );
}
