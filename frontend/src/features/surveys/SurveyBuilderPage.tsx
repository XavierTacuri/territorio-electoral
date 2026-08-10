import { useState } from 'react';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Button,
  Card,
  CardContent,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Grid,
  IconButton,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { useForm } from 'react-hook-form';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { queryClient } from '../../app/queryClient';
import { StatusBadge } from '../../components/data-display/Common';
import { ErrorState, LoadingSkeleton } from '../../components/feedback/States';
import { PageHeader } from '../../components/layout/PageHeader';
import type { Question, Section, Survey } from './types';
type SectionForm = { title: string; description: string };
type QuestionForm = {
  section_id: string;
  code: string;
  question_text: string;
  help_text: string;
  question_type: string;
  is_required: boolean;
  allow_other: boolean;
  min_value: string;
  max_value: string;
  min_length: string;
  max_length: string;
  min_selections: string;
  max_selections: string;
  rating_min: string;
  rating_max: string;
};
type OptionForm = { question_id: string; code: string; label: string; is_other: boolean };
const numberOrNull = (v: string) => (v === '' ? null : Number(v));
export default function SurveyBuilderPage() {
  const { campaignId = '', surveyId = '' } = useParams();
  const navigate = useNavigate();
  const [dialog, setDialog] = useState<'section' | 'question' | 'option' | 'general' | null>(null);
  const [error, setError] = useState('');
  const survey = useQuery({
    queryKey: ['campaign', campaignId, 'survey', surveyId],
    queryFn: () => apiRequest<Survey>('/campaigns/' + campaignId + '/surveys/' + surveyId),
  });
  const sectionForm = useForm<SectionForm>({ defaultValues: { title: '', description: '' } });
  const questionForm = useForm<QuestionForm>({
    defaultValues: {
      section_id: '',
      code: '',
      question_text: '',
      help_text: '',
      question_type: 'SINGLE_CHOICE',
      is_required: false,
      allow_other: false,
      min_value: '',
      max_value: '',
      min_length: '',
      max_length: '',
      min_selections: '',
      max_selections: '',
      rating_min: '1',
      rating_max: '5',
    },
  });
  const optionForm = useForm<OptionForm>({
    defaultValues: { question_id: '', code: '', label: '', is_other: false },
  });
  const general = useForm<{ title: string; description: string; instructions: string }>({
    values: {
      title: survey.data?.title ?? '',
      description: survey.data?.description ?? '',
      instructions: survey.data?.instructions ?? '',
    },
  });
  const action = useMutation({
    mutationFn: ({
      path,
      method = 'POST',
      body,
    }: {
      path: string;
      method?: string;
      body?: unknown;
    }) => apiRequest(path, { method, body: body ? JSON.stringify(body) : undefined }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['campaign', campaignId, 'survey', surveyId] });
      setDialog(null);
      setError('');
    },
  });
  if (survey.isLoading) return <LoadingSkeleton />;
  if (survey.isError || !survey.data) return <ErrorState retry={() => survey.refetch()} />;
  const item = survey.data;
  const sections = item.sections ?? [];
  const questions = sections.flatMap((x) => x.questions);
  const transition = async (name: 'publish' | 'close' | 'archive') => {
    try {
      await action.mutateAsync({
        path: '/campaigns/' + campaignId + '/surveys/' + surveyId + '/' + name,
      });
    } catch {
      setError('La transición no es válida. Revise secciones, preguntas y opciones.');
    }
  };
  const move = async (
    type: 'sections' | 'questions',
    record: Section | Question,
    direction: number,
  ) => {
    await action.mutateAsync({
      path: '/campaigns/' + campaignId + '/surveys/' + surveyId + '/' + type + '/' + record.id,
      method: 'PATCH',
      body: { display_order: Math.max(0, record.display_order + direction) },
    });
  };
  const editText = async (path: string, current: string, field: string, label: string) => {
    const value = window.prompt(label, current);
    if (value === null || !value.trim()) return;
    await action.mutateAsync({ path, method: 'PATCH', body: { [field]: value.trim() } });
  };
  const remove = async (path: string, label: string) => {
    if (!window.confirm('¿Eliminar ' + label + '? Esta acción requiere confirmación.')) return;
    await action.mutateAsync({ path, method: 'DELETE' });
  };
  return (
    <>
      <PageHeader
        title={'Constructor: ' + item.title}
        description="Use botones para reordenar; no se requiere arrastrar."
        action={
          <Stack direction="row" spacing={1} flexWrap="wrap">
            <StatusBadge value={item.status} />
            {item.status === 'DRAFT' && (
              <Button variant="contained" onClick={() => transition('publish')}>
                Publicar
              </Button>
            )}
            {item.status === 'PUBLISHED' && (
              <Button variant="contained" onClick={() => transition('close')}>
                Cerrar
              </Button>
            )}
            {item.status === 'CLOSED' && (
              <Button onClick={() => transition('archive')}>Archivar</Button>
            )}
            <Button
              onClick={() =>
                navigate('/app/campaigns/' + campaignId + '/surveys/' + surveyId + '/collect')
              }
            >
              Vista previa
            </Button>
          </Stack>
        }
      />
      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ mb: 2 }}>
        <Button startIcon={<AddIcon />} onClick={() => setDialog('general')}>
          Editar información
        </Button>
        <Button
          startIcon={<AddIcon />}
          disabled={item.status !== 'DRAFT'}
          onClick={() => setDialog('section')}
        >
          Crear sección
        </Button>
        <Button
          startIcon={<AddIcon />}
          disabled={!sections.length || item.status !== 'DRAFT'}
          onClick={() => setDialog('question')}
        >
          Crear pregunta
        </Button>
        <Button
          startIcon={<AddIcon />}
          disabled={
            !questions.some((x) =>
              ['SINGLE_CHOICE', 'MULTIPLE_CHOICE'].includes(x.question_type),
            ) || item.status !== 'DRAFT'
          }
          onClick={() => setDialog('option')}
        >
          Crear opción
        </Button>
      </Stack>
      {!sections.length && (
        <Alert severity="info">Cree al menos una sección y una pregunta antes de publicar.</Alert>
      )}
      {sections.map((section) => (
        <Accordion key={section.id} defaultExpanded>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Stack direction="row" alignItems="center" spacing={1} sx={{ width: '100%' }}>
              <Typography variant="h2" sx={{ flexGrow: 1 }}>
                {section.title}
              </Typography>
              <IconButton
                aria-label={'Subir sección ' + section.title}
                onClick={(e) => {
                  e.stopPropagation();
                  move('sections', section, -1);
                }}
              >
                <ArrowUpwardIcon />
              </IconButton>
              {item.status === 'DRAFT' && (
                <>
                  <Button
                    size="small"
                    onClick={(e) => {
                      e.stopPropagation();
                      editText(
                        '/campaigns/' +
                          campaignId +
                          '/surveys/' +
                          surveyId +
                          '/sections/' +
                          section.id,
                        section.title,
                        'title',
                        'Título de sección',
                      );
                    }}
                  >
                    Editar sección
                  </Button>
                  <Button
                    size="small"
                    color="error"
                    onClick={(e) => {
                      e.stopPropagation();
                      remove(
                        '/campaigns/' +
                          campaignId +
                          '/surveys/' +
                          surveyId +
                          '/sections/' +
                          section.id,
                        'la sección',
                      );
                    }}
                  >
                    Eliminar sección
                  </Button>
                </>
              )}
              <IconButton
                aria-label={'Bajar sección ' + section.title}
                onClick={(e) => {
                  e.stopPropagation();
                  move('sections', section, 1);
                }}
              >
                <ArrowDownwardIcon />
              </IconButton>
            </Stack>
          </AccordionSummary>
          <AccordionDetails>
            <Grid container spacing={2}>
              {section.questions.map((question) => (
                <Grid key={question.id} size={{ xs: 12, md: 6 }}>
                  <Card variant="outlined">
                    <CardContent>
                      <Stack direction="row" alignItems="start">
                        <Typography fontWeight={700} sx={{ flexGrow: 1 }}>
                          {question.question_text}
                          {question.is_required ? ' *' : ''}
                        </Typography>
                        <IconButton
                          aria-label="Subir pregunta"
                          onClick={() => move('questions', question, -1)}
                        >
                          <ArrowUpwardIcon />
                        </IconButton>
                        <IconButton
                          aria-label="Bajar pregunta"
                          onClick={() => move('questions', question, 1)}
                        >
                          <ArrowDownwardIcon />
                        </IconButton>
                      </Stack>
                      <Typography color="text.secondary">
                        {question.question_type} · código {question.code}
                      </Typography>
                      {item.status === 'DRAFT' && (
                        <Stack direction="row" flexWrap="wrap">
                          <Button
                            size="small"
                            onClick={() =>
                              editText(
                                '/campaigns/' +
                                  campaignId +
                                  '/surveys/' +
                                  surveyId +
                                  '/questions/' +
                                  question.id,
                                question.question_text,
                                'question_text',
                                'Texto de pregunta',
                              )
                            }
                          >
                            Editar pregunta
                          </Button>
                          <Button
                            size="small"
                            onClick={() =>
                              action.mutateAsync({
                                path:
                                  '/campaigns/' +
                                  campaignId +
                                  '/surveys/' +
                                  surveyId +
                                  '/questions/' +
                                  question.id,
                                method: 'PATCH',
                                body: { is_required: !question.is_required },
                              })
                            }
                          >
                            {question.is_required ? 'Hacer opcional' : 'Hacer obligatoria'}
                          </Button>
                          <Button
                            size="small"
                            color="error"
                            onClick={() =>
                              remove(
                                '/campaigns/' +
                                  campaignId +
                                  '/surveys/' +
                                  surveyId +
                                  '/questions/' +
                                  question.id,
                                'la pregunta',
                              )
                            }
                          >
                            Eliminar pregunta
                          </Button>
                        </Stack>
                      )}
                      {question.options.map((option) => (
                        <Stack key={option.id} direction="row" alignItems="center" spacing={0.5}>
                          <Typography sx={{ flexGrow: 1 }}>
                            ○ {option.label}
                            {option.is_other ? ' (Otro)' : ''}
                          </Typography>
                          {item.status === 'DRAFT' && (
                            <>
                              <IconButton
                                aria-label={'Subir opción ' + option.label}
                                onClick={() =>
                                  action.mutateAsync({
                                    path:
                                      '/campaigns/' +
                                      campaignId +
                                      '/surveys/' +
                                      surveyId +
                                      '/questions/' +
                                      question.id +
                                      '/options/' +
                                      option.id,
                                    method: 'PATCH',
                                    body: { display_order: Math.max(0, option.display_order - 1) },
                                  })
                                }
                              >
                                <ArrowUpwardIcon />
                              </IconButton>
                              <IconButton
                                aria-label={'Bajar opción ' + option.label}
                                onClick={() =>
                                  action.mutateAsync({
                                    path:
                                      '/campaigns/' +
                                      campaignId +
                                      '/surveys/' +
                                      surveyId +
                                      '/questions/' +
                                      question.id +
                                      '/options/' +
                                      option.id,
                                    method: 'PATCH',
                                    body: { display_order: option.display_order + 1 },
                                  })
                                }
                              >
                                <ArrowDownwardIcon />
                              </IconButton>
                              <Button
                                size="small"
                                onClick={() =>
                                  editText(
                                    '/campaigns/' +
                                      campaignId +
                                      '/surveys/' +
                                      surveyId +
                                      '/questions/' +
                                      question.id +
                                      '/options/' +
                                      option.id,
                                    option.label,
                                    'label',
                                    'Texto de opción',
                                  )
                                }
                              >
                                Editar opción
                              </Button>
                              <Button
                                size="small"
                                onClick={() =>
                                  action.mutateAsync({
                                    path:
                                      '/campaigns/' +
                                      campaignId +
                                      '/surveys/' +
                                      surveyId +
                                      '/questions/' +
                                      question.id +
                                      '/options/' +
                                      option.id,
                                    method: 'PATCH',
                                    body: { is_other: !option.is_other },
                                  })
                                }
                              >
                                Alternar Otro
                              </Button>
                              <Button
                                size="small"
                                color="error"
                                onClick={() =>
                                  remove(
                                    '/campaigns/' +
                                      campaignId +
                                      '/surveys/' +
                                      surveyId +
                                      '/questions/' +
                                      question.id +
                                      '/options/' +
                                      option.id,
                                    'la opción',
                                  )
                                }
                              >
                                Eliminar
                              </Button>
                            </>
                          )}
                        </Stack>
                      ))}
                    </CardContent>
                  </Card>
                </Grid>
              ))}
            </Grid>
          </AccordionDetails>
        </Accordion>
      ))}
      <Dialog open={dialog === 'general'} onClose={() => setDialog(null)} fullWidth>
        <DialogTitle>Información general</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField label="Título" {...general.register('title')} />
            <TextField label="Descripción" multiline {...general.register('description')} />
            <TextField label="Instrucciones" multiline {...general.register('instructions')} />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialog(null)}>Cancelar</Button>
          <Button
            variant="contained"
            onClick={general.handleSubmit((body) =>
              action.mutateAsync({
                path: '/campaigns/' + campaignId + '/surveys/' + surveyId,
                method: 'PATCH',
                body,
              }),
            )}
          >
            Guardar
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog open={dialog === 'section'} onClose={() => setDialog(null)} fullWidth>
        <DialogTitle>Crear sección</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField label="Título" {...sectionForm.register('title', { required: true })} />
            <TextField label="Descripción" {...sectionForm.register('description')} />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialog(null)}>Cancelar</Button>
          <Button
            variant="contained"
            onClick={sectionForm.handleSubmit((body) =>
              action.mutateAsync({
                path: '/campaigns/' + campaignId + '/surveys/' + surveyId + '/sections',
                body: { ...body, display_order: sections.length },
              }),
            )}
          >
            Crear
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog open={dialog === 'question'} onClose={() => setDialog(null)} fullWidth maxWidth="md">
        <DialogTitle>Crear pregunta</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 0 }}>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                select
                fullWidth
                label="Sección"
                defaultValue=""
                {...questionForm.register('section_id', { required: true })}
              >
                {sections.map((x) => (
                  <MenuItem key={x.id} value={x.id}>
                    {x.title}
                  </MenuItem>
                ))}
              </TextField>
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                fullWidth
                label="Código"
                {...questionForm.register('code', { required: true })}
              />
            </Grid>
            <Grid size={{ xs: 12 }}>
              <TextField
                fullWidth
                label="Pregunta"
                {...questionForm.register('question_text', { required: true })}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                select
                fullWidth
                label="Tipo"
                defaultValue="SINGLE_CHOICE"
                {...questionForm.register('question_type')}
              >
                {[
                  'SINGLE_CHOICE',
                  'MULTIPLE_CHOICE',
                  'YES_NO',
                  'SHORT_TEXT',
                  'LONG_TEXT',
                  'INTEGER',
                  'DECIMAL',
                  'RATING',
                ].map((x) => (
                  <MenuItem key={x} value={x}>
                    {x}
                  </MenuItem>
                ))}
              </TextField>
            </Grid>
            <Grid size={{ xs: 6, sm: 3 }}>
              <FormControlLabel
                control={<Checkbox {...questionForm.register('is_required')} />}
                label="Obligatoria"
              />
            </Grid>
            <Grid size={{ xs: 6, sm: 3 }}>
              <FormControlLabel
                control={<Checkbox {...questionForm.register('allow_other')} />}
                label="Permitir Otro"
              />
            </Grid>
            {[
              ['min_value', 'Mínimo numérico'],
              ['max_value', 'Máximo numérico'],
              ['min_length', 'Longitud mínima'],
              ['max_length', 'Longitud máxima'],
              ['min_selections', 'Selecciones mínimas'],
              ['max_selections', 'Selecciones máximas'],
              ['rating_min', 'Rating mínimo'],
              ['rating_max', 'Rating máximo'],
            ].map(([name, label]) => (
              <Grid key={name} size={{ xs: 6, sm: 3 }}>
                <TextField
                  fullWidth
                  type="number"
                  label={label}
                  {...questionForm.register(name as keyof QuestionForm)}
                />
              </Grid>
            ))}
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialog(null)}>Cancelar</Button>
          <Button
            variant="contained"
            onClick={questionForm.handleSubmit((v) =>
              action.mutateAsync({
                path:
                  '/campaigns/' +
                  campaignId +
                  '/surveys/' +
                  surveyId +
                  '/sections/' +
                  v.section_id +
                  '/questions',
                body: {
                  code: v.code,
                  question_text: v.question_text,
                  help_text: v.help_text || null,
                  question_type: v.question_type,
                  is_required: v.is_required,
                  display_order: questions.length,
                  allow_other: v.allow_other,
                  min_value: numberOrNull(v.min_value),
                  max_value: numberOrNull(v.max_value),
                  min_length: numberOrNull(v.min_length),
                  max_length: numberOrNull(v.max_length),
                  min_selections: numberOrNull(v.min_selections),
                  max_selections: numberOrNull(v.max_selections),
                  rating_min: numberOrNull(v.rating_min),
                  rating_max: numberOrNull(v.rating_max),
                  rating_min_label: null,
                  rating_max_label: null,
                },
              }),
            )}
          >
            Crear
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog open={dialog === 'option'} onClose={() => setDialog(null)} fullWidth>
        <DialogTitle>Crear opción</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              select
              label="Pregunta"
              defaultValue=""
              {...optionForm.register('question_id', { required: true })}
            >
              {questions
                .filter((x) => ['SINGLE_CHOICE', 'MULTIPLE_CHOICE'].includes(x.question_type))
                .map((x) => (
                  <MenuItem key={x.id} value={x.id}>
                    {x.question_text}
                  </MenuItem>
                ))}
            </TextField>
            <TextField label="Código" {...optionForm.register('code', { required: true })} />
            <TextField label="Etiqueta" {...optionForm.register('label', { required: true })} />
            <FormControlLabel
              control={<Checkbox {...optionForm.register('is_other')} />}
              label="Es opción Otro"
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialog(null)}>Cancelar</Button>
          <Button
            variant="contained"
            onClick={optionForm.handleSubmit((v) =>
              action.mutateAsync({
                path:
                  '/campaigns/' +
                  campaignId +
                  '/surveys/' +
                  surveyId +
                  '/questions/' +
                  v.question_id +
                  '/options',
                body: {
                  code: v.code,
                  label: v.label,
                  description: null,
                  display_order: questions.find((x) => x.id === v.question_id)?.options.length ?? 0,
                  is_other: v.is_other,
                },
              }),
            )}
          >
            Crear
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
