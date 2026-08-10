import { CssBaseline, ThemeProvider } from '@mui/material';
import { QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '../auth/AuthProvider';
import { CampaignProvider } from './CampaignProvider';
import { queryClient } from './queryClient';
import { theme } from './theme';
export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <CampaignProvider>{children}</CampaignProvider>
        </AuthProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
