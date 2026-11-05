#!/usr/bin/env python3
"""Deploy MRICS Plane branch images through Coolify.

Modes:
- staging: patch staging service images, refresh staging from production DB/MinIO, run migrator once, verify.
- production: take fresh production backup, patch production service images, run migrator once, verify.

Coolify 4.5 (CoolifyVBSManagement Hub) model this script relies on:
- ``docker_compose_raw`` stored in Coolify is the *authored* compose. Coolify renders it into
  ``/data/coolify/services/<uuid>/docker-compose.yml`` on the server, adding container names
  (``<service>-<uuid>``), Coolify labels, env_file and the per-service network.
- We therefore PATCH the image refs in ``docker_compose_raw`` (source of truth for future Coolify
  deploys) AND patch the same refs in the rendered on-host file. We never write the authored compose
  over the rendered file: that would strip Coolify's container names, labels and networks.
- All container access goes through ``docker compose -p <uuid> <compose-service>`` so the script does
  not depend on container naming. Data volumes are resolved from the running containers' mounts.

Required env:
  COOLIFY_BASE_URL, COOLIFY_ACCESS_TOKEN
  PLANE_TARGET_ENV=staging|production
  PLANE_SERVICE_UUID, PLANE_SERVER_UUID, PLANE_PRODUCTION_SERVICE_UUID
  PLANE_SERVER_IP, PLANE_PUBLIC_HOST
  PLANE_BACKEND_IMAGE, PLANE_FRONTEND_IMAGE, PLANE_ADMIN_IMAGE
"""
from __future__ import annotations

import base64
import datetime as dt
import functools
import json
import os
import re
import subprocess
import tempfile
import urllib.error
import urllib.request

IMAGE_PREFIX = "ghcr.io/mrics-technologies/mrics-plane-"


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None or value == "":
        raise SystemExit(f"missing required env: {name}")
    return value


BASE = env("COOLIFY_BASE_URL").rstrip("/")
TOKEN = env("COOLIFY_ACCESS_TOKEN")
TARGET = env("PLANE_TARGET_ENV")
SERVICE = env("PLANE_SERVICE_UUID")
SERVER = env("PLANE_SERVER_UUID")
PROD_SERVICE = env("PLANE_PRODUCTION_SERVICE_UUID")
SERVER_IP = env("PLANE_SERVER_IP")
PUBLIC_HOST = env("PLANE_PUBLIC_HOST")
BACKEND_IMAGE = env("PLANE_BACKEND_IMAGE")
FRONTEND_IMAGE = env("PLANE_FRONTEND_IMAGE")
ADMIN_IMAGE = env("PLANE_ADMIN_IMAGE")
SHA = os.environ.get("GITHUB_SHA", "manual")[:12]

UUID_RE = re.compile(r"^[a-z0-9]{20,32}$")


def redact(text: str) -> str:
    return re.sub(
        r"(?i)(password|token|secret|key|database_url|redis_url|amqp_url|email_host_password)([=:\s]+)([^\s,'\"]+)",
        r"\1\2[REDACTED]",
        text,
    )


def api(path: str, method: str = "GET", body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": "Bearer " + TOKEN, "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + "/api/v1" + path, data=data, method=method, headers=headers)
    try:
        raw = urllib.request.urlopen(req, timeout=60).read().decode(errors="replace")
        return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        msg = exc.read().decode(errors="replace")
        raise SystemExit(f"Coolify API {method} {path} failed {exc.code}: {redact(msg)[:2000]}")


def decode_compose(raw: str) -> str:
    if raw and "services:" not in raw[:200]:
        try:
            return base64.b64decode(raw).decode(errors="replace")
        except Exception:
            pass
    return raw


def patch_images(compose: str) -> str:
    refs = {
        "backend": BACKEND_IMAGE,
        "frontend": FRONTEND_IMAGE,
        "admin": ADMIN_IMAGE,
    }

    def repl(match: re.Match[str]) -> str:
        indent, component = match.group(1), match.group(2)
        return f"{indent}{refs[component]}"

    pattern = re.compile(
        rf"(?m)^(\s*image:\s*)['\"]?{re.escape(IMAGE_PREFIX)}(backend|frontend|admin)(?::[^\s'\"]+|@sha256:[a-f0-9]+)?['\"]?"
    )
    patched, count = pattern.subn(repl, compose)
    if count < 3:
        raise SystemExit(f"expected to patch at least 3 image refs, patched {count}")
    for ref in refs.values():
        if "@sha256:" not in ref:
            raise SystemExit(f"image ref must be digest-pinned: {ref}")
        if ref not in patched:
            raise SystemExit(f"patched compose missing image ref: {ref}")
    return patched


def update_coolify_compose() -> None:
    """Persist the new image refs in Coolify's authored compose (used by future Coolify deploys)."""
    service = api("/services/" + SERVICE)
    compose = decode_compose(service.get("docker_compose_raw") or "")
    if not compose.strip() or compose.strip() == "***":
        raise SystemExit("Coolify service docker_compose_raw is empty or redacted (token needs read:sensitive)")
    patched = patch_images(compose)
    encoded = base64.b64encode(patched.encode()).decode()
    api("/services/" + SERVICE, method="PATCH", body={"docker_compose_raw": encoded})
    readback = decode_compose(api("/services/" + SERVICE).get("docker_compose_raw") or "")
    for ref in [BACKEND_IMAGE, FRONTEND_IMAGE, ADMIN_IMAGE]:
        if ref not in readback:
            raise SystemExit(f"Coolify readback missing {ref}")
    print(f"coolify_compose_patched target={TARGET} service={SERVICE}")


@functools.cache
def ssh_target() -> tuple[str, int, str]:
    server = api("/servers/" + SERVER)
    if server.get("ip") != SERVER_IP:
        raise SystemExit(f"Coolify server {SERVER} ip {server.get('ip')} != expected {SERVER_IP}")
    keys = api("/security/keys")
    key_obj = next((k for k in keys if k.get("id") == server.get("private_key_id")), None)
    if not key_obj or not str(key_obj.get("private_key", "")).startswith("-----BEGIN"):
        raise SystemExit("server private key not readable through Coolify API (token needs read:sensitive)")
    key = key_obj["private_key"].replace("\\r\\n", "\n")
    return f"{server.get('user') or 'root'}@{server['ip']}", int(server.get("port") or 22), key


def ssh_raw(script: str, timeout: int = 1200) -> tuple[int, str, str]:
    dest, port, key = ssh_target()
    with tempfile.NamedTemporaryFile("w", delete=False) as fh:
        fh.write(key)
        keyfile = fh.name
    os.chmod(keyfile, 0o600)
    try:
        proc = subprocess.run(
            [
                "ssh",
                "-i",
                keyfile,
                "-p",
                str(port),
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=20",
                "-o",
                "StrictHostKeyChecking=accept-new",
                "-o",
                "LogLevel=ERROR",
                dest,
                # Stage the script in a private temp file and run it with stdin=/dev/null so that
                # `docker compose exec -T` (which reads stdin) cannot swallow the rest of the script.
                "umask 077; f=$(mktemp); trap 'rm -f \"$f\"' EXIT; cat > \"$f\"; bash \"$f\" </dev/null",
            ],
            input=script,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    finally:
        try:
            os.unlink(keyfile)
        except FileNotFoundError:
            pass
    return proc.returncode, proc.stdout, proc.stderr


def ssh(script: str, timeout: int = 1200) -> str:
    code, stdout, stderr = ssh_raw(script, timeout)
    output = stdout
    if stderr.strip():
        output += "\n--- stderr tail ---\n" + stderr[-4000:]
    output = redact(output)
    if code != 0:
        raise SystemExit(output + f"\nremote_exit={code}")
    return output


def preflight() -> None:
    print(ssh("set -euo pipefail\necho ssh_ok\nsudo docker compose version --short\n", timeout=120).strip())


def service_dir(uuid: str) -> str:
    if not UUID_RE.match(uuid):
        raise SystemExit(f"invalid Coolify uuid: {uuid}")
    return f"/data/coolify/services/{uuid}"


def rendered_compose() -> str:
    """Read the Coolify-rendered compose on the host and patch only the image refs."""
    code, stdout, stderr = ssh_raw(f"sudo cat {service_dir(SERVICE)}/docker-compose.yml\n", timeout=120)
    if code != 0:
        raise SystemExit(f"cannot read rendered compose: {redact(stderr)[-2000:]}")
    if f"coolify.serviceUuid={SERVICE}" not in stdout:
        raise SystemExit("rendered compose is not Coolify-rendered for this service (missing coolify.serviceUuid label)")
    return base64.b64encode(patch_images(stdout).encode()).decode()


def remote_common(encoded_compose: str) -> str:
    return f"""
set +x
set -euo pipefail
cd {service_dir(SERVICE)}
sudo cp -p docker-compose.yml docker-compose.yml.pre-github-actions-{SHA}-$(date -u +%Y%m%dT%H%M%SZ)
echo {encoded_compose} | base64 -d | sudo tee docker-compose.yml.next >/dev/null
DC="sudo docker compose -f docker-compose.yml -p {SERVICE}"
sudo docker compose -f docker-compose.yml.next -p {SERVICE} config -q
sudo cp docker-compose.yml.next docker-compose.yml
sudo rm -f docker-compose.yml.next
echo compose_config=ok
ctr() {{ $DC ps --all -q "$1" | head -n1; }}
wait_migrator() {{
  for i in $(seq 1 120); do
    mid=$(ctr plane-migrator)
    st=$(sudo docker inspect "$mid" --format '{{{{.State.Status}}}}:{{{{.State.ExitCode}}}}:{{{{.RestartCount}}}}' 2>/dev/null || true)
    echo "migrator=$st"
    case "$st" in
      exited:0:*) return 0 ;;
      exited:*|*:*:[3-9]*) sudo docker logs --tail=120 "$mid" || true; return 2 ;;
    esac
    sleep 5
  done
  echo "migrator did not finish"; return 2
}}
show_images() {{
  for s in plane-api plane-worker plane-beat-worker plane-migrator plane-web plane-admin; do
    c=$(ctr "$s"); [ -n "$c" ] || {{ echo "$s=missing"; continue; }}
    echo "$s image=$(sudo docker inspect "$c" --format '{{{{.Config.Image}}}}') id=$(sudo docker inspect "$c" --format '{{{{.Image}}}}') state=$(sudo docker inspect "$c" --format '{{{{.State.Status}}}}:{{{{.State.ExitCode}}}}')"
  done
}}
wait_api() {{
  # plane-api runs migrations/collectstatic before gunicorn binds :8000; first boot after a
  # refresh took ~80s on 2026-10-27, so a fixed sleep is not enough. Wait up to 5 minutes.
  for i in $(seq 1 60); do
    if $DC exec -T plane-api python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/api/instances/', timeout=5)" >/dev/null 2>&1; then
      echo "api_ready after ~$((i * 5))s"; sleep 5; return 0
    fi
    sleep 5
  done
  echo "api not ready after 300s"; $DC logs --tail=80 plane-api || true; return 3
}}
probe_routes() {{
  for attempt in 1 2 3 4 5 6; do
    if probe_routes_once "$1"; then return 0; fi
    echo "route probe attempt $attempt failed; retrying in 10s"; sleep 10
  done
  echo route_probe_failed; return 3
}}
probe_routes_once() {{
  bad=0
  for p in / /god-mode /god-mode/ /api/instances/ /api/v1/users/me/ /auth/get-csrf-token/; do
    printf '%-24s ' "$p"
    line=$(curl $1 -sS -o /tmp/plane-probe -w 'http=%{{http_code}} size=%{{size_download}} final=%{{url_effective}} redirect=%{{redirect_url}}' -L --max-time 30 "https://{PUBLIC_HOST}$p" || echo 'http=000')
    echo "$line"
    case "$line" in http=5*|http=000*) bad=1 ;; esac
  done
  [ "$bad" = 0 ]
}}
"""


def staging_script(encoded_compose: str) -> str:
    ts = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    prod_dir = service_dir(PROD_SERVICE)
    return remote_common(encoded_compose) + f"""
PROD_DC="sudo docker compose -f {prod_dir}/docker-compose.yml -p {PROD_SERVICE}"
data_volume() {{ sudo docker inspect "$1" --format '{{{{range .Mounts}}}}{{{{if eq .Destination "/data"}}}}{{{{.Name}}}}{{{{end}}}}{{{{end}}}}'; }}

echo resolve_minio_volumes
PROD_MINIO=$($PROD_DC ps -q plane-minio | head -n1)
STAGE_MINIO=$(ctr plane-minio)
[ -n "$PROD_MINIO" ] && [ -n "$STAGE_MINIO" ] || {{ echo "minio containers not found prod=$PROD_MINIO stage=$STAGE_MINIO"; exit 4; }}
SRC_VOL=$(data_volume "$PROD_MINIO")
DST_VOL=$(data_volume "$STAGE_MINIO")
echo "minio_src=$SRC_VOL minio_dst=$DST_VOL"
[ -n "$SRC_VOL" ] && [ -n "$DST_VOL" ] && [ "$SRC_VOL" != "$DST_VOL" ] || {{ echo "unsafe minio volume mapping"; exit 4; }}
sudo docker volume inspect "$SRC_VOL" >/dev/null
sudo docker volume inspect "$DST_VOL" >/dev/null
for c in $($PROD_DC ps --all -q); do
  if sudo docker inspect "$c" --format '{{{{range .Mounts}}}}{{{{.Name}}}} {{{{end}}}}' | tr ' ' '\\n' | grep -qx "$DST_VOL"; then
    echo "refusing: staging minio volume $DST_VOL is mounted by a production container"; exit 4
  fi
done

echo pull_images
$DC pull plane-api plane-worker plane-beat-worker plane-migrator plane-web plane-admin

echo stop_staging_apps
$DC stop plane-api plane-worker plane-beat-worker plane-web plane-admin plane-space plane-live plane-migrator || true
$DC up -d --no-deps plane-db plane-redis plane-mq plane-minio
sleep 10

echo reset_staging_schema
$DC exec -T plane-db sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"' >/dev/null

echo restore_prod_db_into_staging
mkdir -p /home/ubuntu/plane-backups
$PROD_DC exec -T plane-db sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump --clean --if-exists -U "$POSTGRES_USER" -d "$POSTGRES_DB"' | tee >(gzip -c > /home/ubuntu/plane-backups/plane-prod-to-staging-{ts}-{SHA}.sql.gz) | $DC exec -T plane-db sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' >/tmp/staging-restore.log 2>&1 || {{ tail -80 /tmp/staging-restore.log; exit 1; }}
chmod 600 /home/ubuntu/plane-backups/plane-prod-to-staging-{ts}-{SHA}.sql.gz
ls -l /home/ubuntu/plane-backups/plane-prod-to-staging-{ts}-{SHA}.sql.gz | awk '{{print "prod_snapshot_size="$5}}'

echo mirror_minio_prod_to_staging
$DC stop plane-minio
sudo docker run --rm -v "$SRC_VOL":/src:ro -v "$DST_VOL":/dst alpine:3.20 sh -lc 'rm -rf /dst/* /dst/..?* /dst/.[!.]* 2>/dev/null || true; cd /src && tar cf - . | tar xf - -C /dst'
$DC up -d --no-deps plane-minio
sleep 10
$DC up -d --no-deps plane-minio-setup || true

echo run_staging_migrator
$DC up -d --no-deps --force-recreate plane-migrator
wait_migrator

echo start_staging_apps
$DC up -d --no-deps --force-recreate plane-api plane-worker plane-beat-worker plane-web plane-admin plane-space plane-live
wait_api

echo migration_gate
$DC exec -T plane-api sh -lc 'cd /code && python manage.py migrate --check && python manage.py makemigrations --check --dry-run'

echo neutralize_staging_side_effects
$DC exec -T plane-api sh -lc 'cd /code && python manage.py shell' <<'PY'
from django.apps import apps
for M in apps.get_models():
    fields={{f.name for f in M._meta.fields}}
    if not ({{'key','value'}} <= fields or {{'name','value'}} <= fields):
        continue
    key_field='key' if 'key' in fields else 'name'
    disable=['ENABLE_SMTP','IS_GITHUB_ENABLED','ENABLE_GITHUB_SYNC','IS_GOOGLE_ENABLED','ENABLE_GOOGLE_SYNC','IS_GITLAB_ENABLED','ENABLE_GITLAB_SYNC','IS_GITEA_ENABLED','ENABLE_GITEA_SYNC']
    try:
        for obj in M.objects.filter(**{{f'{{key_field}}__in': disable}}):
            setattr(obj,'value','0')
            obj.save(update_fields=['value'])
    except Exception:
        pass
PY
$DC exec -T plane-redis sh -lc 'redis-cli FLUSHALL' >/dev/null || echo "warn: staging redis flush failed"

echo counts
$DC exec -T plane-db sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT concat('"'"'users='"'"', (SELECT count(*) FROM users), '"'"' workspaces='"'"', (SELECT count(*) FROM workspaces), '"'"' projects='"'"', (SELECT count(*) FROM projects), '"'"' issues='"'"', (SELECT count(*) FROM issues));"'

echo images
show_images

echo route_probes
probe_routes "-k --resolve {PUBLIC_HOST}:443:{SERVER_IP}"
"""


def production_script(encoded_compose: str) -> str:
    ts = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    return remote_common(encoded_compose) + f"""
echo backup_production_db
mkdir -p /home/ubuntu/plane-backups
$DC exec -T plane-db sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump --clean --if-exists -U "$POSTGRES_USER" -d "$POSTGRES_DB"' | gzip > /home/ubuntu/plane-backups/plane-prod-pre-deploy-{ts}-{SHA}.sql.gz
chmod 600 /home/ubuntu/plane-backups/plane-prod-pre-deploy-{ts}-{SHA}.sql.gz
ls -l /home/ubuntu/plane-backups/plane-prod-pre-deploy-{ts}-{SHA}.sql.gz | awk '{{print "backup_size="$5}}'

echo deploy_production_images
$DC pull plane-api plane-worker plane-beat-worker plane-migrator plane-web plane-admin
$DC up -d --no-deps --force-recreate plane-migrator
wait_migrator

$DC up -d --no-deps --force-recreate plane-api plane-worker plane-beat-worker plane-web plane-admin plane-space plane-live
wait_api

echo migration_gate
$DC exec -T plane-api sh -lc 'cd /code && python manage.py migrate --check && python manage.py makemigrations --check --dry-run'

echo images
show_images

echo route_probes
probe_routes ""
"""


def main() -> None:
    if TARGET not in {"staging", "production"}:
        raise SystemExit("PLANE_TARGET_ENV must be staging or production")
    if TARGET == "staging" and SERVICE == PROD_SERVICE:
        raise SystemExit("refusing: staging target resolves to the production service uuid")
    if TARGET == "production" and SERVICE != PROD_SERVICE:
        raise SystemExit("refusing: production target does not match PLANE_PRODUCTION_SERVICE_UUID")
    preflight()
    encoded = rendered_compose()
    update_coolify_compose()
    script = staging_script(encoded) if TARGET == "staging" else production_script(encoded)
    print(ssh(script, timeout=1800))
    print(f"deploy_complete target={TARGET} service={SERVICE} sha={SHA}")


if __name__ == "__main__":
    main()
