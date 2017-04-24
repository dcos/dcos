#!/usr/bin/env bash
set -xe

exec /opt/mesosphere/bin/gunicorn --worker-class=sync \
    --workers=1 \
    --threads=10 \
    --bind=unix:/run/dcos/pkgpanda-api.sock \
    --timeout=10 \
    --graceful-timeout=30 \
    --name Pkgpanda\ API \
    --access-logfile - \
    --access-logformat '%({X-Forwarded-For}i)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" (%(L)s s)' \
    --error-logfile - \
    --log-level=info \
    --umask 79 \
    --group dcos_adminrouter \
    pkgpanda.http:app
