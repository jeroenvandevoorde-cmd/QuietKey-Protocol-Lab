export function TestBanner() {
  return (
    <div
      className="bg-amber-500 text-black text-center text-sm font-bold tracking-widest py-2 print:hidden"
      data-testid="banner-test-only"
    >
      TEST USE ONLY — EXPERIMENTAL REFERENCE IMPLEMENTATION — DO NOT USE WITH REAL FUNDS
    </div>
  );
}
