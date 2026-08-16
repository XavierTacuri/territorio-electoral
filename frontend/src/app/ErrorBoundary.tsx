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
  private retry = () => this.setState({ failed: false, error: undefined });
  render() {
    if (this.state.failed)
      return (
        <>
          <ErrorPage message="No pudimos cargar esta sección." />
          <div style={{ display: 'flex', justifyContent: 'center', gap: 12 }}>
            <button type="button" onClick={this.retry}>
              Reintentar
            </button>
            <a href="/app">Volver al inicio</a>
          </div>
          {import.meta.env.DEV && <pre>{this.state.error?.stack}</pre>}
        </>
      );
    return this.props.children;
  }
}
