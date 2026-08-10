import { useQuery } from '@tanstack/react-query';
import { apiRequest } from '../../api/client';
import { DataTable } from '../../components/tables/DataTable';
import { PageHeader } from '../../components/layout/PageHeader';
type Role = { id: number; code: string; name: string; description?: string; is_active: boolean };
export default function RolesPage() {
  const q = useQuery({
    queryKey: ['roles'],
    queryFn: () => apiRequest<Role[]>('/roles?include_inactive=true'),
  });
  return (
    <>
      <PageHeader
        title="Roles"
        description="Roles del sistema de solo lectura. Se asignan desde la edición de usuarios."
      />
      <DataTable
        label="roles"
        loading={q.isLoading}
        rows={(q.data || []).map((x) => ({ ...x, id: String(x.id) }))}
        columns={[
          { key: 'code', label: 'Código', render: (x) => x.code },
          { key: 'name', label: 'Nombre', render: (x) => x.name },
          { key: 'description', label: 'Descripción', render: (x) => x.description || '—' },
          { key: 'active', label: 'Estado', render: (x) => (x.is_active ? 'Activo' : 'Inactivo') },
        ]}
      />
    </>
  );
}
