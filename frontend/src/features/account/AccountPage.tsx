import { useState } from 'react';
import {
  Alert,
  Box,
  Button,
  IconButton,
  InputAdornment,
  Paper,
  Stack,
  Tab,
  Tabs,
  TextField,
  Typography,
} from '@mui/material';
import VisibilityIcon from '@mui/icons-material/Visibility';
import VisibilityOffIcon from '@mui/icons-material/VisibilityOff';
import { apiRequest } from '../../api/client';
import { ApiError } from '../../api/errors';
import { useAuth } from '../../auth/AuthProvider';
import { PageHeader } from '../../components/layout/PageHeader';

const errorMessage = (error: unknown) => {
  if (
    error instanceof ApiError &&
    error.detail &&
    typeof error.detail === 'object' &&
    'detail' in error.detail
  ) {
    const detail = (error.detail as { detail?: unknown }).detail;
    if (typeof detail === 'string') return detail;
  }
  return 'No fue posible cambiar la contraseña.';
};

export default function AccountPage() {
  const { user, logout } = useAuth();
  const [tab, setTab] = useState(0);
  const [values, setValues] = useState({
    current_password: '',
    new_password: '',
    new_password_confirmation: '',
  });
  const [visible, setVisible] = useState<Record<string, boolean>>({});
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError('');
    try {
      const result = await apiRequest<{ message: string }>('/auth/change-password', {
        method: 'POST',
        body: JSON.stringify(values),
      });
      setMessage(result.message);
      window.setTimeout(() => void logout(), 1800);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving(false);
    }
  };
  return (
    <>
      <PageHeader
        title="Mi cuenta"
        description="Consulta tu perfil y administra la seguridad de tu cuenta."
      />
      <Paper sx={{ maxWidth: 720, width: '100%' }}>
        <Tabs
          value={tab}
          onChange={(_, value) => setTab(value)}
          aria-label="Secciones de mi cuenta"
        >
          <Tab label="Perfil" />
          <Tab label="Seguridad" />
        </Tabs>
        <Box sx={{ p: { xs: 2, sm: 3 } }}>
          {tab === 0 ? (
            <Stack spacing={1}>
              <Typography variant="h6">Perfil</Typography>
              <Typography>
                {user?.first_name} {user?.last_name}
              </Typography>
              <Typography color="text.secondary">{user?.email}</Typography>
              <Typography color="text.secondary">Usuario: {user?.username}</Typography>
            </Stack>
          ) : (
            <Box component="form" onSubmit={submit}>
              <Typography variant="h6" mb={2}>
                Cambiar contraseña
              </Typography>
              <Stack spacing={2}>
                {(['current_password', 'new_password', 'new_password_confirmation'] as const).map(
                  (name) => {
                    const labels = {
                      current_password: 'Contraseña actual',
                      new_password: 'Nueva contraseña',
                      new_password_confirmation: 'Confirmar nueva contraseña',
                    };
                    return (
                      <TextField
                        key={name}
                        required
                        fullWidth
                        label={labels[name]}
                        type={visible[name] ? 'text' : 'password'}
                        value={values[name]}
                        onChange={(e) => setValues({ ...values, [name]: e.target.value })}
                        inputProps={{
                          autoComplete:
                            name === 'current_password' ? 'current-password' : 'new-password',
                        }}
                        InputProps={{
                          endAdornment: (
                            <InputAdornment position="end">
                              <IconButton
                                aria-label={`${visible[name] ? 'Ocultar' : 'Mostrar'} ${labels[name].toLowerCase()}`}
                                onClick={() => setVisible({ ...visible, [name]: !visible[name] })}
                              >
                                {visible[name] ? <VisibilityOffIcon /> : <VisibilityIcon />}
                              </IconButton>
                            </InputAdornment>
                          ),
                        }}
                      />
                    );
                  },
                )}
                <Typography variant="body2" color="text.secondary">
                  Mínimo 8 caracteres, una letra y un número.
                </Typography>
                {error && <Alert severity="error">{error}</Alert>}
                {message && <Alert severity="success">{message}</Alert>}
                <Button
                  type="submit"
                  variant="contained"
                  disabled={saving || !!message}
                  sx={{ alignSelf: 'flex-start' }}
                >
                  {saving ? 'Actualizando…' : 'Cambiar contraseña'}
                </Button>
              </Stack>
            </Box>
          )}
        </Box>
      </Paper>
    </>
  );
}
