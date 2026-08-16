import { createRoot } from 'react-dom/client';

import App from './App';
import { ErrorBoundary } from '@/components/error-boundary';

import './index.css';

createRoot(document.getElementById('root')!, {
  // Keeps caught errors off reportError(), which would raise the dev overlay.
  onCaughtError: (error, errorInfo) => {
    // Generic diagnostic only: never log the error object itself — a caught
    // error's message/state could contain secret material (seeds, keys,
    // tokens). Log the error type and component stack, which cannot.
    console.error(
      'Caught render error:',
      error instanceof Error ? error.name : typeof error,
      errorInfo.componentStack,
    );
  },
}).render(
  <ErrorBoundary>
    <App />
  </ErrorBoundary>,
);
