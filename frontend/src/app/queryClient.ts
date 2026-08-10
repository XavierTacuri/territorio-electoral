import { QueryClient } from '@tanstack/react-query';
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30000,
      retry: (count, error) => (error as { status?: number }).status !== 401 && count < 2,
      refetchOnWindowFocus: false,
    },
    mutations: { retry: false },
  },
});
