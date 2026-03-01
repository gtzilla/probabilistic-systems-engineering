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

RUN curl -fsSL -o /tmp/pdf2htmlEX.deb \
      https://github.com/pdf2htmlEX/pdf2htmlEX/releases/download/v0.18.8.rc1/pdf2htmlEX-0.18.8.rc1-master-20200630-Ubuntu-bionic-x86_64.deb \
  && apt-get update \
  && apt-get install -y --no-install-recommends /tmp/pdf2htmlEX.deb \
  && rm -f /tmp/pdf2htmlEX.deb \
  && rm -rf /var/lib/apt/lists/*

# PyMuPDF (fitz) extraction engine.
# Ubuntu 24.04 uses PEP 668 "externally managed" Python; install into a venv.
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv "$VIRTUAL_ENV" \
 && "$VIRTUAL_ENV/bin/pip" install --no-cache-dir --upgrade pip \
 && "$VIRTUAL_ENV/bin/pip" install --no-cache-dir pymupdf
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
