FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY main.c plugins.conf ./
RUN gcc -O1 -o /app/plugin-host main.c -ldl
CMD ["/app/plugin-host"]
