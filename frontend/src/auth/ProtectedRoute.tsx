import { CircularProgress, Box } from '@mui/material';
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from './AuthProvider';
export function ProtectedRoute() {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading)
    return (
      <Box sx={{ minHeight: '100vh', display: 'grid', placeItems: 'center' }}>
        <CircularProgress aria-label="Cargando sesión" />
      </Box>
    );
  return user ? <Outlet /> : <Navigate to="/login" replace state={{ from: location }} />;
}
