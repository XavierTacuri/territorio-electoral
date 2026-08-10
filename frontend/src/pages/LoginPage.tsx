import { useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import {
  Alert,
  Box,
  Button,
  IconButton,
  InputAdornment,
  Paper,
  TextField,
  Typography,
} from '@mui/material';
import Visibility from '@mui/icons-material/Visibility';
import VisibilityOff from '@mui/icons-material/VisibilityOff';
import { useForm } from 'react-hook-form';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { z } from 'zod';
import { useAuth } from '../auth/AuthProvider';
const schema = z.object({
  identifier: z.string().trim().min(1, 'Ingresa tu usuario o correo.'),
  password: z.string().min(1, 'Ingresa tu contraseña.'),
});
type Form = z.infer<typeof schema>;
export default function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [visible, setVisible] = useState(false);
  const [error, setError] = useState('');
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<Form>({
    resolver: zodResolver(schema),
    defaultValues: { identifier: '', password: '' },
  });
  if (user) return <Navigate to="/app" replace />;
  return (
    <Box
      sx={{
        minHeight: '100vh',
        display: 'grid',
        placeItems: 'center',
        p: 2,
        background: 'linear-gradient(145deg,#edf2f3,#dfe7e9)',
      }}
    >
      <Paper
        id="contenido"
        tabIndex={-1}
        component="main"
        elevation={4}
        sx={{ width: '100%', maxWidth: 440, p: { xs: 3, sm: 5 } }}
      >
        <Typography component="h1" variant="h1">
          Territorio Electoral
        </Typography>
        <Typography color="text.secondary" sx={{ mb: 3 }}>
          Acceso seguro a la operación territorial
        </Typography>
        {error && (
          <Alert severity="error" aria-live="assertive" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}
        <Box
          component="form"
          onSubmit={handleSubmit(async (values) => {
            setError('');
            try {
              await login(values.identifier, values.password);
              const from = (location.state as { from?: { pathname?: string } } | null)?.from
                ?.pathname;
              navigate(from ?? '/app', { replace: true });
            } catch {
              setError('Las credenciales ingresadas no son válidas.');
            }
          })}
          noValidate
        >
          <TextField
            fullWidth
            autoFocus
            autoComplete="username"
            label="Correo o nombre de usuario"
            error={!!errors.identifier}
            helperText={errors.identifier?.message}
            {...register('identifier')}
            sx={{ mb: 2 }}
          />
          <TextField
            fullWidth
            autoComplete="current-password"
            label="Contraseña"
            type={visible ? 'text' : 'password'}
            error={!!errors.password}
            helperText={errors.password?.message}
            {...register('password')}
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <IconButton
                    aria-label={visible ? 'Ocultar contraseña' : 'Mostrar contraseña'}
                    onClick={() => setVisible((x) => !x)}
                  >
                    {visible ? <VisibilityOff /> : <Visibility />}
                  </IconButton>
                </InputAdornment>
              ),
            }}
            sx={{ mb: 3 }}
          />
          <Button fullWidth variant="contained" size="large" type="submit" disabled={isSubmitting}>
            {isSubmitting ? 'Ingresando…' : 'Iniciar sesión'}
          </Button>
        </Box>
      </Paper>
    </Box>
  );
}
