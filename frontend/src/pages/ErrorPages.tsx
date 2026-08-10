import { Button, Container, Typography } from '@mui/material';
import { Link } from 'react-router-dom';
export function ErrorPage({
  code = 'Error',
  message = 'Ocurrió un error inesperado.',
}: {
  code?: string;
  message?: string;
}) {
  return (
    <Container component="main" sx={{ py: 10, textAlign: 'center' }}>
      <Typography variant="h1">{code}</Typography>
      <Typography sx={{ my: 2 }}>{message}</Typography>
      <Button component={Link} to="/app" variant="contained">
        Volver al inicio
      </Button>
    </Container>
  );
}
