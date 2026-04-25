#!/bin/sh
set -eu

case "${BACKEND_UPSTREAM:-}" in
  http://*|https://*) ;;
  *)
    BACKEND_UPSTREAM="http://api.railway.internal:8000"
    ;;
esac

if [ -z "${CLIENT_MAX_BODY_SIZE:-}" ]; then
  CLIENT_MAX_BODY_SIZE="50M"
fi

export BACKEND_UPSTREAM
export CLIENT_MAX_BODY_SIZE

envsubst '${BACKEND_UPSTREAM} ${CLIENT_MAX_BODY_SIZE}' \
  < /etc/nginx/templates/default.conf.template \
  > /etc/nginx/conf.d/default.conf
