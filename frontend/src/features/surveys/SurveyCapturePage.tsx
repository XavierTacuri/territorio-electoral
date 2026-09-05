import { useState } from 'react';
import {
  Alert,
  Button,
  Checkbox,
  FormControl,
  FormControlLabel,
  FormGroup,
  FormLabel,
  MenuItem,
  Paper,
  Radio,
  RadioGroup,
  Slider,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { Controller, useForm } from 'react-hook-form';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { useCampaign } from '../../app/CampaignProvider';
import { ErrorState, LoadingSkeleton } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import { todayDateOnly } from '../../lib/dates';
import { parishOptionLabel, type ParishOption } from '../../lib/territoryLabels';
import type { Question, Survey } from './types';
type Values = {
  response_date: string;
  parish_id: number;
  source_channel: string;
  age_range: string;
  answers: Record<string, unknown>;
};
type AnswerPayload = {
  question_code: string;
  text_value: string | null;
  integer_value: number | null;
  decimal_value: number | null;
  boolean_value: boolean | null;
  rating_value: number | null;
  selected_option_codes: string[];
  other_text: string | null;
};
const submissionKey = () => {
  const bytes = new Uint8Array(24);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (x) => x.toString(16).padStart(2, '0')).join('');
};
export default function SurveyCapturePage() {
  const { campaignId = '', surveyId = '' } = useParams();
  const { active } = useCampaign();
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState('');
  const survey = useQuery({
    queryKey: ['campaign', campaignId, 'survey', surveyId],
    queryFn: () => apiRequest<Survey>('/campaigns/' + campaignId + '/surveys/' + surveyId),
  });
  const parishes = useQuery({
    queryKey: ['parishes', active?.canton_id],
    queryFn: () =>
      apiRequest<ParishOption[]>('/parishes?canton_id=' + active!.canton_id),
    enabled: Boolean(active?.canton_id),
  });
  const {
    control,
    register,
    handleSubmit,
    reset,
    formState: { isSubmitting },
  } = useForm<Values>({
    defaultValues: {
      response_date: todayDateOnly(),
      parish_id: 0,
      source_channel: 'FIELD',
      age_range: 'NOT_PROVIDED',
      answers: {},
    },
  });
  const submit = useMutation({
    mutationFn: (body: unknown) =>
      apiRequest('/campaigns/' + campaignId + '/surveys/' + surveyId + '/responses', {
        method: 'POST',
        body: JSON.stringify(body),
      }),
  });
  if (survey.isLoading) return <LoadingSkeleton />;
  if (survey.isError || !survey.data) return <ErrorState retry={() => survey.refetch()} />;
  const item = survey.data;
  const questions = item.sections?.flatMap((x) => x.questions) ?? [];
  const answer = (q: Question, value: unknown): AnswerPayload => {
    const base: AnswerPayload = {
      question_code: q.code,
      text_value: null,
      integer_value: null,
      decimal_value: null,
      boolean_value: null,
      rating_value: null,
      selected_option_codes: [],
      other_text: null,
    };
    if (['SHORT_TEXT', 'LONG_TEXT'].includes(q.question_type))
      base.text_value = String(value || '');
    else if (q.question_type === 'INTEGER')
      base.integer_value = value === '' ? null : Number(value);
    else if (q.question_type === 'DECIMAL')
      base.decimal_value = value === '' ? null : Number(value);
    else if (q.question_type === 'YES_NO') base.boolean_value = value === 'true';
    else if (q.question_type === 'RATING') base.rating_value = Number(value);
    else base.selected_option_codes = Array.isArray(value) ? value : [String(value)];
    return base;
  };
  return (
    <>
      <PageHeader
        title={'Captura: ' + item.title}
        description="Formulario anónimo: no solicite nombre, cédula, teléfono ni correo."
      />
      {item.status !== 'PUBLISHED' && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          La encuesta no está publicada. La vista sirve como previsualización y no permite enviar.
        </Alert>
      )}
      {success && (
        <Alert severity="success" sx={{ mb: 2 }}>
          Respuesta anónima registrada correctamente.
        </Alert>
      )}
      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}
      <Paper
        component="form"
        variant="outlined"
        sx={{ p: { xs: 2, md: 3 } }}
        onSubmit={handleSubmit(async (v) => {
          setError('');
          const answers = questions
            .map((q) => answer(q, v.answers[q.code]))
            .filter(
              (x) =>
                x.text_value !== '' ||
                x.integer_value !== null ||
                x.decimal_value !== null ||
                x.rating_value !== null ||
                x.boolean_value !== null ||
                x.selected_option_codes.length,
            );
          try {
            await submit.mutateAsync({
              response_date: v.response_date,
              parish_id: Number(v.parish_id),
              community_id: null,
              sector_id: null,
              activity_id: null,
              source_channel: v.source_channel,
              age_range: v.age_range || null,
              submission_key: submissionKey(),
              answers,
            });
            setSuccess(true);
            reset({ ...v, answers: {} });
          } catch {
            setError('No se pudo registrar. Revise las respuestas o un posible envío duplicado.');
          }
        })}
      >
        <Stack spacing={3}>
          <Alert severity="info">
            Las respuestas no se guardan en este navegador y solo se consultan de forma agregada.
          </Alert>
          <TextField
            type="date"
            label="Fecha de respuesta"
            InputLabelProps={{ shrink: true }}
            {...register('response_date', { required: true })}
          />
          <Controller
            name="parish_id"
            control={control}
            render={({ field }) => (
              <TextField {...field} select label="Parroquia" required>
                {parishes.data?.map((x) => (
                  <MenuItem key={x.id} value={x.id}>
                    {parishOptionLabel(x, parishes.data ?? [])}
                  </MenuItem>
                ))}
              </TextField>
            )}
          />
          <TextField select label="Canal" defaultValue="FIELD" {...register('source_channel')}>
            {['FIELD', 'WEB', 'QR', 'ACTIVITY', 'MANUAL_IMPORT', 'OTHER'].map((x) => (
              <MenuItem key={x} value={x}>
                {x}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            select
            label="Rango de edad (opcional)"
            defaultValue="NOT_PROVIDED"
            {...register('age_range')}
          >
            {[
              'NOT_PROVIDED',
              'UNDER_18',
              'AGE_18_24',
              'AGE_25_34',
              'AGE_35_44',
              'AGE_45_54',
              'AGE_55_64',
              'AGE_65_PLUS',
            ].map((x) => (
              <MenuItem key={x} value={x}>
                {x}
              </MenuItem>
            ))}
          </TextField>
          {item.sections?.map((section) => (
            <Stack key={section.id} spacing={2}>
              <Typography variant="h2">{section.title}</Typography>
              {section.questions.map((q) => (
                <Controller
                  key={q.id}
                  name={('answers.' + q.code) as any}
                  control={control}
                  rules={{ required: q.is_required }}
                  render={({ field, fieldState }) => (
                    <FormControl error={!!fieldState.error} required={q.is_required}>
                      <FormLabel>{q.question_text}</FormLabel>
                      {q.help_text && <Typography variant="caption">{q.help_text}</Typography>}
                      {q.question_type === 'SINGLE_CHOICE' && (
                        <RadioGroup value={field.value ?? ''} onChange={field.onChange}>
                          {q.options.map((o) => (
                            <FormControlLabel
                              key={o.id}
                              value={o.code}
                              control={<Radio />}
                              label={o.label}
                            />
                          ))}
                        </RadioGroup>
                      )}
                      {q.question_type === 'MULTIPLE_CHOICE' && (
                        <FormGroup>
                          {q.options.map((o) => (
                            <FormControlLabel
                              key={o.id}
                              label={o.label}
                              control={
                                <Checkbox
                                  checked={
                                    Array.isArray(field.value) && field.value.includes(o.code)
                                  }
                                  onChange={(e) => {
                                    const current = Array.isArray(field.value)
                                      ? (field.value as string[])
                                      : [];
                                    field.onChange(
                                      e.target.checked
                                        ? [...current, o.code]
                                        : current.filter((x) => x !== o.code),
                                    );
                                  }}
                                />
                              }
                            />
                          ))}
                        </FormGroup>
                      )}
                      {q.question_type === 'YES_NO' && (
                        <RadioGroup value={field.value ?? ''} onChange={field.onChange}>
                          <FormControlLabel value="true" control={<Radio />} label="Sí" />
                          <FormControlLabel value="false" control={<Radio />} label="No" />
                        </RadioGroup>
                      )}
                      {['SHORT_TEXT', 'LONG_TEXT'].includes(q.question_type) && (
                        <TextField
                          value={field.value ?? ''}
                          onChange={field.onChange}
                          multiline={q.question_type === 'LONG_TEXT'}
                          minRows={q.question_type === 'LONG_TEXT' ? 4 : 1}
                          inputProps={{
                            minLength: q.min_length ?? undefined,
                            maxLength: q.max_length ?? undefined,
                          }}
                        />
                      )}
                      {['INTEGER', 'DECIMAL'].includes(q.question_type) && (
                        <TextField
                          value={field.value ?? ''}
                          onChange={field.onChange}
                          type="number"
                          inputProps={{
                            min: q.min_value ?? undefined,
                            max: q.max_value ?? undefined,
                            step: q.question_type === 'INTEGER' ? 1 : 'any',
                          }}
                        />
                      )}
                      {q.question_type === 'RATING' && (
                        <Slider
                          value={Number(field.value ?? q.rating_min ?? 1)}
                          onChange={(_, v) => field.onChange(v)}
                          min={q.rating_min ?? 1}
                          max={q.rating_max ?? 5}
                          step={1}
                          marks
                          valueLabelDisplay="on"
                          aria-label={q.question_text}
                        />
                      )}
                    </FormControl>
                  )}
                />
              ))}
            </Stack>
          ))}
          <Button
            type="submit"
            variant="contained"
            disabled={isSubmitting || item.status !== 'PUBLISHED'}
          >
            {isSubmitting ? 'Enviando…' : 'Enviar respuesta anónima'}
          </Button>
        </Stack>
      </Paper>
    </>
  );
}
