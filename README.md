# Pi + Herdr in a microsandbox VM

An Arch development environment with Pi, extensions and guest Herdr.
Microsandbox supplies a separate guest kernel. Local Herdr connects through
msb's built-in SSH transport: no guest SSH daemon, published SSH port or
shared host socket.

**Requirements:** Linux x86-64 with writable `/dev/kvm`, msb **0.7.11**,
Herdr **0.9.5**, Python 3, Git and OpenSSH client/keygen. Building also requires
Docker or Podman. No host desktop configuration is changed.

## Quick start

Add this repository's `bin` directory to your host shell's PATH:

```bash
export PATH="/path/to/microvm/bin:$PATH"
```

Choose a backend when opening a project. The default is Herdr Core;
`--backend legacy` selects the old Herdr flow. Core registers the VM as a
Herdr Core machine using msb's
bidirectional byte-stream transport (no VM SSH service, key, or SSH config):

```bash
cd /path/to/myproject
pivm                              # Herdr Core / desktop app
pivm --backend legacy            # legacy Herdr sidebar
```

The launcher creates or starts a VM and mounts the project read/write at its
original absolute path. Legacy mode configures SSH and registers **VM:
myproject** in the local Herdr sidebar. Core mode runs `hc machine add --via`
through `msb exec --stream`; select `vm-<vm-name>` in Herdr Core/the desktop
app. Each VM records its backend at creation; choose another VM name to use
both backends for the same project.
Guest Pi, child agents, worktrees and sessions stay inside the VM.

Generated VM names use a short project slug plus a six-character path hash,
for example `plantmonitoring-148d8c`. Core machine names are capped at its
32-character limit, including the `vm-` prefix; long custom names get a
hashed suffix. The launcher prints the exact Core name to select.
Existing VMs are not renamed: reopen an older generated VM explicitly with
`pivm --name dev-plantmonitoring-148d8ce8` to keep its disk and sessions.
Otherwise the new naming scheme creates a separate VM on the next launch.

New project VMs automatically sync supported host Pi preferences (including the
model list), packages, personal resources and Git identity before opening the
session. This uses the same scope and safety exclusions as `pivm sync` below.
Use `pivm --no-sync` to skip the initial copy. Reopening an existing VM does not
sync again. If initial sync fails, the VM remains available; run the printed
`pivm sync` command on the host before reopening it.

Use `msb list` to find the generated VM name, then refresh configuration later:

```bash
pivm sync VM_NAME --backend legacy --dry-run
pivm sync VM_NAME --backend legacy
```

Use `--backend core` to sync `@howaboua/pi-shepherdr` instead of legacy
`pi-herdr`; the default is Core. This selection should match the backend used
to open the VM. Start Pi inside the guest and use **`/login` once per VM**.
Login and session data persist on the guest disk; host Pi auth is never copied
or mounted.

```bash
pivm --shell                    # guest shell instead of sidebar registration
pivm --attach                   # dedicated remote legacy Herdr UI
pivm /path/to/another/project
pivm --name myproject-v2         # separate VM for the same folder
```

Default resources are **4 vCPUs, 4 GiB RAM and 24 GiB persistent disk**.
Set `--cpus`, `--memory` or `--disk` at creation time. The folder path determines
the default VM name; moving it selects a different VM. If the image is absent,
the launcher builds it automatically.

The project mount includes uncommitted and untracked files. Linked Git
worktrees also expose their common Git directory so `.git` references work.
Agents can read, change or delete files and secrets in these mounted paths.

## Pi configuration sync and Git commits

Sync is a one-way host-to-guest copy, not a live mount. It runs automatically
once when `pivm` creates a project VM (unless `--no-sync` is passed); use
`pivm sync` explicitly for later updates or existing VMs. Its
default backend is Core; pass `--backend legacy` for legacy Herdr. It syncs
host-declared Pi packages at their installed versions and selects the matching
orchestration extension. Stop Pi, sync, then restart it. Do not load both
`pi-herdr` and `pi-shepherdr` in the same Pi session.
Run it after creation and whenever host preferences or extensions change:

```bash
pivm sync VM_NAME
pivm sync VM_NAME --directory /path/to/myproject
```

`--directory` selects the host project used to resolve Git identity; it defaults
to the current directory. Stop guest Pi before syncing to avoid concurrent
settings edits, then restart it. `--dry-run` lists files/packages without
starting or contacting the VM. Updating the host-side helper needs no image
rebuild.

### What sync copies

- Supported personal Pi preferences, including model defaults and theme.
- Declared npm packages, installed independently in the guest at their installed
  host versions. Git package declarations are retained, with an unpinned warning
  where applicable.
- Personal extensions, skills, prompts and themes, including supported explicit
  resource paths relocated into guest-local directories.
- Effective host project `user.name` and `user.email` into guest-global Git
  configuration, with `user.useConfigOnly=true` and `commit.gpgsign=false`.

It does **not** copy auth, sessions, `models.json`, MCP configuration, credential
stores, host `node_modules`, signing keys, Git hooks or the full host Git config.
Guest credential helpers are preserved. Repository-local Git configuration can
override guest globals; sync never edits a mounted repository's `.git/config`.
Creating commits needs no remote credentials; fetch/push authentication is
separate.

### Ownership, backups and limits

Supported preferences and incoming resources are host-authoritative. Existing
Pi files/settings are backed up under `~/.pi/agent/.pivm-sync-backups/`; ownership
is tracked in `~/.pi/agent/.pivm-sync.json`. Removed host resources are deleted
in the guest only if previously synced and unchanged. Guest-created resources
are not removed. Installed package files may remain after their declarations
are removed. Backups can be removed manually when no longer needed.
Guest-global Git settings are updated without a backup.

Symlinks, local package sources, positive resource globs, dependency directories
and common credential filenames are skipped or reported as unsupported.
Filename filtering is **not a content-secret scanner**: review the dry-run
list and resource contents. Desktop extensions, embedded host paths and extra
runtime dependencies may require adaptation. Arbitrary extension-specific
settings are not automatically copied.

## Included tools and shell

The image includes Pi 1.4.0, Herdr 0.9.5, Node 25.2.1, Hunk 0.24.1,
lazygit, Neovim, Vim, Git, gh, ripgrep, fd, jq, Python, base-devel and mise.
The image includes pi-shepherdr rather than legacy pi-herdr/pi-herdr-btw;
host Pi package declarations are synchronized explicitly and may select a
different integration. Use `pivm sync VM_NAME --backend legacy` before using
the legacy integration. Other pinned image packages include Codex
tools/usage/compaction helpers, pi-web-access, Nord, daybreak and
reset-usage-limit. Pi Codex Conversion is installed with all its resources
disabled, matching the host package snapshot.
Project toolchains can be installed in the guest with mise; unreviewed project
mise configuration is not automatically trusted.

Interactive Bash provides a Starship prompt, bash-completion, fzf
completion/history bindings, and zoxide (`z`):

| Command | Behavior |
| --- | --- |
| `ls`, `ll` | eza long listing, directories first, automatic color/icons |
| `la`, `lsa` | Include hidden files |
| `lt`, `lta` | Two-level tree, optionally including hidden files |
| `lg` | lazygit |
| `ff` | fzf with bat preview |
| `bat` | Syntax-highlighted file viewer; `cat` is not aliased |

Shell defaults are guest-owned. Noninteractive commands do not initialize
interactive aliases or prompts. `EDITOR` and `VISUAL` select `nvim`.

Neovim has no plugin distribution preinstalled. To opt into
[LazyVim](https://www.lazyvim.org/installation), back up any existing Neovim
configuration, then run inside the guest:

```bash
git clone https://github.com/LazyVim/starter ~/.config/nvim
nvim
```

This downloads configuration/plugins and requires network access.

## Build and update

From the repository root:

```bash
bin/build-pi-vm                  # build and import pi-vm:local
bin/build-pi-vm --pull --no-cache # refresh rolling Arch packages
```

Additional arguments go to Docker/Podman `build`. Node, Herdr and Hunk artifacts
are version/checksum-pinned; Pi/extensions are pinned in `package.json` and
`package-lock.json`. Arch packages use signed rolling repositories. `--pull`
does not change the pinned base digest. See [image inputs](images/pi-vm/NOTES.md)
for versions, overrides and reproducibility limits.

Rebuilding does **not** update existing VM disks. Either create a replacement:

```bash
cd /path/to/myproject
pivm --name myproject-v2
```

Or remove the old VM and rerun `pivm`:

```bash
msb list
msb remove --force EXACT_VM_NAME
pivm
```

**Removal destroys guest-only files**, including worktrees, login, tools and
sessions, and terminates guest processes. It does not remove the host-mounted
project. Run sync and log in again in the replacement. Updating msb itself is
separate from rebuilding this image.

## Lifecycle, SSH and worktrees

```bash
pivm shell VM_NAME
pivm pi VM_NAME                  # Pi in /workspace/project
pivm stop VM_NAME                # terminate processes; preserve disk
pivm start VM_NAME               # boot without restoring process memory
pivm ssh-config VM_NAME          # print transport config
pivm export VM_NAME /new/path    # export project; destination must not exist
```

The launcher uses a dedicated transport key and known-hosts file under
`~/.local/state/pivm/ssh/`. It maintains one wildcard Include for that directory
at the top of `~/.ssh/config`, retaining a one-time backup, and authorizes the
key in msb's SSH authorization file. Older per-VM Includes are consolidated
automatically on the next SSH setup; unrelated SSH configuration is preserved.
Per-VM connection files stay in that directory, so new VMs no longer add
lines to the main SSH config. After removing a VM, remove its matching
`NAME.conf` file and saved Herdr machine entry as well.
Host keys are pinned from local sandbox storage; SSH-agent/TCP forwarding are
disabled. Authorization is shared across sandboxes in the same `MSB_HOME`,
not restricted to a single VM. Keep the private transport key host-only.

For guest-only VMs, use `pivm setup-ssh VM_NAME`, followed by
`pivm register VM_NAME` for the sidebar or `pivm connect VM_NAME` for a dedicated
UI. Selecting a remote machine does not retarget an already-running host Pi.

Herdr worktree actions require a workspace rooted in the project, not
`/home/dev`. Rerun `pivm` to create/focus the project workspace, or create one
inside the guest:

```bash
herdr --session agents workspace create \
  --cwd /path/to/myproject --label myproject --focus
```

Guest worktrees live under `/home/dev/worktrees`. With mounted projects, shared
Git metadata can reference guest-only paths. Removing the VM deletes those
checkouts but leaves their registrations in the host repository metadata;
review/prune stale registrations before reusing them.

## Guest-only checkouts

To keep the checkout on the guest disk instead of mounting the host project:

```bash
pivm create myproject --clone https://github.com/OWNER/REPO.git
pivm create myproject --import /path/to/repo \
  --origin https://github.com/OWNER/REPO.git
```

Import transfers HEAD and its reachable history via a Git bundle, creates guest
branch `work`, and excludes host Git config, hooks, other refs, dirty/untracked
files and credentials. Secrets already in history are still included. LFS and
submodule contents require separate fetching; unborn repositories cannot be
bundled. Projects live at `/workspace/project`.

`pivm clone VM_NAME HTTPS_URL` and `pivm import VM_NAME DIRECTORY [--origin URL]`
populate an existing empty VM. Neither overwrites a project; failed creation
leaves the VM available for inspection. Use `msb copy` for additional files;
it may create root-owned files requiring an explicit ownership adjustment.

## Authentication and network access

Pi login is per VM. Use `/login` in guest Pi; configuration sync never reads
host auth. Provider/model preferences alone do not authenticate a guest.
Web Access providers needing keys require separate guest provisioning.

Optionally, msb can inject API credentials outside the guest:

| Host variable | Guest placeholder | Injection destinations |
| --- | --- | --- |
| `OPENAI_API_KEY` | `$MSB_OPENAI_API_KEY` | `api.openai.com`, Authorization |
| `GH_TOKEN` | `$MSB_GH_TOKEN` | `github.com`, `api.github.com`, Authorization |

The folder launcher binds these when exported at first creation. Guest-only
`create` requires explicit `--openai` / `--github` flags. Only environment-source
references are saved; raw keys are not passed in argv or baked into the image.
API-key billing is separate from a ChatGPT subscription.

The guest Git credential helper supplies the GitHub placeholder over HTTPS;
`gh` uses `GH_TOKEN`. Private repositories and push/PR operations require
appropriate token permissions. LFS and other API hosts may need additional
credential destinations.

Starting a stopped VM with bindings requires those host variables again.
Running VMs retain loaded bindings; to rotate, stop the VM, load the new
credentials and start it. A desktop-launched Herdr server may not inherit
variables exported later in a terminal; start via `pivm` from the prepared shell.

msb supplies its CA to system and Node trust; do not disable TLS verification.
Credential concealment does not prevent API spending or disclosure to allowed
destinations. Egress allows public internet access, not an exfiltration-proof
allowlist. Host/private network access is not enabled by the launcher.

## Security and checks

- The guest has a separate kernel, but mounted project/Git paths are writable.
- Workers share one VM. pi-herdr `isolated: true` means a Git worktree, not
  another VM; guest Herdr socket access controls guest peers.
- The guest runs as non-root `dev` under msb's restricted profile, without
  host sockets, host credential mounts, SSH-agent forwarding or sudo.
- Persistent VMs retain modifications. Host msb/KVM/VMM and SSH/network mediation
  remain trusted. Treat exported files and guest-produced commits as untrusted.

Run checks from the repository root:

```bash
python -m unittest discover -s tests -v
bash images/pi-vm/test.sh
git diff --check
```

For host Bash completion, run `source <(msb completion bash)`.

## License

This project is released under [the Unlicense](LICENSE).
Bundled tools and dependencies retain their respective licenses.

## References

- [msb SSH](https://docs.microsandbox.dev/sandboxes/ssh)
- [msb secrets](https://docs.microsandbox.dev/sandboxes/secrets)
- [msb secret security boundary](https://docs.microsandbox.dev/security/secrets)
- [Herdr machines](https://herdr.dev/docs/connecting-machines/)
