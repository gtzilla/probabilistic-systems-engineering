FROM ubuntu:24.04

ARG DEBIAN_FRONTEND=noninteractive

# runtime deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    fontconfig \
    git \
    python3 \
    python3-pip \
  && rm -rf /var/lib/apt/lists/*

# Pin pandoc 3.9 (tarball)
RUN curl -fsSL -o /tmp/pandoc.tar.gz \
      https://github.com/jgm/pandoc/releases/download/3.9/pandoc-3.9-linux-amd64.tar.gz \
 && tar -xzf /tmp/pandoc.tar.gz -C /tmp \
 && install -m 0755 /tmp/pandoc-3.9/bin/pandoc /usr/local/bin/pandoc \
 && pandoc --version

# Pin pdf2htmlEX 0.18.8.rc1 AppImage
RUN curl -fsSL -o /usr/local/bin/pdf2htmlEX \
      https://sourceforge.net/projects/pdf2htmlex.mirror/files/v0.18.8.rc1/pdf2htmlEX-0.18.8.rc1-master-20200630-Ubuntu-eoan-x86_64.AppImage/download \
 && chmod 0755 /usr/local/bin/pdf2htmlEX

WORKDIR /repo
