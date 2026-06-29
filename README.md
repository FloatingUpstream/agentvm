# opencode microsandbox VM

This repo builds an `omaterm`-inspired Arch dev image and launches a shell or `opencode` inside a local microsandbox microVM.

## Build

```bash
bin/build-opencode-vm
```

The build uses Docker or Podman, exports the image, and loads it into microsandbox as `opencode-vm:latest`.

If GitHub rate limits mise installs during the image build, pass a token:

```bash
GITHUB_TOKEN=ghp_... bin/build-opencode-vm
```

## Run

```bash
bin/ocvm .
```

`ocvm` creates or reuses a persistent microsandbox for that directory, mounts the directory at `/workspace`, and starts a shell there.

Useful flags:

```bash
bin/ocvm --opencode .       # start opencode
bin/ocvm --fresh .          # replace the existing project VM
bin/ocvm --readonly .       # mount project read-only
bin/ocvm --name testbox .   # choose a fixed VM name
bin/ocvm --port 3000:3000 . # publish localhost port
```

To install the launcher globally:

```bash
ln -sf "$PWD/bin/ocvm" ~/.local/bin/ocvm
```

If microsandbox was installed through npm, `msb doctor` may still complain about
missing standalone runtime files under `~/.microsandbox`. The npm package ships
its own platform binary and runtime library; the practical check is whether
`msb run debian -- uname -a` or `bin/ocvm --shell .` can start a VM.

Inside the image, opencode is configured with the Nord theme by default.

## Security Notes

The project directory is writable by default because this is meant for interactive development. Do not mount your whole home directory or credential directories into the VM. Authenticate tools such as `gh` inside the VM when needed.

The image is derived from the public `omaterm` package selections and dotfile bootstrap, but it is launched with `msb`, not the `omaterm` Docker host CLI.

The mise-installed agent/tool layer currently includes `opencode`, `codex`, `pi`, and `hunk`.
