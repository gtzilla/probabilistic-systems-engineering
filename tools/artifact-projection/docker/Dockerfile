FROM ubuntu:24.04

ARG DEBIAN_FRONTEND=noninteractive

# runtime deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    fontconfig \
    git \
    libfuse2 \
    python3 \
    python3-pip \
    python3-venv \

  && rm -rf /var/lib/apt/lists/*

# Pin pandoc 3.9 (tarball)
RUN curl -fsSL -o /tmp/pandoc.tar.gz \
      https://github.com/jgm/pandoc/releases/download/3.9/pandoc-3.9-linux-amd64.tar.gz \
 && tar -xzf /tmp/pandoc.tar.gz -C /tmp \
 && install -m 0755 /tmp/pandoc-3.9/bin/pandoc /usr/local/bin/pandoc \
 && pandoc --version

# Pin pdf2htmlEX 0.18.8.rc1 AppImage
RUN curl -fsSL -o /tmp/pdf2htmlEX.AppImage \
      https://github.com/pdf2htmlEX/pdf2htmlEX/releases/download/v0.18.8.rc1/pdf2htmlEX-0.18.8.rc1-x86_64.AppImage \
  && chmod 0755 /tmp/pdf2htmlEX.AppImage \
  && /tmp/pdf2htmlEX.AppImage --appimage-extract >/dev/null \
  && mv squashfs-root /opt/pdf2htmlEX \
  && rm -f /tmp/pdf2htmlEX.AppImage \
  && printf '%s\n' '#!/usr/bin/env bash' \
       'set -euo pipefail' \
       'APPDIR=/opt/pdf2htmlEX' \
       'export LD_LIBRARY_PATH="$APPDIR/usr/lib:$APPDIR/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH-}"' \
       'exec "$APPDIR/usr/bin/pdf2htmlEX" "$@"' \
       > /usr/local/bin/pdf2htmlEX \
  && chmod 0755 /usr/local/bin/pdf2htmlEX
