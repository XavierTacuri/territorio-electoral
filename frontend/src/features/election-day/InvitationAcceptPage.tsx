import { useRef, useState } from 'react';
import { Alert, Box, Button, Chip, Paper, Stack, TextField, Typography } from '@mui/material';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { ApiError } from '../../api/errors';
import { useAuth } from '../../auth/AuthProvider';
import { LoadingSkeleton } from '../../components/feedback/States';
import { formatDateOnly } from '../../lib/dates';
import {
  INVITATION_STATUS_LABELS,
  STAFF_TYPE_LABELS,
  type ElectionDayInvitationPreview,
} from './types';

type AcceptResponse = { campaign_id: string; operation_id: string; message: string };

// El token viaja únicamente en el fragment de la URL (#token=...) — el
// fragment nunca se envía al servidor HTTP (no aparece en logs de acceso,
// Referer headers ni caches intermedios) — y se extrae y limpia de la barra
// de direcciones antes de cualquier otra cosa. A partir de ahí vive solo en
// memoria de React; nunca vuelve a escribirse en la URL ni en localStorage/
// IndexedDB.
//
// Red de seguridad efímera en sessionStorage: lazyWithReload puede disparar
// un window.location.reload() de autorrecuperación en la primerísima visita
// de un dispositivo (el service worker todavía instalándose hace fallar la
// carga del chunk — ver src/app/lazyWithReload.ts). Ese reload repite la
// navegación sobre la URL YA sin fragment (esta función ya lo limpió), así
// que sin esta red el token se perdería. Se borra en cuanto la invitación
// queda resuelta (ver clearEphemeralToken).
const SESSION_KEY = 'territorio.electionDayInviteToken';

function extractAndClearToken(): string {
  const match = window.location.hash.match(/token=([^&]+)/);
  let token = match ? decodeURIComponent(match[1]) : '';
  if (window.location.hash) {
    window.history.replaceState(null, '', window.location.pathname + window.location.search);
  }
  try {
    if (token) sessionStorage.setItem(SESSION_KEY, token);
    else token = sessionStorage.getItem(SESSION_KEY) || '';
  } catch {
    // sessionStorage no disponible (modo privado, etc.) — el token vive solo
    // en memoria; no sobrevivirá a un reload, pero nunca se persiste en un
    // almacenamiento más duradero.
  }
  return token;
}

function clearEphemeralToken(): void {
  try {
    sessionStorage.removeItem(SESSION_KEY);
  } catch {
    // best-effort
  }
}

export default function InvitationAcceptPage() {
  const navigate = useNavigate();
  const { user, login } = useAuth();
  const tokenRef = useRef<string | undefined>(undefined);
  if (tokenRef.current === undefined) tokenRef.current = extractAndClearToken();
  const token = tokenRef.current;

  const [accepted, setAccepted] = useState(false);
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [password, setPassword] = useState('');
  const [passwordConfirmation, setPasswordConfirmation] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  const [loginError, setLoginError] = useState('');
  const [loggingIn, setLoggingIn] = useState(false);

  const preview = useQuery({
    queryKey: ['election-day-invitation-preview', token],
    queryFn: async () => {
      const data = await apiRequest<ElectionDayInvitationPreview>(
        '/election-day/invitations/preview',
        { method: 'POST', body: JSON.stringify({ token }) },
      );
      if (!firstName) setFirstName(data.first_name);
      if (!lastName) setLastName(data.last_name);
      return data;
    },
    enabled: !!token,
    retry: false,
  });

  const acceptExisting = useMutation({
    mutationFn: () =>
      apiRequest<AcceptResponse>('/election-day/invitations/accept', {
        method: 'POST',
        body: JSON.stringify({ token }),
      }),
    onSuccess: () => {
      clearEphemeralToken();
      setAccepted(true);
    },
  });

  const acceptNewAccount = useMutation({
    mutationFn: () =>
      apiRequest<AcceptResponse>('/election-day/invitations/accept-new-account', {
        method: 'POST',
        body: JSON.stringify({
          token,
          first_name: firstName.trim(),
          last_name: lastName.trim(),
          password,
          password_confirmation: passwordConfirmation,
        }),
      }),
    onSuccess: async () => {
      // La cuenta recién creada queda autenticada de inmediato con la misma
      // contraseña que se acaba de fijar: evita un salto extra a /login y a
      // que ProtectedRoute redirija "IR A MI JORNADA" a una ruta genérica.
      try {
        await login(preview.data!.email, password);
      } catch {
        // Si el login automático fallara por cualquier motivo, la cuenta ya
        // quedó creada y aceptada igualmente — el usuario puede iniciar
        // sesión manualmente desde /login.
      }
      clearEphemeralToken();
      setAccepted(true);
    },
  });

  async function submitInlineLogin() {
    if (!preview.data) return;
    setLoginError('');
    setLoggingIn(true);
    try {
      await login(preview.data.email, loginPassword);
    } catch {
      setLoginError('Las credenciales ingresadas no son válidas.');
      setLoggingIn(false);
      return;
    }
    setLoggingIn(false);
    acceptExisting.mutate();
  }

  if (!token) {
    return (
      <InvitationShell>
        <Alert severity="error">Este enlace de invitación no es válido.</Alert>
      </InvitationShell>
    );
  }

  if (preview.isLoading) return <LoadingSkeleton />;

  const notFound =
    preview.isError && preview.error instanceof ApiError && preview.error.status === 404;

  return (
    <InvitationShell>
      {notFound && <Alert severity="error">Este enlace de invitación no es válido.</Alert>}
      {preview.isError && !notFound && (
        <Alert severity="error">No se pudo cargar la invitación. Intenta nuevamente.</Alert>
      )}

      {preview.data && !accepted && (
        <>
          <Stack spacing={0.5} sx={{ mb: 3 }}>
            <Typography>
              <strong>Campaña:</strong> {preview.data.campaign_name}
            </Typography>
            <Typography>
              <strong>Fecha:</strong> {formatDateOnly(preview.data.election_date)}
            </Typography>
            <Typography>
              <strong>Perfil:</strong> {STAFF_TYPE_LABELS[preview.data.staff_type]}
            </Typography>
            {preview.data.polling_places.length > 0 && (
              <Typography>
                <strong>Recintos:</strong>{' '}
                {preview.data.polling_places.map((p) => p.name).join(', ')}
              </Typography>
            )}
            <Box sx={{ pt: 1 }}>
              <Chip size="small" label={INVITATION_STATUS_LABELS[preview.data.status]} />
            </Box>
          </Stack>

          {preview.data.status === 'EXPIRED' && (
            <Alert severity="warning">
              Esta invitación expiró. Solicita una nueva al equipo de campaña.
            </Alert>
          )}
          {preview.data.status === 'REVOKED' && (
            <Alert severity="warning">Esta invitación fue revocada.</Alert>
          )}
          {preview.data.status === 'ACCEPTED' && (
            <Alert severity="info">Esta invitación ya fue aceptada.</Alert>
          )}

          {preview.data.status === 'PENDING' && preview.data.requires_login && (
            <Stack spacing={2}>
              <Alert severity="info">Ya tienes una cuenta en Territorio Electoral.</Alert>
              {!user ? (
                <Stack
                  spacing={2}
                  component="form"
                  onSubmit={(e) => {
                    e.preventDefault();
                    void submitInlineLogin();
                  }}
                >
                  <TextField
                    label="Correo"
                    value={preview.data.email}
                    disabled
                    InputProps={{ readOnly: true }}
                  />
                  <TextField
                    label="Contraseña"
                    type="password"
                    value={loginPassword}
                    onChange={(e) => setLoginPassword(e.target.value)}
                    required
                  />
                  {(loginError || acceptExisting.isError) && (
                    <Alert severity="error">
                      {loginError ||
                        'No se pudo aceptar la invitación. Verifica que iniciaste sesión con la cuenta que recibió esta invitación.'}
                    </Alert>
                  )}
                  <Button
                    fullWidth
                    variant="contained"
                    size="large"
                    type="submit"
                    disabled={loggingIn || acceptExisting.isPending}
                  >
                    INICIAR SESIÓN Y ACEPTAR
                  </Button>
                </Stack>
              ) : (
                <>
                  {acceptExisting.isError && (
                    <Alert severity="error">
                      No se pudo aceptar la invitación. Verifica que iniciaste sesión con la cuenta
                      que recibió esta invitación.
                    </Alert>
                  )}
                  <Button
                    fullWidth
                    variant="contained"
                    size="large"
                    disabled={acceptExisting.isPending}
                    onClick={() => acceptExisting.mutate()}
                  >
                    ACEPTAR CON ESTA CUENTA
                  </Button>
                </>
              )}
            </Stack>
          )}

          {preview.data.status === 'PENDING' && !preview.data.requires_login && (
            <Stack
              spacing={2}
              component="form"
              onSubmit={(e) => {
                e.preventDefault();
                acceptNewAccount.mutate();
              }}
            >
              <Typography variant="h2" component="h2">
                Crear acceso
              </Typography>
              <TextField
                label="Nombre"
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
                required
              />
              <TextField
                label="Apellido"
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
                required
              />
              <TextField
                label="Correo"
                value={preview.data.email}
                disabled
                InputProps={{ readOnly: true }}
              />
              <TextField
                label="Nueva contraseña"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
              <TextField
                label="Confirmar contraseña"
                type="password"
                value={passwordConfirmation}
                onChange={(e) => setPasswordConfirmation(e.target.value)}
                required
              />
              {acceptNewAccount.isError && (
                <Alert severity="error">
                  No se pudo activar tu acceso. Verifica que las contraseñas coincidan y cumplan los
                  requisitos de seguridad.
                </Alert>
              )}
              <Button
                fullWidth
                variant="contained"
                size="large"
                type="submit"
                disabled={acceptNewAccount.isPending}
              >
                ACTIVAR MI ACCESO
              </Button>
            </Stack>
          )}
        </>
      )}

      {accepted && (
        <Stack spacing={2}>
          <Alert severity="success">Tu acceso a la Jornada Electoral está listo.</Alert>
          <Button
            fullWidth
            variant="contained"
            size="large"
            onClick={() => navigate('/app/election-day')}
          >
            IR A MI JORNADA
          </Button>
        </Stack>
      )}
    </InvitationShell>
  );
}

function InvitationShell({ children }: { children: React.ReactNode }) {
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
        sx={{ width: '100%', maxWidth: 480, p: { xs: 3, sm: 5 } }}
      >
        <Typography component="h1" variant="h1">
          Territorio Electoral
        </Typography>
        <Typography color="text.secondary" sx={{ mb: 3 }}>
          Invitación a Jornada Electoral
        </Typography>
        {children}
      </Paper>
    </Box>
  );
}
