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
import type { Activity, Catalog, Parish } from './types';
const schema = z
  .object({
    activity_type_code: z.string().min(1),
    title: z.string().trim().min(3).max(220),
    description: z.string().optional(),
    activity_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
    status: z.enum(['PLANNED', 'COMPLETED', 'CANCELLED']),
    parish_id: z.coerce.number().int().positive(),
    location_name: z.string().optional(),
    latitude: z.union([z.coerce.number().min(-90).max(90), z.literal('')]).optional(),
    longitude: z.union([z.coerce.number().min(-180).max(180), z.literal('')]).optional(),
  })
  .refine((x) => (x.latitude === '') === (x.longitude === ''), {
    message: 'Latitud y longitud deben enviarse juntas',
    path: ['latitude'],
  });
export type ActivityFormValue = z.infer<typeof schema>;
export function ActivityForm({
  open,
  activity,
  types,
  parishes,
  onClose,
  onSubmit,
}: {
  open: boolean;
  activity?: Activity | null;
  types: Catalog[];
  parishes: Parish[];
  onClose: () => void;
  onSubmit: (value: ActivityFormValue) => Promise<void>;
}) {
  const [serverError, setServerError] = useState('');
  const {
    control,
    register,
    reset,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ActivityFormValue>({
    resolver: zodResolver(schema),
    defaultValues: {
      activity_type_code: '',
      title: '',
      description: '',
      activity_date: todayDateOnly(),
      status: 'PLANNED',
      parish_id: 0,
      location_name: '',
      latitude: '',
      longitude: '',
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
              status: activity.status as ActivityFormValue['status'],
              parish_id: activity.parish_id,
              location_name: activity.location_name ?? '',
              latitude: activity.latitude ?? '',
              longitude: activity.longitude ?? '',
            }
          : {
              activity_type_code: types[0]?.code ?? '',
              title: '',
              description: '',
              activity_date: todayDateOnly(),
              status: 'PLANNED',
              parish_id: parishes[0]?.id ?? 0,
              location_name: '',
              latitude: '',
              longitude: '',
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
                      {x.name}
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
                  {['PLANNED', 'COMPLETED', 'CANCELLED'].map((x) => (
                    <MenuItem key={x} value={x}>
                      {x}
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
            <Controller
              name="parish_id"
              control={control}
              render={({ field }) => (
                <TextField {...field} select fullWidth label="Parroquia">
                  {parishes.map((x) => (
                    <MenuItem key={x.id} value={x.id}>
                      {x.name}
                    </MenuItem>
                  ))}
                </TextField>
              )}
            />
          </Grid>
          <Grid size={{ xs: 12 }}>
            <TextField
              {...register('location_name')}
              fullWidth
              label="Nombre de ubicación (opcional)"
            />
          </Grid>
          <Grid size={{ xs: 6 }}>
            <TextField
              {...register('latitude')}
              fullWidth
              type="number"
              label="Latitud"
              error={!!errors.latitude}
              helperText={errors.latitude?.message}
            />
          </Grid>
          <Grid size={{ xs: 6 }}>
            <TextField {...register('longitude')} fullWidth type="number" label="Longitud" />
          </Grid>
        </Grid>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancelar</Button>
        <Button
          variant="contained"
          disabled={isSubmitting}
          onClick={handleSubmit(async (value) => {
            try {
              await onSubmit(value);
              onClose();
            } catch (error) {
              setServerError(
                error instanceof ApiError ? error.message : 'No se pudo guardar la actividad.',
              );
            }
          })}
        >
          {isSubmitting ? 'Guardando…' : 'Guardar'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
