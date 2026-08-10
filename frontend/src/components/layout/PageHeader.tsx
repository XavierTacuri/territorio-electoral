import { Box, Typography } from '@mui/material';
export function PageHeader({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <Box
      sx={{
        display: 'flex',
        justifyContent: 'space-between',
        gap: 2,
        alignItems: 'flex-start',
        mb: 3,
        flexWrap: 'wrap',
      }}
    >
      <Box>
        <Typography component="h1" variant="h1">
          {title}
        </Typography>
        {description && <Typography color="text.secondary">{description}</Typography>}
      </Box>
      {action}
    </Box>
  );
}
