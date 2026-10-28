# Validation — 2026-10-26

## Fresh rebuild and acceptance run — 2026-10-28

- Removed the old `dev-microvm-62ff4c96` VM and its saved Herdr profile at the
  user's request. The host project was preserved.
- Ran `bin/build-pi-vm --pull --no-cache`, successfully imported
  `sha256:87e8078cb06f1038b83077fe30cd111c0e0ca489bffeb80e84e4cda91fd600f1`,
  and created a fresh project VM.
- Subsequently changed the requested guest worktree directory to
  `/home/dev/worktrees` in both the image input and the running VM, reloaded
  guest Herdr configuration without stopping user panes, and rebuilt/imported
  the final image:
  `sha256:b110ed134df2b1fddab69598ce2892617f6df3a916dc95af004fc70caf1a5923`.
  The running project VM keeps its first rebuilt root disk with the same
  worktree configuration applied; the final image was boot-tested separately.
- Fresh VM: guest kernel `6.12.113`, non-root UID/GID 1000, restricted profile,
  only the requested project mounted. No Pi auth file, host SSH directory or
  Docker socket exposed.
- Node 25.2.1, Pi 1.4.0, Herdr 0.9.5, Git/gh/rg/fd/jq/Python/cc/mise present.
- Offline Pi RPC `get_state` and `get_commands` succeeded, including the
  pi-herdr `subagents` command. Interactive Pi startup through guest Herdr
  reached `idle` / `interactive_ready=true`, with no extension-loading errors.
  Its temporary workspace was closed and test files removed.
- Created and removed a real Herdr worktree under
  `/home/dev/worktrees/microvm/`; removed its temporary branch afterward.
  Preserved the user's existing `wttest` checkout at its original path.
- Repeated project launches preserved the existing machine profile ID,
  focused the project workspace, and did not accumulate sidebar entries.
- Booted a disposable acceptance VM from the final image. Verified first-use
  SSH without approval prompts, uncommitted host-file reads, immediate
  guest-to-host writes, final worktree directory configuration, and absence
  of provider auth.
- HTTPS to the npm registry returned 200; public GitHub `git ls-remote`
  succeeded without disabling TLS verification.
- Stopped and started that disposable VM: guest-home marker, project mount
  contents and SSH trust survived. Removed it, its temporary project/home,
  and only its specific SSH authorization afterward. The user's project VM
  was not restarted during this last check.
- All 20 unit tests, image/static wrapper tests, and `git diff --check` pass.

**Not a completed authenticated agent test:** guest Pi reports
“No models available. Use /login”. ChatGPT login reuse has not been
implemented/provisioned, so no inference or model-driven pi-herdr child
spawning/messaging/cancellation/resume was tested. No real credentials were
read/copied, and no billable model request was made.

Build logs: `/tmp/pi-vm-fresh-build.log` and
`/tmp/pi-vm-worktree-path-build.log` (temporary host logs).

## Earlier baseline

Branch: `feat/pi-herdr-msb`. Host: Linux x86-64, msb 0.7.11,
libkrunfw 5.6.1, Herdr 0.9.5. Not a security audit.

## Automated offline checks

- `python -m unittest discover -s tests -v`: 20 tests passed.
- `bash images/pi-vm/test.sh`: passed.
- `git diff --check`: passed.

These cover command construction, opt-in credential references rather than
raw argv values, GitHub URL validation, Git bundle content exclusions, SSH
configuration, atomic/symlink-preserving writes, idempotent startup, pinned
package metadata, Git credential helper protocol, shell configuration, and
mocked build/load behavior. They do not replace runtime checks.

## Real image and private-checkout VM checks

This first test exercised the optional guest-only checkout mode, not the
current default live-folder launcher.

`bin/build-pi-vm` completed successfully and imported `pi-vm:local`.
A disposable `pivm-smoke` was created with **distinct dummy credentials only**,
no host mounts and no published ports.

Verified in the guest:

- UID/GID 1000 (`dev`), HOME `/home/dev`.
- Node 25.2.1; Pi 1.4.0; Herdr 0.9.5.
- mise, Python and the C compiler execute in the final image.
- OpenAI and GitHub environment variables equal their expected placeholders,
  not dummy raw credentials.
- `NODE_EXTRA_CA_CERTS` names an existing injected certificate.
- No `/home/dev/.pi/agent/auth.json`.
- Saved msb configuration contains environment-source references and empty
  raw secret value fields, not the distinct dummy values.
- No configured host mounts.
- Pi RPC `get_state` in offline mode succeeded with `openai/gpt-5.4`;
  extension initialization emitted no loading errors. No model call was made.

### Network

- Node fetch to OpenAI with the dummy key returned HTTP 401 without a TLS
  verification bypass.
- `gh api user` with the dummy GitHub token returned HTTP 401.
- Public GitHub HTTPS `git ls-remote` succeeded.

These establish TLS and request connectivity, **not successful authentication**.
401 alone cannot prove that a header was substituted: an unreplaced or absent
credential can also return 401. Guest placeholders and persisted references
were checked separately; upstream's substitution implementation remains trusted.
No real credential or billable inference request was used.

### Project transfer and persistence

- Imported local Git HEAD/history through a bundle.
- Guest clone owned by `dev`; transient import staging directory removed.
- Ignored image archive was absent from guest checkout.
- A guest marker and imported project survived VM stop/start.
- Restart used dummy host variables again, not credentials stored in a file.

An initial implementation copied the bundle into sticky `/tmp`, where
root-owned `msb copy` output could not be removed by dev. The launcher now
creates a unique dev-owned staging directory under `/workspace`.

### SSH and native Herdr

Tested actual external OpenSSH through:

```text
ProxyCommand msb ssh serve pivm-smoke --stdio --no-inactivity-timeout
User dev
```

- SSH exec returned dev's identity, HOME and injected CA environment.
- Native host `herdr machine add` prepared a guest `smoke` session.
- Native `herdr --machine Smoke agent list` returned the remote agent list.
- The test used a disposable SSH key and temporary SSH/Herdr client config.
  First-use host trust was accepted only into a temporary known_hosts file for
  this locally created test endpoint, not the user's normal trust store.
- Temporary public-key authorization was removed after the test.
- The temporary Smoke machine record was subsequently found in the real
  machine catalog despite temporary client config, and explicitly removed.
  No user-owned machine record was modified.

This confirms Herdr's native exec/stdio bridge works; it does not depend on
SSH Unix-socket forwarding or guest sshd.

## Default live-folder launcher

Created a disposable `pivm-launch-smoke` through `pivm DIRECTORY
--prepare-only`, using a temporary host HOME and a real read/write project
mount. No provider credentials were passed.

- Missing VM was created from the cached image automatically.
- Dedicated SSH key, config Include and local-file host-key pinning were
  prepared automatically, without an interactive approval step.
- External `ssh -o BatchMode=yes` succeeded on the first connection.
- Guest working directory matched the host project absolute path.
- An uncommitted host file was immediately readable inside the guest.
- A guest write immediately appeared in the host directory.
- Guest Herdr 0.9.5 and Pi executable were available.
- Running the launcher again from that folder without a directory argument
  reused the same VM successfully.
- Unit tests check default sidebar registration without a second UI and
  explicit `--attach` for the native Herdr attach command. A full interactive
  Herdr UI attach was not exercised in this test.

The test sandbox, temporary files and its specific public-key authorization
were removed. Existing user SSH configuration and authorization were preserved.

## Remaining acceptance checks

### Worktree regression check

The user's restored `agents` session had two workspaces rooted at `/home/dev`.
The updated launcher created a project-rooted workspace without closing or
changing those panes. Repeated launches reused that workspace and retained
the original saved machine profile rather than accumulating duplicate entries.

In the real guest, Herdr successfully created and removed a disposable worktree
under `/home/dev/.herdr/worktrees/microvm/`. Its temporary branch was deleted
afterward. The mounted source checkout and user workspaces were preserved.

### Still outstanding

- Real, scoped GitHub PAT: private clone/fetch, push and required PR operations.
- Real OpenAI API key and desired model: authenticated inference.
- Complete interactive Pi TUI keyboard/resize behavior through remote Herdr.
- pi-herdr child creation, result retrieval, messaging, cancellation and resume
  in that interactive session with the actual desired provider.
- Long-running reconnect behavior and host secret-manager integration.
- Provider-specific Web Access keys/configuration if needed.
- OAuth/subscription credential lifecycle: **not implemented**.

The disposable smoke VM is removed after testing. The built image remains
cached for use. Rebuilding an image does not update existing VM root disks.
