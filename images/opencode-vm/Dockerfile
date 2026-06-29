# syntax=docker/dockerfile:1
FROM archlinux:latest

ARG GITHUB_TOKEN=

COPY arch.packages /tmp/arch.packages

RUN printf 'Server = https://mirror.omarchy.org/$repo/os/$arch\n' > /etc/pacman.d/mirrorlist && \
    printf '\n[omarchy]\nSigLevel = Optional TrustAll\nServer = https://pkgs.omarchy.org/edge/$arch\n' >> /etc/pacman.conf && \
    pacman -Syu --needed --noconfirm $(grep -vE '^[[:space:]]*(#|$)' /tmp/arch.packages) && \
    pacman -Scc --noconfirm

RUN useradd -m -u 1000 -s /bin/bash dev && \
    echo 'dev ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/dev && \
    chmod 0440 /etc/sudoers.d/dev

USER dev
WORKDIR /home/dev
ENV SHELL=/bin/bash

RUN yay -S --needed --noconfirm worktrunk-bin && \
    yay -Scc --noconfirm

# Reuse the Omaterm/Omarchy terminal defaults, then keep this image focused on
# microsandbox rather than the Docker-oriented omaterm launcher.
RUN curl -fsSL https://raw.githubusercontent.com/omacom-io/omadots/refs/heads/master/install.sh | bash

COPY --chown=dev:dev mise.packages /tmp/mise.packages
RUN set -eux; \
    if [ -n "$GITHUB_TOKEN" ]; then export GITHUB_TOKEN GH_TOKEN="$GITHUB_TOKEN"; fi; \
    eval "$(mise activate bash)"; \
    mise use -g -y $(grep -vE '^[[:space:]]*(#|$)' /tmp/mise.packages); \
    gpgconf --kill all || true; \
    rm -rf /home/dev/.gnupg

RUN mkdir -p /home/dev/.local/bin /home/dev/.local/state/ocvm && \
    printf '%s\n' \
      '{' \
      '  "$schema": "https://opencode.ai/config.json",' \
      '  "theme": "nord",' \
      '  "autoupdate": false' \
      '}' > /home/dev/.config/opencode/opencode.json && \
    printf '%s\n' \
      'export PATH="$HOME/.local/share/mise/shims:$HOME/.local/bin:$PATH"' \
      'export EDITOR=nvim' \
      'export VISUAL=nvim' \
      'cd /workspace 2>/dev/null || cd "$HOME"' \
      >> /home/dev/.bashrc

RUN sed -i 's|^if command -v fzf .*|if false \&\& command -v fzf \&>/dev/null; then|' /home/dev/.config/shell/inits

ENV HOME=/home/dev
ENV USER=dev
ENV LOGNAME=dev
ENV PATH="/home/dev/.local/share/mise/shims:/home/dev/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/bin"
ENV EDITOR=nvim
ENV VISUAL=nvim

WORKDIR /workspace
ENTRYPOINT ["/usr/bin/bash"]
