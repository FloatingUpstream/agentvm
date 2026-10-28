#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
IMAGE="$ROOT/images/pi-vm"
grep -Fq 'directory = "/home/dev/worktrees"' "$IMAGE/herdr.toml"
for file in "$ROOT/bin/build-pi-vm" "$IMAGE"/{bash_profile,bashrc,git-credential-github-env,test.sh}; do
  bash -n "$file"
done

node - "$IMAGE" <<'JS'
const fs = require("node:fs");
const assert = require("node:assert/strict");
const root = process.argv[2];
const pkg = JSON.parse(fs.readFileSync(`${root}/package.json`));
const lock = JSON.parse(fs.readFileSync(`${root}/package-lock.json`));
const settings = JSON.parse(fs.readFileSync(`${root}/settings.json`));
assert.equal(pkg.dependencies["@earendil-works/pi-coding-agent"], "1.4.0");
assert.equal(Object.keys(pkg.dependencies).length, 10);
assert.deepEqual(lock.packages[""].dependencies, pkg.dependencies);
for (const [name, version] of Object.entries(pkg.dependencies)) {
  assert.match(version, /^\d+\.\d+\.\d+$/);
  assert.equal(lock.packages[`node_modules/${name}`].version, version);
}
assert.equal(settings.packages.length, 9);
for (const path of settings.packages) {
  assert.ok(path.startsWith("./npm/node_modules/"));
  assert.ok(pkg.dependencies[path.slice("./npm/node_modules/".length)]);
}
for (const entry of Object.values(lock.packages)) {
  if (entry.resolved) {
    assert.ok(entry.resolved.startsWith("https://registry.npmjs.org/"));
    assert.ok(entry.integrity);
  }
}
assert.equal(settings.defaultProjectTrust, "ask");
assert.equal(settings.enableInstallTelemetry, false);
JS

helper="$IMAGE/git-credential-github-env"
actual="$(printf 'protocol=https\nhost=github.com\n\n' | GH_TOKEN=dummy-only "$helper" get)"
[[ $actual == $'username=x-access-token\npassword=dummy-only' ]]
for request in \
  $'protocol=https\nhost=evil.example\n\n' \
  $'protocol=https\nhost=github.com.evil.example\n\n' \
  $'protocol=http\nhost=github.com\n\n' \
  $'protocol=https\nhost=github.com:443\n\n'; do
  [[ -z $(printf '%s' "$request" | GH_TOKEN=dummy-only "$helper" get) ]]
done
[[ -z $(printf 'protocol=https\nhost=github.com\n\n' | GH_TOKEN= "$helper" get) ]]
for action in store erase; do
  [[ -z $(printf 'protocol=https\nhost=github.com\n\n' | GH_TOKEN=dummy-only "$helper" "$action") ]]
done
if printf 'protocol=https\nhost=github.com\n\n' | GH_TOKEN=$'bad\ninjection' "$helper" get; then
  echo "error: helper accepted newline injection" >&2
  exit 1
fi

# Exercise the wrapper without running a build or connecting to msb.
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir "$tmp/bin"
printf '#!/bin/bash\nprintf "docker" >> "$TEST_LOG"\nprintf " <%%s>" "$@" >> "$TEST_LOG"\nprintf "\\n" >> "$TEST_LOG"\n' > "$tmp/bin/docker"
printf '#!/bin/bash\nprintf "msb" >> "$TEST_LOG"\nprintf " <%%s>" "$@" >> "$TEST_LOG"\nprintf "\\n" >> "$TEST_LOG"\n' > "$tmp/bin/msb"
chmod +x "$tmp/bin/"*
TEST_LOG="$tmp/log" PATH="$tmp/bin:$PATH" \
  IMAGE_NAME=test-pi:only ARCHIVE="$tmp/test.tar" BASE_IMAGE=archlinux:test-pin \
  GH_TOKEN=dummy-never-pass GITHUB_TOKEN=dummy-never-pass \
  "$ROOT/bin/build-pi-vm" --pull --no-cache >/dev/null
grep -Fq 'docker <build> <--platform> <linux/amd64> <--build-arg> <BASE_IMAGE=archlinux:test-pin>' "$tmp/log"
grep -Fq "<$ROOT/images/pi-vm>" "$tmp/log"
grep -Fq '<--pull> <--no-cache>' "$tmp/log"
grep -Fq "docker <save> <test-pi:only> <-o> <$tmp/test.tar>" "$tmp/log"
! grep -Fq 'msb <image> <remove>' "$tmp/log"
grep -Fq "msb <image> <load> <--input> <$tmp/test.tar> <--tag> <test-pi:only>" "$tmp/log"
! grep -q 'dummy-never-pass' "$tmp/log"

# Login setup must work without relying on inherited Docker ENV PATH, and must
# keep agentd's CA setting and the pane's chosen working directory unchanged.
mkdir "$tmp/home"
cp "$IMAGE/bashrc" "$tmp/home/.bashrc"
HOME="$tmp/home" NODE_EXTRA_CA_CERTS=/.msb/tls/ca.pem \
  /bin/bash --noprofile --norc -c '
    cd /tmp
    . "$1"
    [[ $PATH == "$HOME/.local/bin:$HOME/.pi/agent/npm/node_modules/.bin:"* ]]
    [[ $NODE_EXTRA_CA_CERTS == /.msb/tls/ca.pem ]]
    [[ $PWD == /tmp ]]
  ' bash "$IMAGE/bash_profile"
echo "pi-vm static and mocked-wrapper tests passed (no image built)"
