"""Exercise release failure/recovery using command doubles; no Docker daemon or VM."""
import gzip
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

import pytest

SHA = "2" * 40
IMAGE_ID = "sha256:" + "b" * 64
PREVIOUS = "inventarios-uno-a-uno:sha256-" + "a" * 64
TARGET = "inventarios-uno-a-uno:sha256-" + "b" * 64


def bash_path(path):
    value = path.resolve().as_posix()
    return "/" + value[0].lower() + value[2:] if os.name == "nt" else value


@pytest.fixture
def simulated_vm(tmp_path):
    bash = shutil.which("bash")
    if not bash and os.name == "nt":
        candidate = Path("C:/Program Files/Git/bin/bash.exe")
        bash = str(candidate) if candidate.exists() else None
    if not bash:
        pytest.skip("Bash required for release tests")
    app, config, state, commands = [tmp_path / name for name in ("app", "config", "state", "commands")]
    for path in (app, config, state, commands):
        path.mkdir()
    (app / "compose.yaml").touch()
    (config / "inventarios.env").write_text("APP_ENV=production\n")
    (config / "image.env").write_text("INVENTARIOS_IMAGE=" + PREVIOUS + "\n")
    (state / "active").write_text(PREVIOUS)

    def command(name, body):
        path = commands / name
        path.write_text("#!/bin/bash\nset -eu\n" + body, encoding="utf-8", newline="\n")
        path.chmod(0o755)

    command("id", "echo 0\n")
    command("stat", 'if [[ "$2" == %u ]]; then echo 0; else echo 755; fi\n')
    command("flock", "exit 0\n")
    command("sleep", 'echo "sleep $*" >> "$VM_STATE/events"\n')
    command("python3", 'exec "$TEST_PYTHON" "$@"\n')
    command("docker", r'''
printf 'docker %s [%s]\n' "$*" "${INVENTARIOS_IMAGE:-}" >> "$VM_STATE/events"
if [[ "$1" == ps ]]; then exit 0; fi
if [[ "$1" == image ]]; then
  case "$2" in
    load) [[ "$SCENARIO" != load_failure ]] ;;
    tag) exit 0 ;;
    inspect)
      if [[ "$4" == '{{.Id}}' ]]; then
        if [[ "$SCENARIO" == wrong_image ]]; then echo wrong; else echo "$TEST_IMAGE_ID"; fi
      else echo "$TEST_SHA"; fi ;;
    *) exit 99 ;;
  esac
  exit
fi
[[ "$1" == compose ]] || exit 99
shift 7
case "$1" in
  config) [[ "$SCENARIO" != config_failure ]] ;;
  run) [[ "$SCENARIO" != preflight_failure ]] ;;
  stop) rm -f "$VM_STATE/active" ;;
  up)
    if [[ "$SCENARIO" == rollback_failure ]]; then exit 1; fi
    if [[ "$SCENARIO" == health_failure && "$INVENTARIOS_IMAGE" != "$TEST_PREVIOUS" ]]; then exit 1; fi
    printf '%s' "$INVENTARIOS_IMAGE" > "$VM_STATE/active" ;;
  *) exit 99 ;;
esac
''')
    source = Path("scripts/docker_release.sh").read_text(encoding="utf-8")
    for original, replacement in [
        ("/opt/apps/inventarios-uno-a-uno", bash_path(app)),
        ("/etc/inventarios-uno-a-uno", bash_path(config)),
        ("/var/lib/inventarios-uno-a-uno-deployment", bash_path(state)),
        ("/usr/bin/docker", bash_path(commands / "docker")),
        ("for path in /opt /opt/apps ", "for path in "),
        ("export PATH=/usr/local/bin:/usr/bin:/bin", 'export PATH="' + bash_path(commands) + ':/usr/bin:/bin"'),
    ]:
        source = source.replace(original, replacement)
    script = tmp_path / "release-test.sh"
    script.write_text(source, encoding="utf-8", newline="\n")

    def run(scenario="success", initial=False, tag=None, sha=SHA):
        if initial:
            (config / "image.env").unlink()
            (state / "active").unlink()
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode="w") as tar:
            manifest = json.dumps([{"RepoTags": [tag or "inventarios-uno-a-uno:ci-" + SHA]}]).encode()
            item = tarfile.TarInfo("manifest.json")
            item.size = len(manifest)
            tar.addfile(item, io.BytesIO(manifest))
        result = subprocess.run([bash, "--noprofile", "--norc", bash_path(script), sha, IMAGE_ID],
            input=gzip.compress(archive.getvalue()), capture_output=True, timeout=25,
            env={**os.environ, "VM_STATE": bash_path(state), "SCENARIO": scenario,
                 "TEST_PYTHON": bash_path(Path(sys.executable)), "TEST_IMAGE_ID": IMAGE_ID,
                 "TEST_SHA": SHA, "TEST_PREVIOUS": PREVIOUS})
        events = state / "events"
        return result, events.read_text() if events.exists() else "", config, state
    return run


def test_release_success_preserves_previous_and_orders_restart(simulated_vm):
    result, events, config, state = simulated_vm()
    assert result.returncode == 0, result.stderr.decode()
    assert (config / "image.env").read_text().strip() == "INVENTARIOS_IMAGE=" + TARGET
    assert (config / "previous-image.env").read_text().strip() == "INVENTARIOS_IMAGE=" + PREVIOUS
    assert (state / "active").read_text() == TARGET
    assert events.index("run --rm") < events.index("stop app") < events.index("sleep 320") < events.index("up -d")
    assert "apache" not in events and "deliveryTraceability" not in events
    assert not list(state.glob("release.*"))


def test_initial_release_has_no_previous_service_to_stop(simulated_vm):
    result, events, config, state = simulated_vm(initial=True)
    assert result.returncode == 0, result.stderr.decode()
    assert "stop app" not in events and "sleep" not in events
    assert (state / "active").read_text() == TARGET


@pytest.mark.parametrize("scenario", ["load_failure", "wrong_image", "config_failure", "preflight_failure"])
def test_preflight_failure_keeps_previous_running(simulated_vm, scenario):
    result, events, config, state = simulated_vm(scenario)
    assert result.returncode != 0
    assert "stop app" not in events
    assert (state / "active").read_text() == PREVIOUS
    assert (config / "image.env").read_text().strip() == "INVENTARIOS_IMAGE=" + PREVIOUS
    assert not list(state.glob("release.*"))


def test_archive_cannot_replace_other_application_tag(simulated_vm):
    result, events, config, state = simulated_vm(tag="another-app:latest")
    assert result.returncode != 0
    assert "image load" not in events and "stop app" not in events
    assert (state / "active").read_text() == PREVIOUS


def test_unhealthy_candidate_rolls_back(simulated_vm):
    result, events, config, state = simulated_vm("health_failure")
    assert result.returncode != 0
    assert (state / "active").read_text() == PREVIOUS
    assert (config / "image.env").read_text().strip() == "INVENTARIOS_IMAGE=" + PREVIOUS
    assert events.count("sleep 320") == 2


def test_failed_rollback_leaves_app_stopped(simulated_vm):
    result, events, config, state = simulated_vm("rollback_failure")
    assert result.returncode != 0
    assert not (state / "active").exists()
    assert "Recovery failed" in result.stderr.decode()


def test_invalid_argument_never_reaches_docker(simulated_vm):
    result, events, config, state = simulated_vm(sha="main; unexpected-command")
    assert result.returncode == 2
    assert not events
