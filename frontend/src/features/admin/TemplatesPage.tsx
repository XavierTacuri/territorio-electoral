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
} from '@mui/material';
import { useForm } from 'react-hook-form';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiRequest } from '../../api/client';
import { DataTable } from '../../components/tables/DataTable';
import { PageHeader } from '../../components/layout/PageHeader';
const SECTIONS = [
  'COVER',
  'EXECUTIVE_METRICS',
  'TERRITORIAL_COVERAGE',
  'ACTIVITY_SUMMARY',
  'TOP_NEEDS',
  'COMMITMENTS',
  'SURVEYS',
  'ELECTORAL_HISTORY',
  'DEMOGRAPHICS',
  'DATA_QUALITY',
  'SOURCES',
];
type T = {
  id: string;
  code: string;
  name: string;
  description?: string;
  report_type: string;
  allowed_formats: string[];
  definition: { sections: string[] };
  is_system: boolean;
  is_active: boolean;
};
export default function TemplatesPage() {
  const qc = useQueryClient();
  const [edit, setEdit] = useState<T | null>(null);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState('');
  const q = useQuery({
    queryKey: ['report-templates'],
    queryFn: () => apiRequest<T[]>('/report-templates?include_inactive=true'),
  });
  const f = useForm<any>({
    defaultValues: {
      code: '',
      name: '',
      description: '',
      report_type: 'CAMPAIGN_EXECUTIVE_SUMMARY',
      allowed_formats: ['PDF'],
      sections: ['COVER', 'EXECUTIVE_METRICS'],
      is_active: true,
    },
  });
  const show = (x?: T) => {
    setEdit(x || null);
    setError('');
    f.reset(
      x
        ? { ...x, sections: x.definition.sections }
        : {
            code: '',
            name: '',
            description: '',
            report_type: 'CAMPAIGN_EXECUTIVE_SUMMARY',
            allowed_formats: ['PDF'],
            sections: ['COVER', 'EXECUTIVE_METRICS'],
            is_active: true,
          },
    );
    setOpen(true);
  };
  const save = useMutation({
    mutationFn: (v: any) =>
      apiRequest(edit ? `/report-templates/${edit.id}` : '/report-templates', {
        method: edit ? 'PATCH' : 'POST',
        body: JSON.stringify({
          ...(!edit && { code: v.code, report_type: v.report_type }),
          name: v.name,
          description: v.description || null,
          allowed_formats: v.allowed_formats,
          definition: {
            sections: v.sections,
            include_comparisons: true,
            include_methodology: true,
            include_sources: true,
            max_items_per_section: 50,
          },
          ...(edit && { is_active: v.is_active }),
        }),
      }),
    onSuccess: () => {
      setOpen(false);
      qc.invalidateQueries({ queryKey: ['report-templates'] });
    },
    onError: () => setError('Definición inválida. Use únicamente secciones y formatos permitidos.'),
  });
  return (
    <>
      <PageHeader
        title="Plantillas de informe"
        description="Definiciones controladas; no se acepta contenido arbitrario."
        action={
          <Button variant="contained" onClick={() => show()}>
            Crear plantilla
          </Button>
        }
      />
      <DataTable
        label="plantillas"
        loading={q.isLoading}
        rows={q.data || []}
        columns={[
          { key: 'code', label: 'Código', render: (x) => x.code },
          { key: 'name', label: 'Nombre', render: (x) => x.name },
          { key: 'formats', label: 'Formatos', render: (x) => x.allowed_formats.join(', ') },
          {
            key: 'sections',
            label: 'Secciones',
            render: (x) => String(x.definition.sections.length),
          },
          {
            key: 'system',
            label: 'Tipo',
            render: (x) => (x.is_system ? 'Sistema' : 'Personalizada'),
          },
        ]}
        onEdit={show}
      />
      <Dialog open={open} onClose={() => setOpen(false)} fullWidth>
        <DialogTitle>{edit ? 'Editar plantilla' : 'Crear plantilla'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            {error && <Alert severity="error">{error}</Alert>}
            <TextField
              label="Código"
              disabled={!!edit}
              {...f.register('code', { required: !edit })}
            />
            <TextField label="Nombre" {...f.register('name', { required: true })} />
            <TextField label="Descripción" multiline {...f.register('description')} />
            {!edit && (
              <TextField
                label="Tipo de informe"
                {...f.register('report_type', { required: true })}
              />
            )}
            <TextField
              select
              label="Formatos"
              SelectProps={{ multiple: true }}
              value={f.watch('allowed_formats')}
              onChange={(e) =>
                f.setValue(
                  'allowed_formats',
                  typeof e.target.value === 'string' ? e.target.value.split(',') : e.target.value,
                )
              }
            >
              {['PDF', 'XLSX'].map((x) => (
                <MenuItem key={x} value={x}>
                  <Checkbox checked={f.watch('allowed_formats').includes(x)} />
                  {x}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Secciones"
              SelectProps={{ multiple: true }}
              value={f.watch('sections')}
              onChange={(e) =>
                f.setValue(
                  'sections',
                  typeof e.target.value === 'string' ? e.target.value.split(',') : e.target.value,
                )
              }
            >
              {SECTIONS.map((x) => (
                <MenuItem key={x} value={x}>
                  <Checkbox checked={f.watch('sections').includes(x)} />
                  {x}
                </MenuItem>
              ))}
            </TextField>
            {edit && (
              <FormControlLabel
                control={
                  <Checkbox
                    checked={f.watch('is_active')}
                    disabled={edit.is_system}
                    onChange={(e) => f.setValue('is_active', e.target.checked)}
                  />
                }
                label="Plantilla activa"
              />
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancelar</Button>
          <Button variant="contained" onClick={f.handleSubmit((v) => save.mutate(v))}>
            Guardar
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
