import { Button, Dialog, DialogActions, DialogContent, DialogTitle } from '@mui/material';
export function ConfirmDialog({
  open,
  title,
  children,
  onCancel,
  onConfirm,
  busy = false,
}: {
  open: boolean;
  title: string;
  children: React.ReactNode;
  onCancel: () => void;
  onConfirm: () => void;
  busy?: boolean;
}) {
  return (
    <Dialog open={open} onClose={onCancel} aria-labelledby="confirm-title">
      <DialogTitle id="confirm-title">{title}</DialogTitle>
      <DialogContent>{children}</DialogContent>
      <DialogActions>
        <Button onClick={onCancel}>Cancelar</Button>
        <Button variant="contained" color="error" disabled={busy} onClick={onConfirm}>
          Confirmar
        </Button>
      </DialogActions>
    </Dialog>
  );
}
