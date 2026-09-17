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
  myJornadaVisible?: boolean,
) =>
  buildNavigation(user(...roles), organizationRole, 'campaign-1', myJornadaVisible).flatMap(
    (group) => group.items.map((item) => item.label),
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

  it('prioriza análisis para ANALYST', () => {
    expect(labels(['ANALYST'])).toEqual(
      expect.arrayContaining([
        'Panorama electoral',
        'Fuentes públicas',
        'Datos electorales',
        'Centro de Informes',
      ]),
    );
  });

  it('muestra el menú reducido para TERRITORIAL_COORDINATOR', () => {
    const result = labels(['TERRITORIAL_COORDINATOR']);
    expect(result).toEqual([
      'Dashboard',
      'Panorama electoral',
      'Inteligencia territorial',
      'Calendario de campaña',
      'Operación territorial',
      'Actividades',
      'Necesidades',
      'Jornada Electoral',
    ]);
    expect(result).not.toEqual(
      expect.arrayContaining([
        'Encuestas y estudios',
        'Territorio IA · PRO',
        'Centro de Informes',
        'Centro de alertas',
        'Preparación para debate',
        'Seguimientos',
        'Operación de campo',
      ]),
    );
  });

  it('muestra Mi Jornada para TERRITORIAL_COORDINATOR solo cuando hay jornada activa y asignación', () => {
    const withoutAssignment = labels(['TERRITORIAL_COORDINATOR'], 'MEMBER', false);
    expect(withoutAssignment).not.toContain('Mi Jornada');
    const withAssignment = labels(['TERRITORIAL_COORDINATOR'], 'MEMBER', true);
    expect(withAssignment).toContain('Mi Jornada');
  });

  it('un superusuario con rol TERRITORIAL_COORDINATOR conserva la navegación de administrador, no la reducida de coordinador', () => {
    const superuser: SessionUser = {
      id: 'user-2',
      username: 'admin_e2e',
      email: 'admin@example.test',
      first_name: 'Admin',
      last_name: 'E2E',
      is_active: true,
      is_superuser: true,
      roles: [{ code: 'TERRITORIAL_COORDINATOR', name: 'TERRITORIAL_COORDINATOR' }],
    };
    const result = buildNavigation(superuser, null, 'campaign-1').flatMap((group) =>
      group.items.map((item) => item.label),
    );
    expect(result).toContain('Centro de Informes');
    expect(result).toContain('Datos electorales');
  });

  it('un usuario con roles CANDIDATE y TERRITORIAL_COORDINATOR a la vez conserva el menú ejecutivo', () => {
    const result = labels(['CANDIDATE', 'TERRITORIAL_COORDINATOR']);
    expect(result).toContain('Centro de Informes');
    expect(result).toContain('Encuestas y estudios');
  });
});
