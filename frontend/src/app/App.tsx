import { RouterProvider } from 'react-router-dom';
import { InstallPrompt } from '../pwa/InstallPrompt';
import { ServiceWorkerUpdateBanner } from '../pwa/ServiceWorkerUpdateBanner';
import { ErrorBoundary } from './ErrorBoundary';
import { router } from './router';
export default function App() {
  return (
    <ErrorBoundary>
      <RouterProvider router={router} />
      <ServiceWorkerUpdateBanner />
      <InstallPrompt />
    </ErrorBoundary>
  );
}
