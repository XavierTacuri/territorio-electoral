import { Alert, Button, MenuItem, Paper, Stack, TextField, Typography } from '@mui/material';
import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { organizationError } from './errors';
import type { Organization } from './types';
import { organizationStatusLabels } from '../../lib/labels';

const initial = {
  name: '',
  legal_name: '',
  slug: '',
  contact_email: '',
  contact_phone: '',
  country: 'EC',
  timezone: 'America/Guayaquil',
  status: 'ACTIVE',
};
export default function OrganizationCreatePage() {
  const [form, setForm] = useState(initial);
  const [error, setError] = useState('');
  const navigate = useNavigate();
  const save = useMutation({
    mutationFn: () =>
      apiRequest<Organization>('/organizations', {
        method: 'POST',
        body: JSON.stringify({
          ...form,
          legal_name: form.legal_name || null,
          contact_email: form.contact_email || null,
          contact_phone: form.contact_phone || null,
        }),
      }),
    onSuccess: (organization) => navigate(`/app/admin/organizations/${organization.id}`),
    onError: (reason) => setError(organizationError(reason)),
  });
  const field = (key: keyof typeof initial) => ({
    value: form[key],
    onChange: (event: React.ChangeEvent<HTMLInputElement>) =>
      setForm({ ...form, [key]: event.target.value }),
  });
  return (
    <Stack spacing={3} maxWidth={760}>
      <Stack>
        <Typography variant="h4">Nueva organización</Typography>
        <Typography color="text.secondary">
          Crea la organización cliente. El plan y la campaña pueden configurarse después.
        </Typography>
      </Stack>
      {error && <Alert severity="error">{error}</Alert>}
      <Paper
        component="form"
        sx={{ p: 3 }}
        onSubmit={(event) => {
          event.preventDefault();
          save.mutate();
        }}
      >
        <Stack spacing={2}>
          <TextField required label="Nombre" {...field('name')} />
          <TextField label="Nombre legal" {...field('legal_name')} />
          <TextField
            required
            label="Slug"
            inputProps={{ pattern: '[a-z0-9-]+' }}
            {...field('slug')}
          />
          <TextField type="email" label="Email de contacto" {...field('contact_email')} />
          <TextField label="Teléfono" {...field('contact_phone')} />
          <Stack direction={{ xs: 'column', sm: 'row' }} gap={2}>
            <TextField required label="País" {...field('country')} />
            <TextField required label="Zona horaria" {...field('timezone')} />
            <TextField select label="Estado inicial" {...field('status')}>
              {Object.entries(organizationStatusLabels).map(([value, label]) => (
                <MenuItem key={value} value={value}>
                  {label}
                </MenuItem>
              ))}
            </TextField>
          </Stack>
          <Stack direction="row" justifyContent="flex-end" gap={1}>
            <Button onClick={() => navigate(-1)}>Cancelar</Button>
            <Button type="submit" variant="contained" disabled={save.isPending}>
              Crear organización
            </Button>
          </Stack>
        </Stack>
      </Paper>
    </Stack>
  );
}
