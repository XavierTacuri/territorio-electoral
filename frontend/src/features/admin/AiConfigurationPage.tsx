import { useState } from 'react';
import { Alert, Button, Chip, Paper, Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { apiRequest } from '../../api/client';
import { ApiError } from '../../api/errors';
import { PageHeader } from '../../components/layout/PageHeader';
type Configuration = {
  provider_label: string;
  model: string | null;
  status: 'CONNECTED' | 'NOT_CONFIGURED' | 'ERROR';
  api_key_configured: boolean;
};
const labels = {
  CONNECTED: 'Conectada',
  NOT_CONFIGURED: 'No configurada',
  ERROR: 'Error de conexión',
};
export default function AiConfigurationPage() {
  const query = useQuery({
    queryKey: ['ai-provider-configuration'],
    queryFn: () => apiRequest<Configuration>('/admin/ai-provider'),
  });
  const [result, setResult] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [testing, setTesting] = useState(false);
  const test = async () => {
    setTesting(true);
    setResult(null);
    try {
      await apiRequest('/admin/ai-provider/test', { method: 'POST' });
      setResult({ type: 'success', text: 'Conexión correcta.' });
    } catch (error) {
      let text = 'No fue posible conectar con el proveedor de IA.';
      if (
        error instanceof ApiError &&
        error.detail &&
        typeof error.detail === 'object' &&
        'detail' in error.detail
      ) {
        const detail = (error.detail as { detail?: unknown }).detail;
        if (typeof detail === 'string') text = detail;
      }
      setResult({ type: 'error', text });
    } finally {
      setTesting(false);
    }
  };
  const data = query.data;
  return (
    <>
      <PageHeader
        title="Configuración de IA"
        description="Estado de la conexión de Territorio IA. La clave se administra de forma segura en la infraestructura."
      />
      <Paper sx={{ p: { xs: 2, sm: 3 }, maxWidth: 720 }}>
        <Stack spacing={2}>
          <Typography>
            <strong>Proveedor:</strong> {data?.provider_label ?? 'No configurado'}
          </Typography>
          <Typography>
            <strong>Modelo:</strong> {data?.model || 'No configurado'}
          </Typography>
          <Typography component="div">
            <strong>Estado:</strong>{' '}
            <Chip
              size="small"
              label={data ? labels[data.status] : 'Consultando…'}
              color={data?.status === 'CONNECTED' ? 'success' : 'default'}
            />
          </Typography>
          <Typography>
            <strong>Clave API:</strong>{' '}
            {data?.api_key_configured ? 'Configurada' : 'No configurada'}
          </Typography>
          {result && <Alert severity={result.type}>{result.text}</Alert>}
          <Button
            variant="contained"
            onClick={test}
            disabled={testing || query.isLoading}
            sx={{ alignSelf: 'flex-start' }}
          >
            {testing ? 'Probando…' : 'Probar conexión'}
          </Button>
        </Stack>
      </Paper>
    </>
  );
}
