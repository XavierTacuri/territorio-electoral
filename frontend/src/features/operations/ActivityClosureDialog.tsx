import { useEffect, useState } from 'react';
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, MenuItem, Stack, TextField } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { apiRequest } from '../../api/client';
import { queryClient } from '../../app/queryClient';
import type { Activity, Catalog, Need, Page } from './types';

type Props = { campaignId: string; activity: Activity | null; mode: 'complete' | 'suspend' | null; onClose: () => void; onSaved: () => void };
export function activityClosurePayload(input: { summary: string; outcomeNotes: string; existingNeedId: string; needTitle: string; needDescription: string; needCategory?: string }) {
  return { summary: input.summary.trim(), outcome_notes: input.outcomeNotes.trim() || null, existing_need_ids: input.existingNeedId ? [input.existingNeedId] : [], new_needs: input.needTitle.trim() ? [{ need_category_code: input.needCategory, title: input.needTitle.trim(), description: input.needDescription.trim() || null, scope: 'PARISH', source_type: 'CAMPAIGN_ACTIVITY' }] : [], commitments: [] };
}
export function ActivityClosureDialog({ campaignId, activity, mode, onClose, onSaved }: Props) {
  const [summary, setSummary] = useState('');
  const [outcomeNotes, setOutcomeNotes] = useState('');
  const [existingNeedId, setExistingNeedId] = useState('');
  const [needTitle, setNeedTitle] = useState('');
  const [needDescription, setNeedDescription] = useState('');
  const [needCategory, setNeedCategory] = useState('');
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const needs = useQuery({
    queryKey: ['activity-closure-needs', campaignId, activity?.id],
    queryFn: () => apiRequest<Page<Need>>(`/campaigns/${campaignId}/needs?parish_id=${activity?.parish_id}&page_size=100`),
    enabled: Boolean(activity && mode === 'complete'),
  });
  const categories = useQuery({ queryKey: ['need-categories'], queryFn: () => apiRequest<Catalog[]>('/need-categories'), enabled: Boolean(mode === 'complete') });
  useEffect(() => {
    if (mode) { setSummary(''); setOutcomeNotes(''); setExistingNeedId(''); setNeedTitle(''); setNeedDescription(''); setNeedCategory(''); setReason(''); setError(''); }
  }, [mode, activity?.id]);
  const submit = async () => {
    if (!activity) return;
    setError('');
    if (mode === 'complete' && summary.trim().length < 10) { setError('Ingresa un resumen de la actividad.'); return; }
    if (mode === 'suspend' && reason.trim().length < 3) { setError('Ingresa un motivo de suspensión.'); return; }
    setSaving(true);
    try {
      if (mode === 'complete') {
        await apiRequest(`/campaigns/${campaignId}/activities/${activity.id}/complete`, { method: 'POST', body: JSON.stringify(activityClosurePayload({ summary, outcomeNotes, existingNeedId, needTitle, needDescription, needCategory: needCategory || categories.data?.[0]?.code })) });
      } else await apiRequest(`/campaigns/${campaignId}/activities/${activity.id}/suspend`, { method: 'POST', body: JSON.stringify({ reason: reason.trim() }) });
      await queryClient.invalidateQueries({ queryKey: ['campaign', campaignId, 'activities'] });
      onSaved();
    } catch (e) { setError(e instanceof Error ? e.message : 'No se pudo guardar el cierre.'); } finally { setSaving(false); }
  };
  return <Dialog open={Boolean(mode)} onClose={() => { if (!saving) onClose(); }} fullWidth maxWidth="md">
    <DialogTitle>{mode === 'complete' ? 'Cerrar actividad' : 'Suspender actividad'}</DialogTitle>
    <DialogContent>
      {error && <Alert severity="error" sx={{ mt: 1 }}>{error}</Alert>}
      {mode === 'complete' ? <Stack spacing={2} sx={{ mt: 1 }}>
        <TextField required multiline minRows={3} label="Resumen de la actividad" value={summary} onChange={(e) => setSummary(e.target.value)} helperText="Describe qué ocurrió (mínimo 10 caracteres)." />
        <TextField multiline minRows={2} label="Resultados u observaciones" value={outcomeNotes} onChange={(e) => setOutcomeNotes(e.target.value)} />
        <TextField select label="Vincular necesidad existente (opcional)" value={existingNeedId} onChange={(e) => setExistingNeedId(e.target.value)}><MenuItem value="">No vincular</MenuItem>{needs.data?.items.map((need) => <MenuItem key={need.id} value={need.id}>{need.title}</MenuItem>)}</TextField>
        <TextField label="Necesidad detectada (opcional)" value={needTitle} onChange={(e) => setNeedTitle(e.target.value)} helperText="+ Agregar necesidad" />
        {needTitle && <><TextField select label="Categoría" value={needCategory || categories.data?.[0]?.code || ''} onChange={(e) => setNeedCategory(e.target.value)}>{categories.data?.map((x) => <MenuItem key={x.code} value={x.code}>{x.name}</MenuItem>)}</TextField><TextField multiline label="Descripción de la necesidad" value={needDescription} onChange={(e) => setNeedDescription(e.target.value)} /></>}
        <Alert severity="info">Las evidencias existentes se conservan y pueden agregarse desde la sección de evidencias.</Alert>
      </Stack> : <TextField autoFocus required fullWidth multiline minRows={3} sx={{ mt: 1 }} label="Motivo de suspensión" value={reason} onChange={(e) => setReason(e.target.value)} />}
    </DialogContent>
    <DialogActions><Button onClick={onClose} disabled={saving}>Cancelar</Button><Button variant="contained" color={mode === 'suspend' ? 'warning' : 'primary'} disabled={saving} onClick={submit}>{saving ? 'Guardando…' : mode === 'complete' ? 'Completar actividad' : 'Suspender actividad'}</Button></DialogActions>
  </Dialog>;
}
