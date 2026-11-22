FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates git g++ make pkg-config libssl-dev && rm -rf /var/lib/apt/lists/*
# zsign is an external, MIT-licensed open source dependency. Build at deploy time.
RUN git clone --depth 1 https://github.com/zhlynn/zsign.git /tmp/zsign-src \
    && make -C /tmp/zsign-src/build/linux -j1 \
    && find /tmp/zsign-src -type f -name zsign -executable -exec cp {} /usr/local/bin/zsign \; \
    && test -x /usr/local/bin/zsign \
    && rm -rf /tmp/zsign-src
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py /app/
COPY static /app/static
ENV WORK_DIR=/tmp MAX_IPA_MB=2048 MAX_PLUGIN_MB=32
EXPOSE 8000
# Private LAN only is strongly recommended; add HTTPS/authentication before public deployment.
CMD ["/bin/sh", "-c", "exec uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
