FROM nginx:1.27-alpine

RUN (getent group nginx || addgroup -S -g 101 nginx) && \
    (id -u nginx || adduser -S -D -H -u 101 -G nginx nginx)

RUN rm -f /etc/nginx/conf.d/default.conf

COPY nginx.conf /etc/nginx/nginx.conf

RUN chown -R nginx:nginx /etc/nginx/nginx.conf /var/log/nginx /var/cache/nginx && \
    chmod 644 /etc/nginx/nginx.conf

EXPOSE 80

STOPSIGNAL SIGQUIT

CMD ["nginx", "-g", "daemon off;"]
