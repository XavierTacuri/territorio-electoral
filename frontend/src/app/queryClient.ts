import { QueryClient } from '@tanstack/react-query';
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30000,
      retry: (count, error) => {
        const status = (error as { status?: number }).status;
        return status !== 401 && status !== 403 && status !== 429 && count < 2;
      },
      refetchOnWindowFocus: false,
    },
    mutations: { retry: false },
  },
});
