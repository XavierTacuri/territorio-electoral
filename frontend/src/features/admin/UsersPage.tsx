import { useState } from 'react';
import {
  Alert,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { apiRequest } from '../../api/client';
import { DataTable } from '../../components/tables/DataTable';
import { PageHeader } from '../../components/layout/PageHeader';
type Role = { code: string; name: string };
type User = {
  id: string;
  email: string;
  username: string;
  first_name: string;
  last_name: string;
  is_active: boolean;
  roles: Role[];
};
type Form = {
  email: string;
  username: string;
  first_name: string;
  last_name: string;
  password: string;
  role_codes: string[];
  is_active: boolean;
};
export default function UsersPage() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<User | null>(null);
  const [error, setError] = useState('');
  const users = useQuery({
    queryKey: ['admin-users'],
    queryFn: () => apiRequest<{ items: User[] }>('/users?page=1&page_size=100'),
  });
  const roles = useQuery({ queryKey: ['roles'], queryFn: () => apiRequest<Role[]>('/roles') });
  const form = useForm<Form>({
    defaultValues: {
      email: '',
      username: '',
      first_name: '',
      last_name: '',
      password: '',
      role_codes: ['CANDIDATE'],
      is_active: true,
    },
  });
  const save = useMutation({
    mutationFn: (v: Form) =>
      apiRequest<User>(editing ? `/users/${editing.id}` : '/users', {
        method: editing ? 'PATCH' : 'POST',
        body: JSON.stringify(
          editing
            ? {
                email: v.email,
                username: v.username,
                first_name: v.first_name,
                last_name: v.last_name,
                is_active: v.is_active,
                role_codes: v.role_codes,
              }
            : v,
        ),
      }),
    onSuccess: () => {
      setOpen(false);
      qc.invalidateQueries({ queryKey: ['admin-users'] });
    },
    onError: () => setError('No se pudo guardar el usuario. Revise los campos y permisos.'),
  });
  const show = (u?: User) => {
    setEditing(u || null);
    setError('');
    form.reset(
      u
        ? { ...u, password: '', role_codes: u.roles.map((r) => r.code) }
        : {
            email: '',
            username: '',
            first_name: '',
            last_name: '',
            password: '',
            role_codes: ['CANDIDATE'],
            is_active: true,
          },
    );
    setOpen(true);
  };
  return (
    <>
      <PageHeader
        title="Usuarios"
        description="Usuarios, roles y estado de acceso; nunca se muestran hashes ni sesiones sensibles."
        action={
          <Button variant="contained" onClick={() => show()}>
            Crear usuario
          </Button>
        }
      />
      <DataTable
        label="usuarios"
        loading={users.isLoading}
        rows={users.data?.items || []}
        columns={[
          { key: 'username', label: 'Usuario', render: (x) => x.username },
          { key: 'name', label: 'Nombre', render: (x) => `${x.first_name} ${x.last_name}` },
          { key: 'roles', label: 'Roles', render: (x) => x.roles.map((r) => r.name).join(', ') },
          { key: 'status', label: 'Estado', render: (x) => (x.is_active ? 'Activo' : 'Inactivo') },
        ]}
        onEdit={show}
      />
      <Dialog open={open} onClose={() => setOpen(false)} fullWidth>
        <DialogTitle>{editing ? 'Editar usuario' : 'Crear usuario'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            {error && <Alert severity="error">{error}</Alert>}
            <TextField label="Correo" {...form.register('email', { required: true })} />
            <TextField label="Usuario" {...form.register('username', { required: true })} />
            <TextField label="Nombres" {...form.register('first_name', { required: true })} />
            <TextField label="Apellidos" {...form.register('last_name', { required: true })} />
            {!editing && (
              <TextField
                label="Contraseña temporal"
                type="password"
                {...form.register('password', { required: true })}
              />
            )}
            <TextField
              select
              label="Roles"
              SelectProps={{ multiple: true }}
              value={form.watch('role_codes')}
              onChange={(e) =>
                form.setValue(
                  'role_codes',
                  typeof e.target.value === 'string' ? e.target.value.split(',') : e.target.value,
                )
              }
            >
              {roles.data?.map((r) => (
                <MenuItem key={r.code} value={r.code}>
                  <Checkbox checked={form.watch('role_codes').includes(r.code)} />
                  {r.name}
                </MenuItem>
              ))}
            </TextField>
            <FormControlLabel
              control={
                <Checkbox
                  checked={form.watch('is_active')}
                  onChange={(e) => form.setValue('is_active', e.target.checked)}
                />
              }
              label="Usuario activo"
            />
            {editing && !form.watch('is_active') && (
              <Typography color="warning.main">
                Al desactivar se invalidan las sesiones según la política backend.
              </Typography>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancelar</Button>
          <Button
            variant="contained"
            disabled={save.isPending}
            onClick={form.handleSubmit((v) => save.mutate(v))}
          >
            Guardar
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
