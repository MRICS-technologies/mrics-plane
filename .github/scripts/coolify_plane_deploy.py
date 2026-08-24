#!/usr/bin/env python3
"""Deploy MRICS Plane branch images through Coolify.

Modes:
- staging: patch staging service images, refresh staging from production DB/MinIO, run migrator once, verify.
- production: take fresh production backup, patch production service images, run migrator once, verify.

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
import json
import os
import re
import subprocess
import sys
import tempfile
import time
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

    pattern = re.compile(rf"(?m)^(\s*image:\s*)['\"]?{re.escape(IMAGE_PREFIX)}(backend|frontend|admin)(?::[^\s'\"]+|@sha256:[a-f0-9]+)?['\"]?")
    patched, count = pattern.subn(repl, compose)
    if count < 3:
        raise SystemExit(f"expected to patch at least 3 image refs, patched {count}")
    for ref in refs.values():
        if "@sha256:" not in ref:
            raise SystemExit(f"image ref must be digest-pinned: {ref}")
        if ref not in patched:
            raise SystemExit(f"patched compose missing image ref: {ref}")
    return patched


def update_coolify_compose() -> str:
    service = api("/services/" + SERVICE)
    compose = decode_compose(service.get("docker_compose_raw") or "")
    if not compose.strip():
        raise SystemExit("Coolify service has empty docker_compose_raw")
    patched = patch_images(compose)
    encoded = base64.b64encode(patched.encode()).decode()
    api("/services/" + SERVICE, method="PATCH", body={"docker_compose_raw": encoded})
    readback = decode_compose(api("/services/" + SERVICE).get("docker_compose_raw") or "")
    for ref in [BACKEND_IMAGE, FRONTEND_IMAGE, ADMIN_IMAGE]:
        if ref not in readback:
            raise SystemExit(f"Coolify readback missing {ref}")
    print(f"coolify_compose_patched target={TARGET} service={SERVICE}")
    return encoded


def ssh(script: str, timeout: int = 1200) -> str:
    server = api("/servers/" + SERVER)
    keys = api("/security/keys")
    key_obj = next((k for k in keys if k.get("id") == server.get("private_key_id")), None)
    if not key_obj:
        raise SystemExit("server private key not found through Coolify API")
    key = key_obj["private_key"].replace("\\r\\n", "\n")
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
                str(server.get("port") or 22),
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=20",
                "-o",
                "StrictHostKeyChecking=accept-new",
                f"{server.get('user') or 'root'}@{server['ip']}",
                "bash -s",
            ],
            input=script,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    finally:
        try:
            os.unlink(keyfile)
        except FileNotFoundError:
            pass
    output = proc.stdout
    if proc.stderr.strip():
        output += "\n--- stderr tail ---\n" + proc.stderr[-4000:]
    output = redact(output)
    if proc.returncode != 0:
        raise SystemExit(output + f"\nremote_exit={proc.returncode}")
    return output


def remote_common(encoded_compose: str) -> str:
    return f"""
set +x
set -euo pipefail
cd /data/coolify/services/{SERVICE}
cp docker-compose.yml docker-compose.yml.pre-github-actions-{SHA}-$(date -u +%Y%m%dT%H%M%SZ) || true
echo {encoded_compose} | base64 -d > docker-compose.yml
sudo docker compose -f docker-compose.yml -p {SERVICE} config -q
echo compose_config=ok
"""


def staging_script(encoded_compose: str) -> str:
    ts = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    return remote_common(encoded_compose) + f"""
echo stop_staging_apps
sudo docker compose -f docker-compose.yml -p {SERVICE} stop plane-api plane-worker plane-beat-worker plane-web plane-admin plane-space plane-live plane-migrator || true
sudo docker compose -f docker-compose.yml -p {SERVICE} up -d plane-db plane-redis plane-mq plane-minio

echo reset_staging_schema
sudo docker exec plane-db sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"' >/dev/null

echo restore_prod_db_into_staging
mkdir -p /home/ubuntu/plane-backups
sudo docker exec plane-db-{PROD_SERVICE} sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump --clean --if-exists -U "$POSTGRES_USER" -d "$POSTGRES_DB"' | tee >(gzip -c > /home/ubuntu/plane-backups/plane-prod-to-staging-{ts}-{SHA}.sql.gz) | sudo docker exec -i plane-db sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' >/tmp/staging-restore.log 2>&1 || {{ tail -80 /tmp/staging-restore.log; exit 1; }}
chmod 600 /home/ubuntu/plane-backups/plane-prod-to-staging-{ts}-{SHA}.sql.gz

echo mirror_minio_prod_to_staging
sudo docker stop plane-minio >/dev/null 2>&1 || true
sudo docker run --rm -v {PROD_SERVICE}_miniodata:/src:ro -v plane_staging_miniodata:/dst alpine:3.20 sh -lc 'rm -rf /dst/* /dst/..?* /dst/.[!.]* 2>/dev/null || true; cd /src && tar cf - . | tar xf - -C /dst'
sudo docker compose -f docker-compose.yml -p {SERVICE} up -d plane-minio plane-minio-setup

echo run_staging_migrator
sudo docker compose -f docker-compose.yml -p {SERVICE} pull plane-api plane-worker plane-beat-worker plane-web plane-admin || true
sudo docker compose -f docker-compose.yml -p {SERVICE} up -d --force-recreate plane-migrator
for i in $(seq 1 90); do
  st=$(sudo docker inspect plane-staging-migrator --format '{{{{.State.Status}}}}:{{{{.State.ExitCode}}}}' 2>/dev/null || true)
  echo "migrator=$st"
  [ "$st" = "exited:0" ] && break
  [ "$st" = "exited:1" ] && {{ sudo docker logs --tail=120 plane-staging-migrator; exit 2; }}
  sleep 5
done
[ "$(sudo docker inspect plane-staging-migrator --format '{{{{.State.Status}}}}:{{{{.State.ExitCode}}}}')" = "exited:0" ]

echo start_staging_apps
sudo docker compose -f docker-compose.yml -p {SERVICE} up -d --force-recreate plane-api plane-worker plane-beat-worker plane-web plane-admin plane-space plane-live
sleep 45

echo migration_gate
sudo docker exec plane-api sh -lc 'cd /code && python manage.py migrate --check && python manage.py makemigrations --check --dry-run'

echo neutralize_staging_side_effects
sudo docker exec -i plane-api sh -lc 'cd /code && python manage.py shell' <<'PY'
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
sudo docker exec plane-redis sh -lc 'redis-cli FLUSHALL' >/dev/null || true

echo counts
sudo docker exec plane-db sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT concat('"'"'users='"'"', (SELECT count(*) FROM users), '"'"' workspaces='"'"', (SELECT count(*) FROM workspaces), '"'"' projects='"'"', (SELECT count(*) FROM projects), '"'"' issues='"'"', (SELECT count(*) FROM issues));"'

echo route_probes
for p in / /god-mode /god-mode/ /api/instances/; do
  printf '%-18s ' "$p"
  curl -k --resolve {PUBLIC_HOST}:443:{SERVER_IP} -sS -o /tmp/plane-stage-probe -w 'http=%{{http_code}} size=%{{size_download}} final=%{{url_effective}} redirect=%{{redirect_url}}\n' -L --max-time 30 "https://{PUBLIC_HOST}$p"
done
"""


def production_script(encoded_compose: str) -> str:
    ts = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    return remote_common(encoded_compose) + f"""
echo backup_production_db
mkdir -p /home/ubuntu/plane-backups
sudo docker exec plane-db-{SERVICE} sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump --clean --if-exists -U "$POSTGRES_USER" -d "$POSTGRES_DB"' | gzip > /home/ubuntu/plane-backups/plane-prod-pre-deploy-{ts}-{SHA}.sql.gz
chmod 600 /home/ubuntu/plane-backups/plane-prod-pre-deploy-{ts}-{SHA}.sql.gz
ls -lh /home/ubuntu/plane-backups/plane-prod-pre-deploy-{ts}-{SHA}.sql.gz | awk '{{print "backup_size="$5}}'

echo deploy_production_images
sudo docker compose -f docker-compose.yml -p {SERVICE} pull plane-api plane-worker plane-beat-worker plane-web plane-admin || true
sudo docker compose -f docker-compose.yml -p {SERVICE} up -d --force-recreate plane-migrator
for i in $(seq 1 90); do
  st=$(sudo docker inspect plane-migrator-{SERVICE} --format '{{{{.State.Status}}}}:{{{{.State.ExitCode}}}}' 2>/dev/null || true)
  echo "migrator=$st"
  [ "$st" = "exited:0" ] && break
  [ "$st" = "exited:1" ] && {{ sudo docker logs --tail=120 plane-migrator-{SERVICE}; exit 2; }}
  sleep 5
done
[ "$(sudo docker inspect plane-migrator-{SERVICE} --format '{{{{.State.Status}}}}:{{{{.State.ExitCode}}}}')" = "exited:0" ]

sudo docker compose -f docker-compose.yml -p {SERVICE} up -d --force-recreate plane-api plane-worker plane-beat-worker plane-web plane-admin plane-space plane-live
sleep 60

echo migration_gate
sudo docker exec plane-api-{SERVICE} sh -lc 'cd /code && python manage.py migrate --check && python manage.py makemigrations --check --dry-run'

echo route_probes
for p in / /god-mode /god-mode/ /api/instances/; do
  printf '%-18s ' "$p"
  curl -sS -o /tmp/plane-prod-probe -w 'http=%{{http_code}} size=%{{size_download}} final=%{{url_effective}} redirect=%{{redirect_url}}\n' -L --max-time 30 "https://{PUBLIC_HOST}$p"
done
"""


def main() -> None:
    if TARGET not in {"staging", "production"}:
        raise SystemExit("PLANE_TARGET_ENV must be staging or production")
    encoded = update_coolify_compose()
    script = staging_script(encoded) if TARGET == "staging" else production_script(encoded)
    print(ssh(script, timeout=1800))
    print(f"deploy_complete target={TARGET} service={SERVICE} sha={SHA}")


if __name__ == "__main__":
    main()
