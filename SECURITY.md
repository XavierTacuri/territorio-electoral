# Seguridad

El OAuth2 existente permanece para Swagger y automatización. El navegador recibe JWT corto en memoria y refresh aleatorio en cookie HttpOnly, Secure en producción, SameSite Lax y ruta limitada. Refresh/logout requieren double-submit CSRF y producción valida Origin. Cada refresh rota el token; la reutilización revoca la familia. Contraseñas, desactivación y roles críticos incrementan token_version y revocan sesiones.

No registre ni exponga contraseñas, tokens, CSRF, hashes, IP, User-Agent, rutas, archivos o respuestas. Configure SECRET_KEY, BROWSER_REFRESH_TOKEN_HMAC_SECRET y SURVEY_SUBMISSION_HMAC_SECRET distintos. Nginx define CSP sin unsafe-eval; FastAPI limita CORS y Trusted Hosts.

Los uploads se validan en backend y tienen límite. Los informes privados se descargan como blob con nosniff; XLSX no se interpreta. Reporte vulnerabilidades de forma privada al responsable del despliegue y mantenga dependencias revisadas semanalmente.

La plataforma no guarda encuestados identificados, padrón nominal, voto individual, puntos de respuestas ni textos abiertos; no implementa microsegmentación, perfilamiento, predicción, persuasión ni recomendaciones políticas.

## Riesgo npm revisado el 03/08/2026

`npm audit` y `npm audit --omit=dev` informan dos hallazgos de severidad alta: `react-router-dom` es dependencia directa y `react-router` transitiva. Ambos corresponden a GHSA-qwww-vcr4-c8h2: omisión CSRF en modo RSC que permite ejecutar una server action antes de una respuesta 400. Territorio Electoral es una SPA Vite: no usa SSR, RSC, server actions ni loaders de servidor, por lo que el vector afectado no está habilitado.

No existe una actualización ascendente compatible indicada por npm; la corrección automática propuesta degradaría `react-router-dom` de 7.18.2 a 7.11.0. No se usa `npm audit fix --force`. La mitigación es mantener la SPA sin capacidades RSC/SSR, conservar CSRF y Origin en FastAPI/Nginx, y revisar semanalmente Dependabot y el advisory hasta disponer de una versión ascendente corregida.

Riesgo residual aceptado temporalmente: el vector afectado no es utilizado por esta SPA. Se mantiene seguimiento hasta disponer de una actualización compatible.

Los avisos previos de desarrollo quedaron corregidos sin saltos mayores: `@playwright/test` 1.55.1, `vite` 7.3.6 y `vitest` 3.2.7. Playwright solo descarga navegadores durante preparación controlada de E2E; Vite no se ejecuta en producción; Vitest UI no se inicia. Acción futura: actualizar cada paquete dentro de su línea compatible y ejecutar la batería completa antes de promoverlo.