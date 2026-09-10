#!/bin/bash
# Install as root: /usr/local/sbin/inventarios-docker-release (0755).
# Input: gzip-compressed docker save archive. Arguments: Git SHA, Docker image ID.
set -Eeuo pipefail
export PATH=/usr/local/bin:/usr/bin:/bin
umask 077
[[ $(id -u) == 0 ]] || { echo 'Requires root via the restricted sudo wrapper' >&2; exit 1; }
[[ $# == 2 && $1 =~ ^[0-9a-f]{40}$ && $2 =~ ^sha256:[0-9a-f]{64}$ ]] || exit 2
sha=$1
image_id=$2
compose_file=/opt/apps/inventarios-uno-a-uno/compose.yaml
config_dir=/etc/inventarios-uno-a-uno
state_dir=/var/lib/inventarios-uno-a-uno-deployment
docker=/usr/bin/docker

trusted() {
  [[ ! -L $1 && -e $1 && $(stat -c %u "$1") == 0 ]] || return 1
  local mode
  mode=$(stat -c %a "$1")
  (( (8#$mode & 0022) == 0 ))
}
for path in /opt /opt/apps /opt/apps/inventarios-uno-a-uno "$compose_file" "$config_dir" "$config_dir/inventarios.env" "$state_dir"; do
  trusted "$path" || { echo "Root-owned, non-writable control path required: $path" >&2; exit 1; }
done
exec 9>"$state_dir/deployment.lock"
flock -n 9 || { echo 'Another deployment is running' >&2; exit 1; }
previous=''
if [[ -e $config_dir/image.env ]]; then
  trusted "$config_dir/image.env" || exit 1
  marker=$(cat "$config_dir/image.env")
  [[ $marker =~ ^INVENTARIOS_IMAGE=inventarios-uno-a-uno:sha256-[0-9a-f]{64}$ ]] || exit 1
  previous=${marker#INVENTARIOS_IMAGE=}
elif [[ -n $("$docker" ps -aq --filter label=com.docker.compose.project=inventarios-uno-a-uno) ]]; then
  echo 'Existing containers without image.env: reconcile the installation first' >&2
  exit 1
fi
compose() {
  local ref=$1
  shift
  INVENTARIOS_IMAGE="$ref" "$docker" compose --project-name inventarios-uno-a-uno \
    --env-file /dev/null -f "$compose_file" "$@"
}
work=$(mktemp -d "$state_dir/release.XXXXXX")
new_ref="inventarios-uno-a-uno:sha256-${image_id#sha256:}"
switched=false
cleanup() {
  local result=$?
  trap - EXIT
  if (( result != 0 )) && [[ $switched == true ]]; then
    echo 'Deployment failed; stopping the candidate and recovering the previous image' >&2
    if compose "$new_ref" stop app; then
      # Replay cache is in memory: cover the maximum permitted SSO TTL + skew.
      sleep 320
      if [[ -n $previous ]]; then
        if ! compose "$previous" up -d --no-build --wait --wait-timeout 120 app; then
          echo 'Recovery failed; operator intervention required' >&2
          compose "$previous" stop app || true
        fi
      fi
    else
      echo 'Could not stop candidate; recovery requires operator intervention' >&2
    fi
  fi
  rm -f -- "$work/image.tar"
  rmdir -- "$work"
  exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT TERM
gzip -dc > "$work/image.tar"
# Prevent a supplied archive from replacing tags belonging to another application.
python3 - "$work/image.tar" "inventarios-uno-a-uno:ci-$sha" <<'PY'
import json, sys, tarfile
with tarfile.open(sys.argv[1], 'r:') as archive:
    member = archive.getmember('manifest.json')
    if member.size > 1024 * 1024:
        raise SystemExit('Unexpected archive manifest size')
    manifest = json.load(archive.extractfile(member))
    if len(manifest) != 1 or manifest[0].get('RepoTags') != [sys.argv[2]]:
        raise SystemExit('Archive must contain only the expected application tag')
PY
"$docker" image load --input "$work/image.tar" >/dev/null
loaded_ref="inventarios-uno-a-uno:ci-$sha"
[[ $("$docker" image inspect --format '{{.Id}}' "$loaded_ref") == "$image_id" ]] || exit 1
[[ $("$docker" image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$loaded_ref") == "$sha" ]] || exit 1
"$docker" image tag "$image_id" "$new_ref"
compose "$new_ref" config --quiet
# Load production configuration without starting a server or contacting Google.
compose "$new_ref" run --rm --no-deps --entrypoint python app -B -c \
  'from app import create_app; app=create_app(); assert app.config["APP_ENV"] == "production"; assert app.test_client().get("/healthz").json == {"status":"ok"}'
if [[ -n $previous ]]; then
  compose "$previous" stop app
  switched=true
  sleep 320
else
  switched=true
fi
compose "$new_ref" up -d --no-build --wait --wait-timeout 120 app
if [[ -n $previous ]]; then
  printf 'INVENTARIOS_IMAGE=%s\n' "$previous" > "$config_dir/previous-image.env"
fi
printf 'INVENTARIOS_IMAGE=%s\n' "$new_ref" > "$config_dir/image.env.new"
mv -f -- "$config_dir/image.env.new" "$config_dir/image.env"
switched=false
echo "Healthy deployment: $sha ($image_id)"
