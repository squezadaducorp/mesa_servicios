# Compilación
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# Servidor estático + proxy a la API (usuario sin privilegios, puertos 8080/8443)
FROM nginxinc/nginx-unprivileged:1.31-alpine
COPY nginx/aducorp-comun.conf nginx/aducorp-proxy.conf /etc/nginx/
COPY nginx/http.conf /etc/nginx/conf.d/default.conf
COPY nginx/https.conf /etc/nginx/aducorp-https.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080 8443
