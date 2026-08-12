import { type ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ErrorBoundary } from '@/components/error-boundary';
import { Toaster } from '@/components/ui/toaster';
import { TooltipProvider } from '@/components/ui/tooltip';
import NotFound from '@/pages/not-found';
import CreatePage from '@/pages/create';
import RecoverPage from '@/pages/recover';
import SharesPage from '@/pages/shares';
import SelfTestPage from '@/pages/self-test';
import { TestBanner } from '@/components/test-banner';
import { Link } from 'wouter';
import {
  Route,
  Switch,
  useLocation,
  Router as WouterRouter,
} from 'wouter';

const queryClient = new QueryClient();

function Router() {
  return (
    // Keep a shared shell (banner, navbar) outside the boundary so it
    // survives a page crash.
    <div className="min-h-screen bg-white text-gray-900">
      <TestBanner />
      <nav className="border-b px-6 py-3 flex gap-6 text-sm print:hidden">
        <Link href="/" className="hover:underline" data-testid="link-create">Create</Link>
        <Link href="/recover" className="hover:underline" data-testid="link-recover">Recover</Link>
        <Link href="/shares" className="hover:underline" data-testid="link-shares">Shares</Link>
        <Link href="/self-test" className="hover:underline" data-testid="link-selftest">Self-Test</Link>
      </nav>
      <RoutedErrorBoundary>
        <Switch>
          <Route path="/" component={CreatePage} />
          <Route path="/recover" component={RecoverPage} />
          <Route path="/shares" component={SharesPage} />
          <Route path="/self-test" component={SelfTestPage} />
          <Route component={NotFound} />
        </Switch>
      </RoutedErrorBoundary>
    </div>
  );
}

function RoutedErrorBoundary({ children }: { children: ReactNode }) {
  const [location] = useLocation();
  return <ErrorBoundary resetKey={location}>{children}</ErrorBoundary>;
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, '')}>
          <Router />
        </WouterRouter>
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default App;
