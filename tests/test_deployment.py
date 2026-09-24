"""Deployment and portability guarantees (static checks; nothing is built or run)."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION = [p for d in ("src", "app", "scripts", "configs") for p in (ROOT / d).rglob("*")
              if p.is_file() and p.suffix in (".py", ".yaml", ".yml", ".ps1", ".sh", ".toml")]
ABSOLUTE = re.compile(r"(?i)\b[a-z]:[\/](adm|users)\b|/home/\w+|/v/adm")


def test_no_absolute_machine_paths_in_production_code():
    offenders = [p.relative_to(ROOT).as_posix() for p in PRODUCTION
                 if ABSOLUTE.search(p.read_text(encoding="utf-8", errors="replace"))]
    assert not offenders, offenders


def test_image_excludes_data_models_and_secrets():
    ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").split()
    for must in ("data/raw", "data/external", "models", "outputs", ".venv", ".git", ".env",
                 "data/metadata/annotations"):
        assert must in ignore, must
    docker = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "USER appuser" in docker and "data/raw" not in docker.split("COPY")[-1].split("\n")[0]


def test_compose_publishes_on_localhost_only():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    for name, svc in compose["services"].items():
        for port in svc.get("ports", []):
            assert str(port).startswith("127.0.0.1:"), (name, port)
    assert compose["services"]["api"]["volumes"][0].endswith(":ro")


def test_start_scripts_exist_and_use_relative_paths():
    for name in ("setup.ps1", "setup.sh", "start_app.ps1", "start_app.sh", "start_api.ps1", "start_api.sh"):
        text = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert ".venv" in text and not ABSOLUTE.search(text)
    assert "127.0.0.1" in (ROOT / "scripts" / "start_api.sh").read_text(encoding="utf-8")
