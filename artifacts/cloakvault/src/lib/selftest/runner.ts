/**
 * Minimal in-browser test runner for the Self-Test page.
 *
 * The suites in ./suites.ts are direct ports of the vitest files under
 * src/lib/(star)/__tests__ — same inputs, same assertions, same counts.
 * This runner only provides the assertion helpers and sequencing; it never
 * weakens, samples, or skips a test.
 */

export class AssertionError extends Error {}

function fail(message: string): never {
  throw new AssertionError(message);
}

export const assert = {
  ok(cond: unknown, msg = 'expected truthy'): void {
    if (!cond) fail(msg);
  },
  eq(actual: unknown, expected: unknown, msg?: string): void {
    // Strict equality on primitives; deep equality on arrays.
    if (Array.isArray(actual) && Array.isArray(expected)) {
      if (
        actual.length !== expected.length ||
        actual.some((v, i) => v !== expected[i])
      ) {
        fail(msg ?? `expected [${expected}] but got [${actual}]`);
      }
      return;
    }
    if (actual !== expected) {
      fail(msg ?? `expected ${JSON.stringify(expected)} but got ${JSON.stringify(actual)}`);
    }
  },
  notEq(actual: unknown, expected: unknown, msg?: string): void {
    if (actual === expected) fail(msg ?? `expected values to differ, both were ${JSON.stringify(actual)}`);
  },
  match(actual: string, re: RegExp, msg?: string): void {
    if (!re.test(actual)) fail(msg ?? `expected "${actual}" to match ${re}`);
  },
  throws(fn: () => unknown, expected?: RegExp | (new (...args: never[]) => Error), msg?: string): void {
    try {
      fn();
    } catch (e) {
      if (expected instanceof RegExp) {
        const text = e instanceof Error ? e.message : String(e);
        if (!expected.test(text)) fail(msg ?? `threw, but message "${text}" did not match ${expected}`);
      } else if (typeof expected === 'function') {
        if (!(e instanceof expected)) fail(msg ?? `threw wrong error type: ${String(e)}`);
      }
      return;
    }
    fail(msg ?? 'expected function to throw, but it did not');
  },
  gte(actual: number, min: number, msg?: string): void {
    if (!(actual >= min)) fail(msg ?? `expected ${actual} >= ${min}`);
  },
  lte(actual: number, max: number, msg?: string): void {
    if (!(actual <= max)) fail(msg ?? `expected ${actual} <= ${max}`);
  },
};

export type TestScope = 'smoke' | 'full';

export interface TestCase {
  name: string;
  /** 'smoke' runs on page load AND in the full suite; 'full' only via Run Full Suite. */
  scope: TestScope;
  run: () => void;
}

export interface SuiteGroup {
  id: string;
  label: string;
  tests: TestCase[];
}

export interface TestResult {
  name: string;
  ok: boolean;
  error?: string;
  ms: number;
}

export interface GroupResult {
  id: string;
  label: string;
  scope: TestScope;
  tests: TestResult[];
  passed: number;
  failed: number;
  ms: number;
  done: boolean;
}

const yieldToUi = () => new Promise<void>((r) => setTimeout(r, 0));

/**
 * Run the given groups sequentially. scope='smoke' runs only smoke-tagged
 * tests; scope='full' runs every test (smoke + full) at full counts.
 */
export async function runGroups(
  groups: SuiteGroup[],
  scope: TestScope,
  onProgress: (results: GroupResult[]) => void,
): Promise<GroupResult[]> {
  const results: GroupResult[] = groups.map((g) => ({
    id: g.id,
    label: g.label,
    scope,
    tests: [],
    passed: 0,
    failed: 0,
    ms: 0,
    done: false,
  }));
  onProgress([...results]);

  for (let gi = 0; gi < groups.length; gi++) {
    const group = groups[gi];
    const res = results[gi];
    const selected = scope === 'full' ? group.tests : group.tests.filter((t) => t.scope === 'smoke');
    for (const test of selected) {
      await yieldToUi();
      const t0 = performance.now();
      try {
        test.run();
        res.tests.push({ name: test.name, ok: true, ms: performance.now() - t0 });
        res.passed++;
      } catch (e) {
        res.tests.push({
          name: test.name,
          ok: false,
          error: e instanceof Error ? e.message : String(e),
          ms: performance.now() - t0,
        });
        res.failed++;
      }
      res.ms = res.tests.reduce((s, t) => s + t.ms, 0);
      onProgress([...results]);
    }
    res.done = true;
    onProgress([...results]);
  }
  return results;
}
