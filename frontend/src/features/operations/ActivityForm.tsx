import { zodResolver } from '@hookform/resolvers/zod';
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Grid,
  MenuItem,
  TextField,
} from '@mui/material';
import { useEffect, useState } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { z } from 'zod';
import { ApiError } from '../../api/errors';
import { todayDateOnly } from '../../lib/dates';
import { EXECUTION_STATUS_LABELS } from './statusLabels';
import type { Activity, Catalog, Parish } from './types';
import { parishOptionLabel } from '../../lib/territoryLabels';
// La hora es obligatoria para actividades NUEVAS (validado además aquí, no
// solo con el atributo required del input). Editar una actividad histórica
// creada antes de que el campo existiera no debe bloquearse por eso — p. ej.
// cambiar su estado a Completada/Suspendida no tiene por qué exigir rellenar
// un dato que nunca se pidió al crearla; ese caso se valida aparte, a mano,
// solo cuando corresponde (ver handleSubmit más abajo).
const schema = z.object({
  activity_type_code: z.string().min(1),
  title: z.string().trim().min(3).max(220),
  description: z.string().optional(),
  activity_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  start_time: z.string().regex(/^\d{2}:\d{2}$/, 'Hora inválida').or(z.literal('')),
  status: z.enum(['PLANNED', 'IN_PROGRESS', 'COMPLETED', 'SUSPENDED', 'CANCELLED']),
  parish_id: z.coerce.number().int().positive(),
});
export type ActivityFormValue = z.infer<typeof schema>;
// Lo que de verdad viaja a la API: una hora en blanco (actividad histórica
// sin editar ese campo) se envía como null, nunca como cadena vacía — la API
// espera time|None, no un string vacío.
export type ActivitySubmitValue = Omit<ActivityFormValue, 'start_time'> & {
  start_time: string | null;
};
export function activityStatusOptions(activity?: Activity | null) {
  if (!activity) return ['PLANNED'] as const;
  if (activity.status === 'PLANNED' && activity.approval_status === 'APPROVED')
    return ['PLANNED', 'COMPLETED', 'SUSPENDED'] as const;
  if (activity.status === 'SUSPENDED' && activity.approval_status === 'APPROVED')
    return ['SUSPENDED', 'PLANNED'] as const;
  return [activity.status];
}
export function ActivityForm({
  open,
  activity,
  types,
  parishes,
  onClose,
  onSubmit,
  submitLabel = 'Guardar',
}: {
  open: boolean;
  activity?: Activity | null;
  types: Catalog[];
  parishes: Parish[];
  onClose: () => void;
  onSubmit: (value: ActivitySubmitValue) => Promise<void>;
  submitLabel?: string;
}) {
  const statusOptions = activityStatusOptions(activity);
  const [serverError, setServerError] = useState('');
  const {
    control,
    register,
    reset,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<ActivityFormValue>({
    resolver: zodResolver(schema),
    defaultValues: {
      activity_type_code: '',
      title: '',
      description: '',
      activity_date: todayDateOnly(),
      start_time: '',
      status: 'PLANNED',
      parish_id: 0,
    },
  });
  useEffect(() => {
    if (open)
      reset(
        activity
          ? {
              activity_type_code: types.find((x) => x.id === activity.activity_type_id)?.code ?? '',
              title: activity.title,
              description: activity.description ?? '',
              activity_date: activity.activity_date,
              start_time: activity.start_time?.slice(0, 5) ?? '',
              status: activity.status as ActivityFormValue['status'],
              parish_id: activity.parish_id,
            }
          : {
              activity_type_code: types[0]?.code ?? '',
              title: '',
              description: '',
              activity_date: todayDateOnly(),
              start_time: '',
              status: 'PLANNED',
              parish_id: parishes[0]?.id ?? 0,
            },
      );
    setServerError('');
  }, [open, activity, types, parishes, reset]);
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>{activity ? 'Editar actividad' : 'Crear actividad'}</DialogTitle>
      <DialogContent>
        {serverError && (
          <Alert severity="error" sx={{ my: 1 }}>
            {serverError}
          </Alert>
        )}
        <Grid container spacing={2} sx={{ mt: 0 }}>
          <Grid size={{ xs: 12, sm: 6 }}>
            <Controller
              name="activity_type_code"
              control={control}
              render={({ field }) => (
                <TextField
                  {...field}
                  select
                  fullWidth
                  label="Tipo"
                  error={!!errors.activity_type_code}
                >
                  {types.map((x) => (
                    <MenuItem key={x.id} value={x.code}>
                      {parishOptionLabel(x, parishes)}
                    </MenuItem>
                  ))}
                </TextField>
              )}
            />
          </Grid>
          <Grid size={{ xs: 12, sm: 6 }}>
            <Controller
              name="status"
              control={control}
              render={({ field }) => (
                <TextField {...field} select fullWidth label="Estado">
                  {statusOptions.map((value) => (
                    <MenuItem key={value} value={value}>
                      {EXECUTION_STATUS_LABELS[value as keyof typeof EXECUTION_STATUS_LABELS]}
                    </MenuItem>
                  ))}
                </TextField>
              )}
            />
          </Grid>
          <Grid size={{ xs: 12 }}>
            <TextField
              {...register('title')}
              fullWidth
              label="Título"
              error={!!errors.title}
              helperText={errors.title?.message}
            />
          </Grid>
          <Grid size={{ xs: 12 }}>
            <TextField
              {...register('description')}
              fullWidth
              multiline
              minRows={3}
              label="Descripción"
            />
          </Grid>
          <Grid size={{ xs: 12, sm: 6 }}>
            <TextField
              {...register('activity_date')}
              fullWidth
              type="date"
              label="Fecha"
              InputLabelProps={{ shrink: true }}
              error={!!errors.activity_date}
            />
          </Grid>
          <Grid size={{ xs: 12, sm: 6 }}>
            <TextField
              {...register('start_time')}
              fullWidth
              type="time"
              label="Hora"
              InputLabelProps={{ shrink: true }}
              error={!!errors.start_time}
              helperText={errors.start_time?.message}
            />
          </Grid>
          <Grid size={{ xs: 12 }}>
            <Controller
              name="parish_id"
              control={control}
              render={({ field }) => (
                <TextField {...field} select fullWidth label="Lugar / Parroquia">
                  {parishes.map((x) => (
                    <MenuItem key={x.id} value={x.id}>
                      {x.name}
                    </MenuItem>
                  ))}
                </TextField>
              )}
            />
          </Grid>
        </Grid>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancelar</Button>
        <Button
          variant="contained"
          disabled={isSubmitting}
          onClick={handleSubmit(async (value) => {
            if (!activity && !value.start_time) {
              setError('start_time', { type: 'manual', message: 'Hora requerida' });
              return;
            }
            try {
              await onSubmit({ ...value, start_time: value.start_time || null });
              onClose();
            } catch (error) {
              setServerError(
                error instanceof ApiError ? error.message : 'No se pudo guardar la actividad.',
              );
            }
          })}
        >
          {isSubmitting ? 'Guardando…' : submitLabel}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
