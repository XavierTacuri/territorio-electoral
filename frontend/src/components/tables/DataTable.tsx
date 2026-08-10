import {
  Box,
  IconButton,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from '@mui/material';
import EditIcon from '@mui/icons-material/Edit';
import VisibilityIcon from '@mui/icons-material/Visibility';
import { EmptyState, LoadingSkeleton } from '../feedback/States';
export type Column<T> = { key: string; label: string; render: (row: T) => React.ReactNode };
export function DataTable<T extends { id: string }>({
  rows,
  columns,
  loading,
  onView,
  onEdit,
  label,
}: {
  rows: T[];
  columns: Column<T>[];
  loading?: boolean;
  onView?: (row: T) => void;
  onEdit?: (row: T) => void;
  label: string;
}) {
  if (loading) return <LoadingSkeleton />;
  if (!rows.length) return <EmptyState />;
  return (
    <TableContainer
      component={Paper}
      variant="outlined"
      sx={{ maxWidth: '100%', overflowX: 'auto' }}
    >
      <Table aria-label={label} size="small">
        <TableHead>
          <TableRow>
            {columns.map((column) => (
              <TableCell key={column.key}>
                <Typography fontWeight={700}>{column.label}</Typography>
              </TableCell>
            ))}
            {(onView || onEdit) && <TableCell align="right">Acciones</TableCell>}
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.id} hover>
              {columns.map((column) => (
                <TableCell key={column.key}>{column.render(row)}</TableCell>
              ))}
              {(onView || onEdit) && (
                <TableCell align="right">
                  <Box sx={{ whiteSpace: 'nowrap' }}>
                    {onView && (
                      <Tooltip title="Ver detalle">
                        <IconButton aria-label={'Ver ' + label} onClick={() => onView(row)}>
                          <VisibilityIcon />
                        </IconButton>
                      </Tooltip>
                    )}
                    {onEdit && (
                      <Tooltip title="Editar">
                        <IconButton aria-label={'Editar ' + label} onClick={() => onEdit(row)}>
                          <EditIcon />
                        </IconButton>
                      </Tooltip>
                    )}
                  </Box>
                </TableCell>
              )}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}
