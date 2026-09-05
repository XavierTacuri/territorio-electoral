import { describe, expect, it } from 'vitest';
import type { SessionUser } from '../auth/permissions';
import { buildNavigation } from './navigation';

const user = (...roles: string[]): SessionUser => ({
  id: 'user-1',
  username: 'usuario',
  email: 'user@example.test',
  first_name: 'Usuario',
  last_name: 'Prueba',
  is_active: true,
  is_superuser: false,
  roles: roles.map((code) => ({ code, name: code })),
});
const labels = (
  roles: string[],
  organizationRole: 'OWNER' | 'ADMIN' | 'MEMBER' | null = 'MEMBER',
) =>
  buildNavigation(user(...roles), organizationRole, 'campaign-1').flatMap((group) =>
    group.items.map((item) => item.label),
  );

describe('navegación por capacidades', () => {
  it('muestra el menú reducido para CANDIDATE', () => {
    const result = labels(['CANDIDATE']);
    expect(result).toEqual([
      'Dashboard',
      'Panorama electoral',
      'Inteligencia territorial',
      'Encuestas y estudios',
      'Territorio IA · PRO',
      'Calendario de campaña',
      'Centro de Informes',
      'Centro de alertas',
      'Preparación para debate',
      'Jornada Electoral',
      'Operación territorial',
      'Actividades',
      'Necesidades',
    ]);
    expect(result).not.toEqual(
      expect.arrayContaining([
        'Campañas',
        'Mi organización',
        'Datos electorales',
        'Demografía',
        'Mapas',
      ]),
    );
  });

  it('combina capacidades para CANDIDATE y CAMPAIGN_MANAGER', () => {
    const candidate = labels(['CANDIDATE']);
    const manager = labels(['CAMPAIGN_MANAGER']);
    expect(manager).toEqual(candidate);
    expect(manager).not.toEqual(expect.arrayContaining(['Campañas', 'Mi organización']));
  });

  it('muestra Mi organización a Organization ADMIN sin administración de plataforma', () => {
    const result = labels(['CANDIDATE'], 'ADMIN');
    expect(result).toContain('Mi organización');
    expect(result).not.toContain('Usuarios');
    expect(result).not.toContain('Organizaciones');
  });

  it('mantiene la navegación completa para Platform Admin', () => {
    const result = labels(['ADMIN'], null);
    expect(result).toEqual(
      expect.arrayContaining([
        'Campañas',
        'Mi organización',
        'Organizaciones',
        'Usuarios',
        'Asignaciones',
        'Datos electorales',
        'Demografía',
        'Mapas',
        'Auditoría',
        'Configuración de IA',
      ]),
    );
  });

  it('prioriza análisis para ANALYST y operación territorial para coordinación', () => {
    expect(labels(['ANALYST'])).toEqual(
      expect.arrayContaining([
        'Panorama electoral',
        'Fuentes públicas',
        'Datos electorales',
        'Centro de Informes',
      ]),
    );
    expect(labels(['TERRITORIAL_COORDINATOR'])).toEqual(
      expect.arrayContaining(['Dashboard', 'Operación territorial', 'Actividades', 'Necesidades']),
    );
  });
});
