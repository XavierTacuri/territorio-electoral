import React from 'react';
import { ErrorPage } from '../pages/ErrorPages';
export class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { failed: boolean; error?: Error }
> {
  state: { failed: boolean; error?: Error } = { failed: false };
  static getDerivedStateFromError(error: Error) {
    return { failed: true, error };
  }
  render() {
    if (this.state.failed)
      return (
        <>
          <ErrorPage />
          {import.meta.env.DEV && <pre>{this.state.error?.stack}</pre>}
        </>
      );
    return this.props.children;
  }
}
