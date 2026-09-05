import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { GlobalFooter } from './GlobalFooter';

describe('footer global', () => {
  it('muestra el crédito de Territorio Electoral en español', () => {
    render(<GlobalFooter />);

    expect(screen.getByRole('contentinfo')).toHaveTextContent('Territorio Electoral');
    expect(screen.getByRole('contentinfo')).toHaveTextContent('Todos los derechos reservados');
    expect(screen.getByRole('contentinfo')).toHaveTextContent('Desarrollado por Xavier Tacuri');
    expect(screen.getByRole('contentinfo')).toHaveTextContent(String(new Date().getFullYear()));
  });
});
