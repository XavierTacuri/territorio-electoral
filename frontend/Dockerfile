FROM node:22.16.0-alpine3.22 AS build
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run typecheck && npm run build

FROM nginx:1.28.0-alpine3.21
COPY nginx.conf /etc/nginx/nginx.conf
COPY proxy_params /etc/nginx/proxy_params
COPY --from=build /build/dist /usr/share/nginx/html
RUN chown -R nginx:nginx /usr/share/nginx/html /var/cache/nginx /var/run
USER nginx
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD wget -q -O - http://127.0.0.1:8080/health || exit 1
