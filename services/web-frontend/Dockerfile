# syntax=docker/dockerfile:1.7
FROM nginx:1.27-alpine

# Use the template-substitution feature of the official nginx image:
# files in /etc/nginx/templates/*.template are envsubst'd into /etc/nginx/conf.d/
COPY services/web-frontend/nginx.conf /etc/nginx/templates/default.conf.template
COPY services/web-frontend/public /usr/share/nginx/html

ARG BUILD_VERSION=dev
RUN printf '{"version":"%s"}\n' "$BUILD_VERSION" > /usr/share/nginx/html/version.json \
 && sed -i "s/name=\"app-version\" content=\"dev\"/name=\"app-version\" content=\"${BUILD_VERSION}\"/" /usr/share/nginx/html/index.html

ENV API_GATEWAY_URL=http://api-gateway:8080
# Only substitute the vars we use; otherwise envsubst eats $host, $remote_addr etc.
ENV NGINX_ENVSUBST_TEMPLATE_DIR=/etc/nginx/templates
ENV NGINX_ENVSUBST_OUTPUT_DIR=/etc/nginx/conf.d
ENV NGINX_ENVSUBST_FILTER='^(API_GATEWAY_URL)$'

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -qO- http://localhost:3000/ > /dev/null || exit 1
