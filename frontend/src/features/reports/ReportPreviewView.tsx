import {
  Alert,
  Box,
  Card,
  CardContent,
  Chip,
  Divider,
  Link as MuiLink,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import { Link as RouterLink } from 'react-router-dom';
import { EVIDENCE_CLASS_LABELS, SOURCE_TYPE_LABELS, type ReportPreview } from './types';

function evidenceChipColor(evidenceClass: string): 'primary' | 'success' | 'default' | 'warning' {
  if (evidenceClass === 'OFFICIAL') return 'primary';
  if (evidenceClass === 'PUBLIC') return 'success';
  if (evidenceClass === 'DEMO') return 'warning';
  return 'default';
}

function cellValue(value: unknown): string {
  if (value === null || value === undefined) return 'No disponible';
  if (typeof value === 'number') return value.toLocaleString('es-EC');
  return String(value);
}

export function ReportPreviewView({ preview }: { preview: ReportPreview }) {
  return (
    <Stack spacing={2.5}>
      <Box>
        <Typography variant="overline" color="text.secondary">
          {preview.report_kind.replaceAll('_', ' ')}
        </Typography>
        <Typography component="h2" variant="h2">
          {preview.title}
        </Typography>
        {preview.subtitle && <Typography color="text.secondary">{preview.subtitle}</Typography>}
        <Typography variant="caption" color="text.secondary">
          Generado el {preview.generated_at} · {preview.generated_by}
        </Typography>
      </Box>

      {preview.is_demo && (
        <Alert severity="warning" variant="outlined">
          Este informe incluye datos simulados para demostración. No representan campaña real.
        </Alert>
      )}
      <Alert severity="info" variant="outlined">
        Informe descriptivo. No constituye predicción electoral, persuasión política ni
        perfilamiento individual.
      </Alert>

      <Card variant="outlined" sx={{ bgcolor: 'action.hover' }}>
        <CardContent>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
            <Typography component="h3" variant="h3">
              Resumen ejecutivo
            </Typography>
            <Chip
              size="small"
              label={
                preview.narrative.provider === 'deterministic-fallback'
                  ? 'Redacción del sistema'
                  : 'Redactado por IA grounded'
              }
            />
          </Stack>
          <Typography>{preview.narrative.resumen_ejecutivo}</Typography>
          {preview.narrative.hallazgos_principales.length > 0 && (
            <>
              <Typography component="h4" variant="h4" sx={{ mt: 2, mb: 1 }}>
                Hallazgos principales
              </Typography>
              <Stack spacing={0.5} component="ul" sx={{ pl: 3, m: 0 }}>
                {preview.narrative.hallazgos_principales.map((item, index) => (
                  <Typography component="li" key={index}>
                    {item}
                  </Typography>
                ))}
              </Stack>
            </>
          )}
        </CardContent>
      </Card>

      {preview.sections.map((section, index) => (
        <Card variant="outlined" key={`${section.title}-${index}`}>
          <CardContent>
            <Typography component="h3" variant="h3">
              {section.title}
            </Typography>
            {section.subtitle && (
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
                {section.subtitle}
              </Typography>
            )}
            {section.text && <Typography sx={{ mt: 1 }}>{section.text}</Typography>}
            {section.headers.length > 0 && section.rows.length > 0 && (
              <Box sx={{ maxWidth: '100%', overflowX: 'auto', mt: 2 }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      {section.headers.map((header) => (
                        <TableCell key={header}>{header}</TableCell>
                      ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {section.rows.map((row, rowIndex) => (
                      <TableRow key={rowIndex}>
                        {row.map((value, cellIndex) => (
                          <TableCell key={cellIndex}>{cellValue(value)}</TableCell>
                        ))}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Box>
            )}
            {section.headers.length > 0 && section.rows.length === 0 && (
              <Typography color="text.secondary" sx={{ mt: 1 }}>
                No hay datos disponibles para esta sección.
              </Typography>
            )}
          </CardContent>
        </Card>
      ))}

      {preview.citations.length > 0 && (
        <Card variant="outlined" id="report-citations">
          <CardContent>
            <Typography component="h3" variant="h3" sx={{ mb: 1 }}>
              Evidencia y fuentes
            </Typography>
            <Stack spacing={1}>
              {preview.citations.map((citation) => (
                <Stack
                  key={citation.id}
                  direction="row"
                  justifyContent="space-between"
                  alignItems="center"
                  flexWrap="wrap"
                  gap={1}
                  sx={{ py: 1, borderBottom: 1, borderColor: 'divider' }}
                >
                  <Box sx={{ minWidth: 0 }}>
                    <Typography fontWeight={700}>{citation.title}</Typography>
                    <Typography variant="body2" color="text.secondary">
                      {SOURCE_TYPE_LABELS[citation.source_type] ?? citation.source_type} ·{' '}
                      {citation.source_name}
                      {citation.record_date ? ` · ${citation.record_date}` : ''}
                    </Typography>
                  </Box>
                  <Stack direction="row" spacing={1} alignItems="center">
                    <Chip
                      size="small"
                      color={evidenceChipColor(citation.evidence_class)}
                      label={
                        EVIDENCE_CLASS_LABELS[citation.evidence_class] ?? citation.evidence_class
                      }
                    />
                    {citation.deep_link && (
                      <MuiLink
                        component={RouterLink}
                        to={citation.deep_link}
                        sx={{ whiteSpace: 'nowrap' }}
                      >
                        Ver origen
                      </MuiLink>
                    )}
                    {!citation.deep_link && citation.source_url && (
                      <MuiLink
                        href={citation.source_url}
                        target="_blank"
                        rel="noreferrer"
                        sx={{ whiteSpace: 'nowrap' }}
                      >
                        Ver fuente
                      </MuiLink>
                    )}
                  </Stack>
                </Stack>
              ))}
            </Stack>
          </CardContent>
        </Card>
      )}

      {preview.limitations.length > 0 && (
        <>
          <Divider />
          <Typography variant="body2" color="text.secondary">
            {preview.limitations.join(' ')}
          </Typography>
        </>
      )}
    </Stack>
  );
}
