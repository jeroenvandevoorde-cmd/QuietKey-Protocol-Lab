export function TestBanner() {
  return (
    <div
      className="bg-amber-500 text-black text-center text-sm font-bold tracking-widest py-2 print:hidden"
      data-testid="banner-test-only"
    >
      EXPERIMENTAL — TEST USE ONLY — BROWSER PROTOCOL LABORATORY — NOT A MODEL OF PRODUCTION SECRET HANDLING — DO NOT USE WITH REAL FUNDS
    </div>
  );
}
