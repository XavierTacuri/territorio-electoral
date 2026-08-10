import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { EmptyState, ErrorState } from './States';
describe('estados comunes', () => {
  it('muestra ausencia de datos', () => {
    render(<EmptyState />);
    expect(screen.getByRole('heading', { name: /no hay datos/i })).toBeInTheDocument();
  });
  it('anuncia errores', () => {
    render(<ErrorState />);
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });
});
