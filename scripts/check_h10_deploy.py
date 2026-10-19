"""Exige H10 completo antes de publicar una entrega distinta de la servida en docs."""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

from deploy_no_retroceder_produccion import SELLO_DOCS_URL, leer_sello


def changed(repo: Path, published: str, candidate: str) -> bool:
    """Compara contra producción: un commit intermedio de docs no elude la primera entrega."""
    if not all(re.fullmatch(r"[0-9a-f]{40}", sha) for sha in (published, candidate)):
        raise ValueError("no se puede comparar H10 sin dos commits verificables")
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "diff",
            "--quiet",
            published,
            candidate,
            "--",
            "docs_site/benchmarks/h10",
            "docs_site/downloads/h10-benchmark.tar.gz",
            "docs_site/downloads/h10-benchmark.json",
        ],
        capture_output=True,
        check=False,
    )
    if result.returncode not in (0, 1):
        raise ValueError("no se pudo comparar H10 con producción")
    return result.returncode == 1


def require_complete(sha: str, repo: str, token: str | None) -> int:
    """Devuelve el run acreditado sólo con todos sus jobs verdes y un marcador completo."""
    if not token:
        raise ValueError("sin token no se puede verificar H10 completo")
    base = os.environ.get("GITHUB_API_URL", "https://api.github.com")

    def get(path):
        request = urllib.request.Request(
            f"{base}/repos/{repo}/{path}",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)

    query = urllib.parse.urlencode({"head_sha": sha, "per_page": 100})
    runs = get(f"actions/workflows/ci.yml/runs?{query}")["workflow_runs"]
    for run in runs:
        if not (
            run.get("head_sha") == sha
            and run.get("head_branch") == "main"
            and run.get("head_repository", {}).get("full_name") == repo
            and run.get("event") == "workflow_dispatch"
            and run.get("status") == "completed"
            and run.get("conclusion") == "success"
        ):
            continue
        body = get(f"actions/runs/{int(run['id'])}/jobs?per_page=100")
        jobs = body["jobs"]
        markers = [j for j in jobs if j.get("name") == "H10 cobertura completa acreditada"]
        if (
            body["total_count"] == len(jobs)
            and len(markers) == 1
            and all(
                j.get("status") == "completed" and j.get("conclusion") == "success" for j in jobs
            )
        ):
            return int(run["id"])
    raise ValueError(f"falta H10 completo verde de main para {sha}; despacha CI y reejecuta Deploy")


def main() -> int:
    """La vía automática falla cerrada; conserva el override manual explícito ya existente."""
    if os.environ.get("FORZAR", "").lower() == "true":
        print("::warning::forzar=true omite también la barrera H10 de producción")
        return 0
    try:
        published = leer_sello(os.environ.get("SELLO_DOCS_URL", SELLO_DOCS_URL)).sha
        if published is None:
            raise ValueError("no se pudo leer la huella de docs para acreditar H10")
        sha = os.environ["DEPLOY_SHA"]
        if changed(Path.cwd(), published, sha):
            run_id = require_complete(
                sha, os.environ["GITHUB_REPOSITORY"], os.environ.get("GITHUB_TOKEN")
            )
            print(f"H10 completo acreditado en run {run_id} para {sha}")
        else:
            print("La entrega H10 coincide con la que ya sirve producción")
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"::error::{error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
