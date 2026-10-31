# syntax=docker/dockerfile:1
# Arch's base is immutable here, but pacman -Syu intentionally uses rolling repos.
ARG BASE_IMAGE=archlinux@sha256:52dfbd5afb23a220d5ee92dafcb4c788d96c026ed04179890c23adef4c897fa0
FROM ${BASE_IMAGE}

ARG NODE_VERSION=25.2.1
ARG NODE_SHA256=b9f6a97e81c89a9df45526b4f86dafdccaf12b82295f7bf35bdb2b0f5e68744f
ARG HERDR_VERSION=0.9.5
ARG HERDR_SHA256=14d9e8bc8b4a9e0118d77c32266f76d461f09b40342eb23752960bd89f59929d
ARG HUNK_VERSION=0.24.1
ARG HUNK_SHA256=4b8c98f8d97745499916cc1e1d2f27ffd258c6d6358dd4532f61e41c5eb19692

COPY arch.packages /tmp/arch.packages
RUN test "$(uname -m)" = x86_64 && \
    pacman -Syu --needed --noconfirm $(grep -vE '^[[:space:]]*(#|$)' /tmp/arch.packages) && \
    pacman -Scc --noconfirm && rm /tmp/arch.packages

# Official upstream artifacts; no installers, mutable channels, or host binaries.
RUN set -eux; \
    curl -fsSL --retry 3 "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz" -o /tmp/node.tar.xz; \
    printf '%s  %s\n' "$NODE_SHA256" /tmp/node.tar.xz | sha256sum -c -; \
    tar -xJf /tmp/node.tar.xz --strip-components=1 -C /usr/local; \
    rm /tmp/node.tar.xz; \
    curl -fsSL --retry 3 "https://github.com/herdrdev/herdr/releases/download/v${HERDR_VERSION}/herdr-linux-x86_64" -o /tmp/herdr; \
    printf '%s  %s\n' "$HERDR_SHA256" /tmp/herdr | sha256sum -c -; \
    install -m 0755 /tmp/herdr /usr/local/bin/herdr; \
    rm /tmp/herdr; \
    node --version; herdr --version

RUN set -eux; \
    curl -fsSL --retry 3 "https://github.com/modem-dev/hunk/releases/download/v${HUNK_VERSION}/hunkdiff-linux-x64.tar.gz" -o /tmp/hunk.tar.gz; \
    printf '%s  %s\n' "$HUNK_SHA256" /tmp/hunk.tar.gz | sha256sum -c -; \
    mkdir /tmp/hunk; \
    tar -xzf /tmp/hunk.tar.gz --strip-components=1 -C /tmp/hunk; \
    install -m 0755 /tmp/hunk/hunk /usr/local/bin/hunk; \
    rm -rf /tmp/hunk /tmp/hunk.tar.gz; \
    hunk --version; lazygit --version; nvim --version

RUN useradd --create-home --uid 1000 --user-group --shell /bin/bash dev && \
    install -d -o dev -g dev /workspace /home/dev/.pi/agent/npm /home/dev/.config/herdr /home/dev/.local/bin && \
    chown -R dev:dev /home/dev

ENV HOME=/home/dev USER=dev LOGNAME=dev SHELL=/bin/bash
ENV PATH=/home/dev/.local/bin:/home/dev/.pi/agent/npm/node_modules/.bin:/home/dev/.local/share/mise/shims:/usr/local/sbin:/usr/local/bin:/usr/bin
ENV EDITOR=nvim VISUAL=nvim
USER dev
WORKDIR /home/dev/.pi/agent/npm
COPY --chown=dev:dev package.json package-lock.json ./
# No host node_modules and no dependency lifecycle hooks.
RUN npm ci --ignore-scripts --legacy-peer-deps --no-audit --no-fund && npm cache clean --force

COPY --chown=dev:dev settings.json /home/dev/.pi/agent/settings.json
COPY --chown=dev:dev herdr.toml /home/dev/.config/herdr/config.toml
COPY --chown=dev:dev bash_profile /home/dev/.bash_profile
COPY --chown=dev:dev bashrc /home/dev/.bashrc
COPY --chown=dev:dev starship.toml /home/dev/.config/starship.toml
COPY --chown=dev:dev gitconfig /home/dev/.gitconfig
COPY --chown=dev:dev --chmod=0755 git-credential-github-env /home/dev/.local/bin/git-credential-github-env
# Generate the matching official Pi integration in the GUEST home only.
RUN herdr integration install pi

# agentd (msb 0.7.11) supplies NODE_EXTRA_CA_CERTS=/.msb/tls/ca.pem.
# Do not overwrite runtime CA/proxy settings or bake credentials into the image.
WORKDIR /workspace
ENTRYPOINT ["/usr/bin/bash"]
