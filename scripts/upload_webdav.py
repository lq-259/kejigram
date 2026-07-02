#!/usr/bin/env python3
"""Upload date-scoped zaihua_pipeline outputs to a WebDAV destination."""

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import quote

import requests

# Import shared utilities
_script_dir = Path(__file__).parent
if str(_script_dir) not in sys.path:
    sys.path.insert(0, str(_script_dir))
from common import ROOT

DEFAULT_BASE_URL = "http://192.168.15.5:5244/dav"
DEFAULT_REMOTE_ROOT = "/和彩云/视频"


def load_env(path):
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def quote_path(path):
    return "/".join(quote(part) for part in path.strip("/").split("/") if part)


def dav_url(base_url, remote_path):
    base = base_url.rstrip("/")
    quoted = quote_path(remote_path)
    return f"{base}/{quoted}" if quoted else base


def ensure_remote_dir(session, base_url, remote_dir):
    current = ""
    for part in [p for p in remote_dir.strip("/").split("/") if p]:
        current = f"{current}/{part}"
        url = dav_url(base_url, current)
        resp = session.request("MKCOL", url, timeout=60)
        if resp.status_code not in (201, 405):
            raise RuntimeError(f"MKCOL failed {resp.status_code}: {current} | {resp.text[:200]}")


def iter_files(local_dir):
    skip_names = {"__pycache__", "segments"}
    for path in sorted(local_dir.rglob("*")):
        if any(part in skip_names for part in path.parts):
            continue
        if path.is_file():
            yield path


def upload_file(session, base_url, local_file, remote_file):
    url = dav_url(base_url, remote_file)
    with local_file.open("rb") as f:
        resp = session.put(url, data=f, timeout=300)
    if resp.status_code not in (200, 201, 204):
        raise RuntimeError(f"PUT failed {resp.status_code}: {remote_file} | {resp.text[:200]}")


def upload_date(date_str, dry_run=False):
    from common import load_env_file
    load_env_file(Path(__file__).parent.parent / ".env")
    base_url = os.environ.get("WEBDAV_BASE_URL", DEFAULT_BASE_URL)
    username = os.environ.get("WEBDAV_USERNAME")
    password = os.environ.get("WEBDAV_PASSWORD")
    remote_root = os.environ.get("WEBDAV_REMOTE_ROOT", DEFAULT_REMOTE_ROOT).rstrip("/")
    if not username or not password:
        raise RuntimeError("WEBDAV_USERNAME and WEBDAV_PASSWORD are required")

    local_dir = ROOT / date_str
    if not local_dir.exists():
        raise RuntimeError(f"Local date directory does not exist: {local_dir}")

    remote_dir = f"{remote_root}/zaihua_pipeline/{date_str}"
    files = list(iter_files(local_dir))
    if dry_run:
        print(f"[webdav] dry run: {local_dir} -> {base_url}{remote_dir}")
        for path in files:
            rel = path.relative_to(local_dir).as_posix()
            print(f"  {rel}")
        return len(files)

    session = requests.Session()
    session.auth = (username, password)
    ensure_remote_dir(session, base_url, remote_dir)

    for path in files:
        rel = path.relative_to(local_dir).as_posix()
        remote_file = f"{remote_dir}/{rel}"
        ensure_remote_dir(session, base_url, str(Path(remote_file).parent).replace("\\", "/"))
        upload_file(session, base_url, path, remote_file)
        print(f"    uploaded {rel}")

    print(f"[webdav] uploaded {len(files)} files to {remote_dir}")
    return len(files)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("date", help="YYYY-MM-DD date directory under zaihua_pipeline")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    upload_date(args.date, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
