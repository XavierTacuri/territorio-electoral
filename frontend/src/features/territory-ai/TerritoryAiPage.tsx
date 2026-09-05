import { KeyboardEvent, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Divider,
  Drawer,
  Link,
  List,
  ListItemButton,
  ListItemText,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useParams, useSearchParams } from 'react-router-dom';
import { ApiError } from '../../api/errors';
import { apiRequest } from '../../api/client';
import { queryClient } from '../../app/queryClient';
import { commercialErrorMessages, territoryAiSourceLabels } from '../../lib/labels';
type Entitlement = {
  status: 'ENABLED' | 'TRIAL' | 'EXPIRED' | 'DISABLED' | 'SCHEDULED';
  expires_at: string | null;
} | null;
type Territory = { id: number; name: string; dpa_code: string; level: string };
type Citation = {
  id: string;
  source_type: string;
  evidence_class: 'OFFICIAL' | 'PUBLIC' | 'CAMPAIGN' | 'DEMO';
  title: string;
  source_name: string;
  reference_date: string | null;
  data_cutoff: string | null;
  territory: Territory | null;
  excerpt: string | null;
  internal_path: string | null;
  external_url: string | null;
  freshness: string;
  metadata?: {
    fieldwork_start?: string;
    fieldwork_end?: string;
    sample_size?: number;
    methodology?: string;
    coverage?: string;
  };
};
type Answer = {
  answer: string;
  citations: Citation[];
  limitations: string[];
  intent: string;
  territory: Territory | null;
  conversation_id: string;
  message_id: string;
  provider: string | null;
  model: string | null;
  status: string;
};
type Message = {
  id: string;
  role: 'USER' | 'ASSISTANT';
  content: string;
  citations: Citation[];
  created_at: string;
};
type Conversation = { id: string; title: string; messages: Message[] };
const suggestions = [
  '¿Cuál es el panorama electoral actual?',
  '¿Cómo ha cambiado la participación electoral?',
  '¿Qué necesidades se han registrado por parroquia?',
  '¿Qué temas se repiten en las actividades?',
  '¿Qué estudios agregados están disponibles?',
  'Resume la evidencia disponible sobre vialidad.',
];
export const evidenceClassLabels = {
  OFFICIAL: 'Oficial',
  PUBLIC: 'Fuente pública',
  CAMPAIGN: 'Registro de campaña',
  DEMO: 'Datos simulados',
} as const;
function errorMessage(error: Error) {
  if (error instanceof ApiError) {
    const body = error.detail as { detail?: { code?: string; message?: string } } | undefined;
    if (body?.detail?.code === 'AI_PROVIDER_UNAVAILABLE')
      return 'Territorio IA no está configurada en este entorno.';
    return (
      commercialErrorMessages[body?.detail?.code ?? ''] ??
      'No fue posible completar la consulta en Territorio IA.'
    );
  }
  return 'No fue posible completar la consulta.';
}
export default function TerritoryAiPage() {
  const { campaignId } = useParams();
  const [params] = useSearchParams();
  const [question, setQuestion] = useState(params.get('question') ?? '');
  const [conversationId, setConversationId] = useState<string>();
  const [local, setLocal] = useState<Message[]>([]);
  const [citation, setCitation] = useState<Citation | null>(null);
  const entitlement = useQuery({
    queryKey: ['entitlement', campaignId, 'TERRITORY_AI'],
    queryFn: () =>
      apiRequest<Entitlement>(`/campaigns/${campaignId}/feature-entitlements/TERRITORY_AI`),
    enabled: !!campaignId,
  });
  const active = entitlement.data?.status === 'ENABLED' || entitlement.data?.status === 'TRIAL';
  const conversations = useQuery({
    queryKey: ['territory-ai-conversations', campaignId],
    queryFn: () =>
      apiRequest<Conversation[]>(`/campaigns/${campaignId}/territory-ai/conversations`),
    enabled: !!campaignId && active,
  });
  const selected = useQuery({
    queryKey: ['territory-ai-conversation', campaignId, conversationId],
    queryFn: () =>
      apiRequest<Conversation>(
        `/campaigns/${campaignId}/territory-ai/conversations/${conversationId}`,
      ),
    enabled: !!campaignId && !!conversationId,
  });
  useEffect(() => {
    if (selected.data?.messages) setLocal(selected.data.messages);
  }, [selected.data]);
  const query = useMutation({
    mutationFn: (value: string) =>
      apiRequest<Answer>(`/campaigns/${campaignId}/territory-ai/query`, {
        method: 'POST',
        body: JSON.stringify({
          question: value,
          conversation_id: conversationId,
          parish_id: params.get('parish_id') ? Number(params.get('parish_id')) : null,
          study_id: params.get('study_id'),
          activity_id: params.get('activity_id'),
          need_id: params.get('need_id'),
          public_item_id: params.get('public_item_id'),
        }),
      }),
    onMutate: (value) => {
      setLocal((old) => [
        ...old,
        {
          id: `pending-${Date.now()}`,
          role: 'USER',
          content: value,
          citations: [],
          created_at: new Date().toISOString(),
        },
      ]);
      setQuestion('');
    },
    onSuccess: (data) => {
      setConversationId(data.conversation_id);
      setLocal((old) => [
        ...old,
        {
          id: data.message_id,
          role: 'ASSISTANT',
          content: data.answer,
          citations: data.citations,
          created_at: new Date().toISOString(),
        },
      ]);
      queryClient.invalidateQueries({ queryKey: ['territory-ai-conversations', campaignId] });
    },
  });
  const send = () => {
    const value = question.trim();
    if (value && !query.isPending) query.mutate(value);
  };
  const keyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };
  if (entitlement.isLoading) return <CircularProgress aria-label="Cargando licencia" />;
  if (!active)
    return (
      <Stack spacing={2}>
        <Typography variant="h4" fontWeight={800}>
          Territorio IA
        </Typography>
        <Paper sx={{ p: 4, textAlign: 'center' }}>
          <Chip label="PRO" color="secondary" />
          <Typography variant="h5" sx={{ mt: 2 }}>
            Funcionalidad disponible en el plan Pro.
          </Typography>
          <Typography color="text.secondary">
            Territorio IA no está disponible para esta campaña.
          </Typography>
        </Paper>
      </Stack>
    );
  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: { xs: '1fr', md: '240px minmax(0,1fr)' },
        gap: 2,
        height: { md: 'calc(100vh - 112px)' },
      }}
    >
      <Paper sx={{ display: { xs: 'none', md: 'block' }, overflow: 'auto' }}>
        <Button
          sx={{ m: 1 }}
          onClick={() => {
            setConversationId(undefined);
            setLocal([]);
          }}
        >
          Nueva conversación
        </Button>
        <List>
          {conversations.data?.map((c) => (
            <ListItemButton
              key={c.id}
              selected={c.id === conversationId}
              onClick={() => setConversationId(c.id)}
            >
              <ListItemText primary={c.title} />
            </ListItemButton>
          ))}
        </List>
      </Paper>
      <Stack minWidth={0} spacing={2}>
        <Box>
          <Typography variant="h4" fontWeight={800}>
            Territorio IA
          </Typography>
          <Typography color="text.secondary">
            Consulta los datos de tu campaña y territorio con respuestas respaldadas por fuentes.
          </Typography>
          {entitlement.data?.status === 'TRIAL' && (
            <Chip sx={{ mt: 1 }} label="Prueba activa" color="info" />
          )}
        </Box>
        <Paper
          aria-live="polite"
          sx={{
            p: 2,
            flex: 1,
            minHeight: 240,
            maxHeight: { md: 'calc(100vh - 390px)' },
            overflowY: 'auto',
          }}
        >
          {!local.length && (
            <Stack spacing={1}>
              <Typography fontWeight={700}>Preguntas sugeridas</Typography>
              {suggestions.map((s) => (
                <Button
                  key={s}
                  variant="outlined"
                  sx={{ justifyContent: 'flex-start', textAlign: 'left' }}
                  onClick={() => setQuestion(s)}
                >
                  {s}
                </Button>
              ))}
            </Stack>
          )}
          {local.map((m) => (
            <Box
              key={m.id}
              sx={{
                display: 'flex',
                justifyContent: m.role === 'USER' ? 'flex-end' : 'flex-start',
                mb: 2,
              }}
            >
              <Paper
                variant="outlined"
                sx={{
                  p: 2,
                  maxWidth: '85%',
                  bgcolor: m.role === 'USER' ? 'primary.50' : 'background.paper',
                }}
              >
                <Typography sx={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
                  {m.content}
                </Typography>
                {m.citations?.length > 0 && (
                  <Stack direction="row" flexWrap="wrap" gap={1} mt={2}>
                    {m.citations.map((c) => (
                      <Chip
                        key={c.id}
                        label={`${c.id}. ${c.title}`}
                        onClick={() => setCitation(c)}
                        clickable
                      />
                    ))}
                  </Stack>
                )}
              </Paper>
            </Box>
          ))}
          {query.isPending && (
            <CircularProgress size={24} aria-label="Territorio IA está respondiendo" />
          )}
        </Paper>
        {query.isError && <Alert severity="error">{errorMessage(query.error)}</Alert>}
        <Paper sx={{ p: 2 }}>
          <TextField
            fullWidth
            multiline
            minRows={2}
            maxRows={6}
            label="Escribe una pregunta"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={keyDown}
            disabled={query.isPending}
            helperText="Presiona Enter para enviar · Mayús+Enter para una nueva línea"
          />
          <Button
            variant="contained"
            sx={{ mt: 1 }}
            onClick={send}
            disabled={!question.trim() || query.isPending}
          >
            ENVIAR
          </Button>
        </Paper>
      </Stack>
      <Drawer
        anchor="right"
        open={!!citation}
        onClose={() => setCitation(null)}
        PaperProps={{ sx: { width: { xs: '100%', sm: 420 }, p: 3 } }}
      >
        {citation && (
          <Stack spacing={2}>
            <Typography variant="h5">Fuente</Typography>
            <Divider />
            <Typography>
              <b>Tipo:</b>{' '}
              {territoryAiSourceLabels[citation.source_type] ?? 'Fuente de información'}
            </Typography>
            <Chip
              label={evidenceClassLabels[citation.evidence_class] ?? 'Registro de campaña'}
              color={citation.evidence_class === 'DEMO' ? 'warning' : 'default'}
            />
            {citation.evidence_class === 'DEMO' && (
              <Alert severity="warning">Datos simulados para demostración.</Alert>
            )}
            <Typography>
              <b>Título:</b> {citation.title}
            </Typography>
            <Typography>
              <b>Fuente:</b> {citation.source_name}
            </Typography>
            <Typography>
              <b>Fecha:</b> {citation.reference_date ?? 'No disponible'}
            </Typography>
            <Typography>
              <b>Corte:</b> {citation.data_cutoff ?? 'No disponible'}
            </Typography>
            <Typography>
              <b>Territorio:</b> {citation.territory?.name ?? 'Cantonal'}
            </Typography>
            {citation.source_type === 'SURVEY_STUDY' && (
              <Paper variant="outlined" sx={{ p: 2 }}>
                <Typography>
                  <b>Encuesta:</b> {citation.title}
                </Typography>
                <Typography>
                  <b>Trabajo de campo:</b> {citation.metadata?.fieldwork_start ?? 'No disponible'} –{' '}
                  {citation.metadata?.fieldwork_end ?? 'No disponible'}
                </Typography>
                <Typography>
                  <b>Muestra:</b> {citation.metadata?.sample_size ?? 'No disponible'}
                </Typography>
                <Typography>
                  <b>Metodología:</b> {citation.metadata?.methodology ?? 'No disponible'}
                </Typography>
                <Typography>
                  <b>Cobertura:</b>{' '}
                  {citation.metadata?.coverage === 'PARISH' ? 'Parroquial' : 'Cantonal'}
                </Typography>
              </Paper>
            )}
            <Typography>
              <b>Nivel:</b>{' '}
              {citation.territory?.level === 'CANTON'
                ? 'Cantón'
                : citation.territory?.level === 'PARISH'
                  ? 'Parroquia'
                  : 'No disponible'}
            </Typography>
            {citation.excerpt && (
              <Paper variant="outlined" sx={{ p: 2 }}>
                <Typography>{citation.excerpt}</Typography>
              </Paper>
            )}
            {citation.internal_path && (
              <Button component={Link} href={citation.internal_path}>
                VER EN TERRITORIO ELECTORAL
              </Button>
            )}
            {citation.external_url && (
              <Button
                component={Link}
                href={citation.external_url}
                target="_blank"
                rel="noreferrer"
              >
                ABRIR FUENTE
              </Button>
            )}
            <Button onClick={() => setCitation(null)}>Cerrar</Button>
          </Stack>
        )}
      </Drawer>
    </Box>
  );
}
