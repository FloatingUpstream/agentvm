# Pi VM image inputs

Fresh Arch userspace for msb 0.7.11, x86-64 only. No guest sshd, sudo,
host home, or host node_modules.
The dev user has UID/GID 1000 and owns `/workspace` and `/home/dev`.

`bin/build-pi-vm` follows the existing build/save/msb-load convention. It
accepts `IMAGE_NAME`, `ARCHIVE`, and build-argument environment overrides
`BASE_IMAGE`, `NODE_VERSION`, `NODE_SHA256`, `HERDR_VERSION`, `HERDR_SHA256`.
No token or credential build arguments are accepted. The build context is
only this directory. Default image name: `pi-vm:local`.

## Pins and reproducibility

- Official `library/archlinux` base manifest index:
  `sha256:52dfbd5afb23a220d5ee92dafcb4c788d96c026ed04179890c23adef4c897fa0`.
  **Arch remains rolling:** `pacman -Syu` uses current signed upstream package
  repositories, so the base digest does not make the entire image reproducible.
  `BASE_IMAGE` overrides the pinned base.
- Node 25.2.1 official Linux x64 tarball; SHA-256 from
  `https://nodejs.org/dist/v25.2.1/SHASUMS256.txt`.
- Herdr 0.9.5 official `herdr-linux-x86_64` artifact from
  `https://github.com/herdrdev/herdr/releases/tag/v0.9.5`; SHA-256 from the
  release asset's GitHub API `digest`. No host installation is modified.
- Pi 1.4.0 and all nine top-level extension versions are pinned in `package.json`.
  The checked-in lock pins guest transitive resolution, including integrity
  hashes.
- `npm ci --ignore-scripts --legacy-peer-deps` suppresses lifecycle hooks
  and automatic peer installation, matching Pi's package provisioning policy.
  The configured package sources are guest-local paths, not unversioned npm
  declarations that could install or update themselves on first startup.
- `herdr integration install pi` runs only inside the build, as dev, to generate
  the Pi lifecycle integration matching the pinned Herdr artifact.

## Runtime configuration

Pi has no baked-in provider, model endpoint, login, or credentials. Supply those
through the launcher at runtime. The settings configure dark theme, medium
thinking, visible thinking, and disabled telemetry; project trust still asks.
The Nord theme package is included.

msb 0.7.11 agentd supplies `NODE_EXTRA_CA_CERTS=/.msb/tls/ca.pem` and appends its
CA to distro bundles. Neither shell startup nor Docker ENV overrides this.
Do not use TLS-verification bypasses; non-msb runtimes must provide their own CA.

Git's credential helper answers only `get` for HTTPS `github.com` with runtime
`GH_TOKEN`, username `x-access-token`. It ignores store/erase and other hosts
and never writes credentials. `gh` is available via Arch's `github-cli`.
No token is required to build this public-artifact image.

Pi Web Access 0.45.0 can use keyless Exa MCP; other providers/features may need
host-supplied runtime keys or a separately provisioned
`/home/dev/.pi/agent/web-search.json`. Its config supports environment references
such as `"braveApiKey": "$BRAVE_API_KEY"`. Do not bake real values or browser
cookies into this image; outbound policy must allow the selected services.
No live host web-search config is copied.

## Checks without building

Run `bash images/pi-vm/test.sh`. This validates JSON pins and local resource
paths, shell syntax, the credential protocol using dummy values, and the build
wrapper with fake commands (no Docker daemon or msb instance needed).
Runtime checks cover login-shell PATH,
`node --version`, `pi --version`, `herdr --version`, guest ownership, Pi extension
loading, and a real msb TLS request. These integration checks are separate from
the static tests.
