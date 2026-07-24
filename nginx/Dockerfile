FROM nginx:1.27-alpine

RUN (getent group nginx || addgroup -S -g 101 nginx) && \
    (id -u nginx || adduser -S -D -H -u 101 -G nginx nginx)

RUN rm -f /etc/nginx/conf.d/default.conf && \
    sed -i 's|^pid .*;|pid /tmp/nginx.pid;|' /etc/nginx/nginx.conf

COPY nginx.conf /etc/nginx/conf.d/default.conf

RUN chown -R nginx:nginx /etc/nginx/conf.d/default.conf /var/log/nginx /var/cache/nginx && \
    chmod 644 /etc/nginx/conf.d/default.conf

USER nginx

EXPOSE 8080

STOPSIGNAL SIGQUIT

ENTRYPOINT []
CMD ["nginx", "-g", "daemon off;"]
