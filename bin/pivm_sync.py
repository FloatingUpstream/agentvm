"""Explicit, one-way Pi preference/resource sync. Never reads auth or sessions.

Only personal settings/resources are exported; project files stay in the project.
Local packages, resource globs, custom runtime dependencies and embedded absolute
paths in resource contents are deliberately unsupported. Review executable
resources before syncing. Filename filtering is not a content secret scanner.
"""
import base64
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import subprocess
import sys


RESOURCES = ("extensions", "skills", "prompts", "themes")
# No arbitrary extension settings, endpoints, shell commands, trust, proxy,
# session paths, MCP or model configuration: these can contain host secrets.
PREFERENCES = set("""
defaultProvider defaultModel defaultThinkingLevel modelThinkingLevels
thinkingBudgets enabledModels hideThinkingBlock showCacheMissNotices
steeringMode followUpMode doubleEscapeAction treeFilterMode
compaction branchSummary theme quietStartup tuiMode fullscreenExitOutput
fullscreenScrollbar fullscreenCopyOnSelect fullscreenWheelScrollLines
editorPaddingX outputPad autocompleteMaxVisible showHardwareCursor terminal
images markdown retry collapseChangelog enableSkillCommands enableAnalytics
enableInstallTelemetry warnings
""".split())
BLOCKED = re.compile(
    r"(^\.env($|\.)|auth|credential|secret|token|password|^id_|"
    r"\.(pem|key|p12|pfx|kdbx)$)", re.I)
SKIP = {"node_modules", ".git", ".ssh", ".aws", "sessions", "__pycache__"}
MAX_FILE = 4 * 1024 * 1024
MAX_TOTAL = 32 * 1024 * 1024
LEGACY_PACKAGES = {
    "@andrewjacop/pi-herdr": "npm:@andrewjacop/pi-herdr@0.6.0",
    "pi-herdr-btw": "npm:pi-herdr-btw@0.3.1",
}


def warn(message):
    print(f"pivm sync: warning: {message}", file=sys.stderr)


def safe_host(path, package_manifest=False):
    """Check every lexical ancestor before opening anything (no symlink reads)."""
    path = Path(os.path.abspath(path))
    return all(not p.is_symlink() and not BLOCKED.search(p.name)
               and (p.name not in SKIP or
                    (package_manifest and p.name == "node_modules"))
               for p in (path, *path.parents))


def read_json(path, package_manifest=False):
    if not safe_host(path, package_manifest=package_manifest):
        raise ValueError(f"unsafe configuration path: {path}")
    return json.loads(path.read_text()) if path.exists() else {}


def pin_package(entry, agent):
    source = entry.get("source") if isinstance(entry, dict) else entry
    if not isinstance(source, str):
        warn("invalid package declaration skipped")
        return None
    if source.startswith("npm:"):
        spec = source[4:]
        name = spec.rsplit("@", 1)[0] if "@" in spec[1:] else spec
        if not re.fullmatch(r"(?:@[a-zA-Z0-9_.-]+/)?[a-zA-Z0-9_.-]+", name):
            warn(f"unsupported npm source: {source}")
            return None
        # Pi's personal managed npm prefix. Never copy its node_modules.
        manifest = agent / "npm" / "node_modules" / name / "package.json"
        try:
            version = read_json(manifest, package_manifest=True).get("version", "")
        except (ValueError, OSError):
            version = ""
        if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?", version):
            warn(f"cannot pin {source}: installed package.json unavailable")
            return None
        source = f"npm:{name}@{version}"
    elif source.startswith(("git:", "https://", "http://", "git@")):
        # Avoid accidentally transporting URL-embedded credentials.
        if re.search(r"://[^/]*@", source) or "?" in source:
            warn("credential-bearing/query package URL skipped")
            return None
        if not re.search(r"@[A-Za-z0-9_.-]+$", source.split("://")[-1]):
            warn(f"unpinned git package preserved: {source}")
    else:
        warn(f"local/unsupported package skipped: {source}")
        return None
    if isinstance(entry, dict):
        result = {"source": source}
        for key in (*RESOURCES, "autoload"):
            if key in entry:
                if key in RESOURCES and (not isinstance(entry[key], list) or any(
                        not isinstance(f, str) or f.lstrip("!+-").startswith(("/", "~"))
                        or ".." in Path(f.lstrip("!+-")).parts for f in entry[key])):
                    warn(f"unsupported package resource filter; skipped {source}")
                    return None
                result[key] = entry[key]
        return result
    return source


def build_payload(directory, backend="core"):
    if backend not in ("legacy", "core"):
        raise ValueError(f"unknown Pi/Herdr backend: {backend}")
    agent = Path(os.path.abspath(os.path.expanduser(
        os.environ.get("PI_CODING_AGENT_DIR", "~/.pi/agent"))))
    settings = read_json(agent / "settings.json")
    prefs = {k: v for k, v in settings.items() if k in PREFERENCES}
    files = {}
    executable_files = []
    total = 0

    def collect(src, dest):
        nonlocal total
        if not safe_host(src):
            warn(f"unsafe/symlink resource skipped: {src}")
            return False
        if src.is_dir():
            for child in sorted(src.iterdir()):
                collect(child, dest / child.name)
            return True
        if not src.is_file():
            warn(f"missing/nonregular resource skipped: {src}")
            return False
        size = src.stat().st_size
        if size > MAX_FILE or total + size > MAX_TOTAL:
            warn(f"resource size limit, skipped: {src}")
            return False
        content = src.read_bytes()
        total += len(content)
        files[dest.as_posix()] = base64.b64encode(content).decode("ascii")
        if src.stat().st_mode & 0o111:
            executable_files.append(dest.as_posix())
        return True

    for kind in RESOURCES:
        auto = agent / kind
        if auto.exists():
            collect(auto, Path(kind))
        refs = []
        for ref in settings.get(kind, []):
            if not isinstance(ref, str):
                warn(f"invalid {kind} reference skipped")
                continue
            prefix = ref[0] if ref[:1] in ("+", "-", "!") else ""
            raw = ref[len(prefix):]
            if raw.startswith("builtin:") and kind == "extensions":
                refs.append(ref)
                continue
            if prefix in ("-", "!"):
                excluded = Path(os.path.abspath(os.path.expanduser(
                    raw if raw.startswith(("/", "~")) else str(agent / raw))))
                try:
                    relative = excluded.relative_to(agent)
                    if relative.parts[0] != kind:
                        raise ValueError()
                    refs.append(prefix + "./" + relative.as_posix())
                except ValueError:
                    warn(f"external resource exclusion skipped: {ref}")
                continue
            if any(c in raw for c in "*?[]"):
                warn(f"unsupported resource filter skipped: {ref}")
                continue
            src = Path(os.path.expanduser(raw))
            src = Path(os.path.abspath(src if src.is_absolute() else agent / src))
            # Keep conventional locations stable, relocate external resources.
            try:
                relative = src.relative_to(agent)
                if relative.parts[0] != kind:
                    raise ValueError()
                dest = relative
            except ValueError:
                tag = hashlib.sha256(str(src).encode()).hexdigest()[:12]
                dest = Path(kind) / f"pivm-{tag}" / src.name
            if collect(src, dest):
                refs.append(prefix + "./" + dest.as_posix())
        prefs[kind] = refs
    packages = []
    for entry in settings.get("packages", []):
        pinned = pin_package(entry, agent)
        if pinned is None:
            continue
        source = pinned.get("source") if isinstance(pinned, dict) else pinned
        name = source[4:].rsplit("@", 1)[0] if source.startswith("npm:") else ""
        # The host's selected integration should follow the VM backend, never
        # leave both delegation extensions active in the same Pi session.
        if backend == "legacy" and name == "@howaboua/pi-shepherdr":
            continue
        if name in LEGACY_PACKAGES and (backend == "core" or backend == "legacy"):
            continue
        packages.append(pinned)
    if backend == "legacy":
        packages.extend(LEGACY_PACKAGES.values())
    prefs["packages"] = packages
    if any(name.startswith("extensions/") for name in files):
        warn("copied extensions may require host-only desktop services or "
             "dependencies; resource contents are not rewritten")
    identity = {}
    for key in ("user.name", "user.email"):
        result = subprocess.run(["git", "-C", str(directory), "config", "--get", key],
                                capture_output=True, text=True, check=False)
        if result.returncode == 0 and result.stdout.strip():
            identity[key] = result.stdout.strip()
        else:
            warn(f"host project has no {key}; guest identity left unchanged "
                 "(user.useConfigOnly will be enabled)")
    return {"settings": prefs, "files": files, "identity": identity,
            "executable_files": executable_files}


def guest_apply(payload):
    """Self-contained guest program; tests invoke it only in temporary homes."""
    import base64
    import hashlib
    import json
    import os
    from pathlib import Path
    import re
    import shutil
    import subprocess
    import tempfile
    import uuid

    home = Path.home()
    root = home / ".pi" / "agent"
    kinds = {"extensions", "skills", "prompts", "themes"}

    def checked(path):
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError(f"refusing guest symlink: {path}")
        return path

    checked(root)
    root.mkdir(parents=True, exist_ok=True)
    manifest = checked(root / ".pivm-sync.json")
    old = json.loads(manifest.read_text()) if manifest.exists() else {}
    settings_path = checked(root / "settings.json")
    current = json.loads(settings_path.read_text()) if settings_path.exists() else {}
    backup = checked(root / ".pivm-sync-backups" / uuid.uuid4().hex)

    def save_backup(path):
        if path.exists():
            dest = checked(backup / path.relative_to(root))
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)

    def write(path, data):
        checked(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".pivm-")
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    def resource(name):
        parts = Path(name).parts
        if (not parts or parts[0] not in kinds or len(parts) < 2
                or ".." in parts or Path(name).is_absolute()
                or any(re.search(r"(^\.env($|\.)|auth|credential|secret|token|password|"
                                 r"^id_|\.(pem|key|p12|pfx|kdbx)$)", p, re.I)
                       or p in {"node_modules", ".git", ".ssh", ".aws", "sessions"}
                       for p in parts)):
            raise ValueError(f"invalid manifest resource: {name}")
        path = checked(root / name)
        if path.exists() and not path.is_file():
            raise ValueError(f"nonregular guest resource: {name}")
        return path

    def digest(data):
        return hashlib.sha256(data).hexdigest()

    # Validate all paths before mutation. Never follow guest-side symlinks.
    for name in set(payload["files"]) | set(old.get("files", {})):
        resource(name)
    executables = set(payload.get("executable_files", []))
    if not executables.issubset(payload["files"]):
        raise ValueError("executable resource missing from payload")
    owned = {}
    for name, encoded in payload["files"].items():
        path = resource(name)
        data = base64.b64decode(encoded, validate=True)
        if not path.exists() or path.read_bytes() != data:
            save_backup(path)
            write(path, data)
        os.chmod(path, 0o700 if name in executables else 0o600)
        owned[name] = digest(data)
    for name, previous_hash in old.get("files", {}).items():
        if name not in owned:
            path = resource(name)
            if path.is_file() and digest(path.read_bytes()) == previous_hash:
                save_backup(path)
                path.unlink()
            elif path.exists():
                print(f"pivm sync: retained guest-modified resource: {name}")

    # Merge preferences, relinquishing stale keys only if unchanged by guest.
    for key, previous in old.get("settings", {}).items():
        if key not in payload["settings"] and current.get(key) == previous:
            current.pop(key, None)
    current.update(payload["settings"])
    save_backup(settings_path)
    # Install sources on the guest, never transfer host node_modules. pi install
    # may modify settings, so restore our merged settings after each invocation.
    try:
        for entry in payload["settings"].get("packages", []):
            source = entry["source"] if isinstance(entry, dict) else entry
            subprocess.run(["pi", "install", source], check=True,
                           env={**os.environ, "PI_CODING_AGENT_DIR": str(root)})
    finally:
        write(settings_path, (json.dumps(current, indent=2) + "\n").encode())
    # Scope all identity writes to guest global config; preserve helpers/signing
    # keys. Never copy host .gitconfig, includes, SSH config, or credentials.
    checked(home / ".gitconfig")
    checked(home / ".config" / "git" / "config")
    for key, value in {**payload["identity"], "commit.gpgsign": "false",
                       "user.useConfigOnly": "true"}.items():
        subprocess.run(["git", "config", "--global", key, value], check=True)
    save_backup(manifest)
    write(manifest, (json.dumps({"files": owned, "settings": payload["settings"]},
                               indent=2) + "\n").encode())
    print(f"pivm sync: synced {len(owned)} resource files")


def sync(msb, name, directory, dry_run=False, backend="core"):
    """Export host preferences/resources; dry-run never contacts the VM."""
    payload = build_payload(directory, backend)
    if dry_run:
        print(f"pivm sync dry-run: {len(payload['files'])} files; "
              f"{len(payload['settings']['packages'])} packages; "
              "guest ~/.pi/agent; git global identity/signing preferences")
        for filename in sorted(payload["files"]):
            print(f"  file: {filename}")
        for entry in payload["settings"]["packages"]:
            print(f"  package: {entry['source'] if isinstance(entry, dict) else entry}")
        return payload
    script = inspect.getsource(guest_apply) + "\nimport json,sys\nguest_apply(json.load(sys.stdin))\n"
    subprocess.run([str(msb), "exec", str(name), "--", "python3", "-c", script],
                   input=json.dumps(payload), text=True, check=True)
    return payload
