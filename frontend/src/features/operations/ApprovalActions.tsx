import { Button, Stack } from '@mui/material';
import CheckIcon from '@mui/icons-material/Check';
import CloseIcon from '@mui/icons-material/Close';

// Jerarquía compartida entre Actividades y Actividades pendientes de
// aprobación: Aprobar/Rechazar son la acción principal de una pantalla de
// revisión (se mantienen visibles, nunca detrás de un menú "⋯"), con tonos
// suaves en vez de botones sólidos que dominen la fila de la tabla.
const noCaps = { textTransform: 'none' } as const;
export function ApprovalActions({
  onApprove,
  onReject,
}: {
  onApprove: () => void;
  onReject: () => void;
}) {
  return (
    <Stack direction="row" spacing={1}>
      <Button
        size="small"
        variant="outlined"
        color="primary"
        startIcon={<CheckIcon fontSize="small" />}
        onClick={onApprove}
        sx={noCaps}
      >
        Aprobar
      </Button>
      <Button
        size="small"
        variant="outlined"
        color="error"
        startIcon={<CloseIcon fontSize="small" />}
        onClick={onReject}
        sx={noCaps}
      >
        Rechazar
      </Button>
    </Stack>
  );
}
