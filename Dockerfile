FROM ubuntu:24.04

ARG APP_UID=10001
ARG APP_GID=10001

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        python3 \
        sane-utils \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid "${APP_GID}" es60w \
    && useradd \
        --uid "${APP_UID}" \
        --gid "${APP_GID}" \
        --no-create-home \
        --home-dir /nonexistent \
        --shell /usr/sbin/nologin \
        es60w \
    && install -d -o "${APP_UID}" -g "${APP_GID}" -m 0750 /data/raw

WORKDIR /app
COPY --chown=${APP_UID}:${APP_GID} src/es60w_listener.py /app/es60w_listener.py

ENV PYTHONUNBUFFERED=1 \
    RAW_SCAN=/data/raw \
    ES60W_LOG_FILE=

USER ${APP_UID}:${APP_GID}

STOPSIGNAL SIGTERM
ENTRYPOINT ["/usr/bin/python3", "/app/es60w_listener.py"]
