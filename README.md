# Pi + Herdr in a microsandbox VM

An Arch userspace with Pi, a pinned extension package set, and guest Herdr.
Microsandbox supplies a separate guest
kernel. Local Herdr connects through msb's built-in SSH transport without a
guest SSH daemon, published SSH port, or shared host socket.

Requirements: Linux x86-64 with writable `/dev/kvm`, msb **0.7.11**, Python 3,
Git, OpenSSH client/keygen, and Herdr **0.9.5**. Building needs Docker or Podman.
No host desktop configuration is changed by building or creating a VM.

## Launcher setup

Add the repository's `bin` directory to the host shell's `PATH`, replacing
`/path/to/microvm` with the repository location:

```bash
export PATH="/path/to/microvm/bin:$PATH"
```

The examples below use `pivm` from that directory. Image build and test commands
run from the repository root.

## Launch a project VM

From a local Herdr pane:

```bash
cd /path/to/myproject
pivm
```

The launcher:

1. Creates this folder's VM on first use; otherwise starts/reuses it.
2. Mounts the actual folder read/write at the same absolute path.
3. Configures the built-in SSH transport and pins its locally stored host key.
4. Adds it to the local Herdr machine sidebar.
   Select `VM: myproject` there. Launch Pi there; pi-herdr children stay in the VM.
5. Creates or focuses a project-rooted workspace, so Herdr's worktree actions
   work even when older restored workspaces are rooted at the guest home.

The mounted directory includes uncommitted changes and untracked files.
Host and guest processes access the same files. A stable name derived from
the folder path identifies the VM.
Moving the folder selects a different VM.

```bash
pivm --shell   # guest shell instead of Herdr
pivm --attach  # open a dedicated remote Herdr UI instead
pivm /path/to/another/project
```

If the image is missing, the first launch builds it automatically (requires
Docker or Podman). Default resources: 4 vCPUs, 4 GiB RAM, 24 GiB persistent
guest disk; override with `--cpus`, `--memory`, `--disk` when first creating.
Existing VMs retain their original configuration.

Host `OPENAI_API_KEY` and `GH_TOKEN`, when exported before first creation,
are automatically configured as host-held msb secret bindings. They are not
copied into the image. See credential limitations below.

The project mount is writable: agents can change or delete
its files and read secrets inside it, including `.env`. Other host folders
are not automatically mounted. Linked Git worktrees also expose their Git
common directory so existing `.git` references work; this grants access to
shared repository metadata.

## Image

```bash
cd /path/to/microvm
bin/build-pi-vm
```

Builds and imports `pi-vm:local`. OS packages come from signed official Arch
repositories. Node 25.2.1, Pi 1.4.0, Herdr 0.9.5, and the extension dependencies are
pinned. Arch packages are rolling, not snapshot-pinned. See
[image inputs and limitations](images/pi-vm/NOTES.md).

### Rebuild / update

Rebuild and reimport the image after editing its inputs:

```bash
cd /path/to/microvm
bin/build-pi-vm
```

To pull the configured base and refresh Arch packages, bypass the build cache:

```bash
bin/build-pi-vm --pull --no-cache
```

Additional arguments are passed to Docker/Podman's `build`. Pi/extensions are
pinned in `images/pi-vm/package.json` and `package-lock.json`; rebuilding alone
does not upgrade them. Version changes require updating both files. Node and Herdr
versions/checksums are pinned in `images/pi-vm/Dockerfile`; update each version
and its verified checksum together.
The base image is also pinned by digest; `--pull` does not change that pin.

Rebuilding does not update an existing VM's disk. To use the rebuilt image
while retaining the existing VM, create a VM with a different name:

```bash
cd /path/to/myproject
pivm --name myproject-v2
```

This mounts the same host project, but starts with fresh guest tools, home,
sessions and configuration. Both VMs can modify the same mounted checkout.
Credentials must be provisioned separately for the new VM.

Alternatively, find the old VM with `msb list`, then remove it and rerun `pivm`:

```bash
msb list
msb remove --force EXACT_VM_NAME
pivm
```

Removal destroys the VM's guest-only files, including guest-home
worktrees, auth, installed tools and session history. It does not remove the
host-mounted project. Removing a running VM also terminates its processes.

Updating msb itself is separate (`msb update`); it does not rebuild this image.
This setup was tested with the versions listed above.

Included: Git, gh, ripgrep, fd, jq, Python, base-devel, mise, Vim, Node, Pi and
Herdr. Add project toolchains inside the guest with mise, or extend the image.
Mise shims are on PATH; no unreviewed project mise config is automatically
trusted. No desktop services, other coding agents, sudo, or personal credentials.

The extension manifest pins the included packages; it does not mount the host home.
It includes pi-herdr, pi-herdr-btw, codex tools/usage/compaction helpers,
pi-web-access, Nord, daybreak and reset-usage-limit. Host desktop extensions,
auth.json, browser cookies, provider secrets and arbitrary local config are
not copied. Web providers needing keys require separate scoped provisioning.

## Guest-only checkout

The `create` command stores the checkout on the guest disk without mounting
the host project.

### Clone from GitHub

The `--openai` and `--github` flags read credentials from the host environment:

```bash
# Requires OPENAI_API_KEY and GH_TOKEN in the host environment.
pivm create myproject --openai --github \
  --clone https://github.com/OWNER/REPO.git
```

Public repositories can be cloned without credentials:

```bash
pivm create experiment --clone https://github.com/OWNER/PUBLIC-REPO.git
```

### Import a local Git checkout

```bash
pivm create myproject --openai --github \
  --import /path/to/myproject --origin https://github.com/OWNER/REPO.git
```

Imports HEAD and its reachable commit history through a Git bundle, then
creates guest branch `work`. It does not copy host Git configuration, hooks,
uncommitted changes, untracked/ignored files, sibling branch refs or credentials.
The bundle includes any secrets present in the imported commit history.
LFS objects and submodule checkouts are not included in the bundle and need
separate guest fetching. An initial empty/unborn repository cannot be bundled.

For these explicit `create` commands, projects live at `/workspace/project` on
the guest's persistent disk, without automatic synchronization or a host
bind mount. Default resources are
4 vCPUs, 4 GiB RAM, 24 GiB root disk, configurable at create time.

For an already-created empty VM:

```bash
pivm import myproject /path/to/myproject --origin https://github.com/OWNER/REPO.git
pivm clone myproject https://github.com/OWNER/REPO.git
```

Neither overwrites an existing project. On a failed initial clone/import, the
VM remains available for inspection; it is not automatically deleted.

### Other project files

Copy files with `msb copy`:

```bash
msb copy ./fixtures myproject:/workspace/fixtures
```

msb copy may create root-owned files. To make an explicitly copied directory
writable, change its guest ownership:

```bash
msb exec --no-stdin --user root myproject -- chown -R dev:dev /workspace/fixtures
```

Copied files are accessible to guest processes, including credentials or
secrets in those files. msb also supports read-only mounts. The folder
launcher uses a read/write mount.

## Credentials: OpenAI and GitHub

The folder launcher binds exported `OPENAI_API_KEY` / `GH_TOKEN`
automatically when creating the VM. The `create` command uses
explicit `--openai` / `--github` flags:

| Host variable | Guest sees | Injection destinations |
| --- | --- | --- |
| `OPENAI_API_KEY` | `$MSB_OPENAI_API_KEY` | `api.openai.com`, Authorization only |
| `GH_TOKEN` | `$MSB_GH_TOKEN` | `github.com`, `api.github.com`, Authorization only |

Only host environment source names are saved in VM configuration. No raw
keys are passed in argv or baked into the image. msb enables TLS inspection
and supplies its public CA to Node and system trust bundles. Credential
substitution depends on interception at the configured destinations.

Restarting a stopped VM requires these variables on the host again. A
running VM retains its loaded bindings; an already-running guest does not
automatically rotate when the host environment changes. To rotate, stop it,
load the new credentials, and start it again.

### OpenAI authentication

The launcher supports Pi's `openai` API-key provider:

```bash
pivm pi myproject -- --model openai/gpt-5.4
```

Or choose an available `openai/...` model in guest Pi, then use pi-herdr there.
Host provider/model defaults are not copied. API-key usage is billed
separately from a ChatGPT subscription.

ChatGPT login is different from an OpenAI API key. The current launcher does
not automatically reuse host Pi login. Traditional `openai-codex` OAuth decodes
a JWT inside Pi, so an opaque msb placeholder is not a drop-in token.

Reusing host login is technically possible without removing VM isolation, but
it gives guest processes the real credential. A writable auth mount also lets
them modify host auth; a read-only mount can interfere with refresh persistence.
A guest copy avoids host-file writes but can diverge from the host login.
Automatic auth sharing and OAuth refresh coordination are not implemented.

### GitHub

The GitHub token requires repository contents read permission for clone/fetch
and write permission for push. PR, issue and workflow operations require their
corresponding permissions.

The guest Git credential helper supplies the placeholder through HTTPS Basic
auth; msb rewrites it outside the VM. The helper does not store credentials.
`gh` uses `GH_TOKEN` directly, without `gh auth login`.

```bash
# Inside the guest:
git -C /workspace/project fetch origin
git -C /workspace/project push -u origin work
gh pr create --repo OWNER/REPO
```

The launcher accepts credential-free GitHub HTTPS URLs. Guest Git author
name/email are configured separately. LFS, package registries and additional
GitHub APIs may require additional credential destinations.

Credential concealment does not prevent authorized API usage, spending, or
source disclosure to an allowed endpoint. Defaults allow public internet
egress (including dependency registries), not an exfiltration-proof allowlist.
Host/private network access is not enabled by this launcher.

msb can reject a request to OpenAI that contains a GitHub placeholder.
Its secret options support unchanged-placeholder passthrough without
credential injection.

## SSH and native Herdr

msb's host-side SSH server bridges commands and PTYs
to the guest agent. OpenSSH can use it through `ProxyCommand ... --stdio`.
Herdr 0.9.5's exec/stdio remote bridge works with this transport; guest sshd
and SSH Unix-socket forwarding are not required.

The `pivm` launcher configures SSH automatically:

- Creates a dedicated, unencrypted local-transport key under
  `~/.local/state/pivm/ssh/`.
- Authorizes its public key in `$MSB_HOME/ssh/authorized_keys`.
- Writes a host-specific config there and prepends its Include to
  `~/.ssh/config`; retains the original config once as `ssh-config.before-pivm`.
- Disables SSH-agent and TCP forwarding for that alias.

The launcher pins the public host key directly from this local msb sandbox's
key file into its own `known_hosts`. No interactive host-key approval or
disabled host-key checking is needed.
The transport authorization file is shared across sandboxes in the same
MSB_HOME, not a per-VM key ACL. Keep its private key host-only.

Inspect without configuring SSH:

```bash
pivm ssh-config myproject
```

For guest-only VMs, configure SSH and connect with:

```bash
pivm setup-ssh myproject
pivm connect myproject
```

Or register one in the local Herdr sidebar:

```bash
pivm register myproject
```

Select `VM: myproject` in local Herdr. Guest panes, Pi, pi-herdr child spawning,
worktrees and session/result files all live inside that VM. Selecting it does
not retarget a Pi process still running in a local host pane.

### Launching from Herdr

Run `pivm` in the project folder in a local pane.
It prepares the VM and adds it to the local Herdr machine sidebar.
The `pivm --attach` option opens a dedicated remote UI.

For a stopped VM, load the host credentials and run:

```bash
pivm start myproject
```

Native SSH reconnect can auto-start a VM, but its process must have the required
host credential environment. A desktop-launched Herdr server may not have
variables exported later in a terminal. Starting through `pivm` from a terminal
with the required variables makes them available to the VM runtime.
No host Herdr keybindings/plugins are changed automatically.

### Worktree troubleshooting

Herdr worktree actions require the selected remote workspace to be rooted in
a Git checkout. A restored workspace at `/home/dev` is not a repository, even
if this VM was launched for a mounted project. The launcher creates or
focuses a project-rooted workspace without changing existing home workspaces.
Rerun `pivm`, then select the project workspace before using worktree actions.

If configuring manually, create a correctly rooted workspace from a guest terminal:

```bash
herdr --session agents workspace create \
  --cwd /path/to/myproject --label myproject --focus
```

Then use Herdr's worktree action there. For diagnosis:

```bash
herdr --session agents worktree list --cwd /path/to/myproject
```

Default guest worktree checkouts live under `/home/dev/worktrees`, on the
guest's disk, not alongside the host project. The shared `.git` metadata can
therefore reference paths that exist only in the guest. Deleting the VM
deletes those checkouts but leaves their registration in the shared Git
metadata. An explicitly configured sibling path outside the project mount
may not be writable.

Other lifecycle commands:

```bash
pivm shell myproject
pivm stop myproject          # preserves disk; terminates all guest processes
pivm start myproject         # does not resume process memory
pivm export myproject /path/to/review-myproject  # new destination only
```

Exported files and commits pushed from the guest can contain guest-generated
code and configuration.

## Security boundary and limitations

- Guest environment has a separate kernel, but the mounted project is exposed
  read/write. Workers inside one VM are not individually VM-isolated.
  Guest herdr socket access controls guest peers.
- `isolated: true` in pi-herdr is a Git worktree, not a separate VM.
- Non-root `dev` + msb restricted profile; no host sockets or credential mounts.
- Persistent VMs retain modifications. Rebuilding the image does not update
  an existing root disk.
- No automatic OAuth broker, credential-manager integration,
  global cross-VM worker quota, or project-specific service exposure.
- Host msb/KVM/VMM and network/SSH mediation remain trusted.

## Checks

```bash
python -m unittest discover -s tests -v
bash images/pi-vm/test.sh
```

Integration observations and remaining tests are recorded in
[validation](docs/validation.md). These are not a security audit.

## msb Bash completions

msb includes a completion generator. Enable it for the current Bash session:

```bash
source <(msb completion bash)
```

Or install the generated script for Bash's completion loader:

```bash
mkdir -p ~/.local/share/bash-completion/completions
msb completion bash > ~/.local/share/bash-completion/completions/msb
```

The persistent form requires the shell's `bash-completion` loader to be
enabled. Regenerate after updating msb. Fish, Zsh, Elvish and PowerShell are
also supported (`msb completion --help`).

## References

- [msb SSH CLI](https://docs.microsandbox.dev/cli/ssh-commands)
- [msb SSH transport](https://docs.microsandbox.dev/sandboxes/ssh)
- [msb secret configuration](https://docs.microsandbox.dev/sandboxes/secrets)
- [msb secret security boundary](https://docs.microsandbox.dev/security/secrets)
- [Herdr machines](https://herdr.dev/docs/connecting-machines/)
