# Compilación
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# Servidor estático + proxy a la API (usuario sin privilegios, puertos 8080/8443)
# Imagen oficial de nginx 1.30.8 (corrige las CVE de 1.30.6) adaptada para correr sin privilegios, igual que
# nginxinc/nginx-unprivileged, que aún no publica 1.30.8. Cuando la publique se puede volver a ella.
FROM nginx:1.30.8-alpine
# Parches de seguridad de Alpine publicados después de la imagen base (zlib, tiff, pcre2…)
RUN apk upgrade --no-cache \
 && sed -i '/^user /d' /etc/nginx/nginx.conf \
 && sed -i 's|^pid .*;|pid /tmp/nginx.pid;|' /etc/nginx/nginx.conf \
 && sed -i '/^http {/a\    client_body_temp_path /tmp/client_temp;\n    proxy_temp_path /tmp/proxy_temp;\n    fastcgi_temp_path /tmp/fastcgi_temp;\n    uwsgi_temp_path /tmp/uwsgi_temp;\n    scgi_temp_path /tmp/scgi_temp;' /etc/nginx/nginx.conf \
 && chown -R 101:0 /var/cache/nginx /etc/nginx /usr/share/nginx/html \
 && chmod -R g+w /var/cache/nginx /etc/nginx
USER 101
COPY nginx/aducorp-comun.conf nginx/aducorp-cabeceras.conf nginx/aducorp-proxy.conf /etc/nginx/
COPY nginx/http.conf /etc/nginx/conf.d/default.conf
COPY nginx/https.conf /etc/nginx/aducorp-https.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080 8443
