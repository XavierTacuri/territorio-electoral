# Frontend web

React, TypeScript y Vite con Material UI, TanStack Query, React Hook Form/Zod, Recharts y MapLibre lazy. Los tokens de acceso viven exclusivamente en memoria; la renovación usa cookie HttpOnly y CSRF.

## Desarrollo

Copie .env.example a .env.local, ejecute npm ci, npm run api:generate y npm run dev. Todo valor VITE\_ es público: nunca coloque secretos allí.

Validación: npm run lint, npm run format:check, npm run typecheck, npm run test, npm run build y npm run e2e.

Las fechas funcionales circulan como YYYY-MM-DD y se muestran como DD/MM/AAAA. El mapa requiere VITE_MAP_STYLE_URL; sin ella se presenta un estado controlado.
