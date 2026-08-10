"""Spike da §0 do change jira-openspec-coding-agent.

Valida, contra um Jira real, as premissas que o plano inteiro assume e que
nunca foram exercitadas: autenticação Basic, leitura de issue, a matriz de
transições do board, e comentário em ADF com os caracteres que o Jira rejeita.

Uso (a partir de open-swe/):
    pip install httpx
    python scripts/spike_jira.py --issue SSAI-1              # só leitura
    python scripts/spike_jira.py --issue SSAI-1 --write      # move o card e comenta

Config via ambiente ou arquivo .env.jira.local na raiz do repositório (um
nível acima de open-swe/ — não dentro dele):
    JIRA_BASE_URL=https://sensedia.atlassian.net
    JIRA_EMAIL=voce@sensedia.com
    JIRA_API_TOKEN=...        # id.atlassian.com -> Security -> API tokens

Com --write o script move o card por todas as colunas e no fim o devolve para
a coluna original. Use um card descartável.
"""

from __future__ import annotations

import argparse
import base64
import os
import pathlib
import re
import subprocess
import sys
from typing import Any

import httpx

DESIGN_COLUMNS = [
    "BACKLOG",
    "In Progress",
    "Em Revisão de Spec",
    "Spec Aprovada",
    "Ajustar Spec",
    "Em Code Review",
    "Code Review Aprovado",
    "Ajustar Code",
    "Em Merge",
    "Mergeado",
    "Done",
]

# Os caracteres que quebraram o Jira no projeto sensedia-ai-gateway
# (_pre_validate_add_comment): aspas curvas, travessões, espaço inquebrável.
NASTY = (
    "Teste de ADF “aspas curvas” e ‘simples’ — travessão, "
    "– meia-risca, espaço inquebrável, acentuação: ação, revisão, código."
)

OK, FAIL, SKIP = "PASS", "FAIL", "SKIP"
results: list[tuple[str, str, str]] = []


def report(name: str, status: str, detail: str = "") -> None:
    results.append((name, status, detail))
    mark = {OK: "[ok]  ", FAIL: "[FAIL]", SKIP: "[skip]"}[status]
    print(f"{mark} {name}" + (f" — {detail}" if detail else ""), flush=True)


def load_config() -> dict[str, str]:
    # scripts/spike_jira.py -> scripts -> open-swe -> repo root (where
    # .env.jira.local actually lives, one level above open-swe/).
    env_file = pathlib.Path(__file__).resolve().parent.parent.parent / ".env.jira.local"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

    missing = [
        k
        for k in ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN")
        if not os.environ.get(k, "").strip()
    ]
    if missing:
        sys.exit(
            f"faltando: {', '.join(missing)}.\n"
            f"Edite {env_file} e preencha os valores em branco."
        )

    token = os.environ["JIRA_API_TOKEN"].strip()
    if token.lower() in {"cole-aqui", "cole-seu-token-aqui", "changeme", "todo"}:
        sys.exit(f"JIRA_API_TOKEN ainda está com o placeholder. Edite {env_file}.")

    return {
        "base_url": os.environ["JIRA_BASE_URL"].rstrip("/"),
        "email": os.environ["JIRA_EMAIL"],
        "token": os.environ["JIRA_API_TOKEN"],
    }


def make_client(cfg: dict[str, str]) -> httpx.Client:
    raw = f"{cfg['email']}:{cfg['token']}".encode()
    return httpx.Client(
        base_url=cfg["base_url"],
        headers={
            "Authorization": "Basic " + base64.b64encode(raw).decode(),
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        timeout=30.0,
    )


def check_auth(client: httpx.Client) -> bool:
    r = client.get("/rest/api/3/myself")
    if r.status_code == 200:
        report("auth", OK, f"autenticado como {r.json().get('displayName')}")
        return True
    hint = " (token errado ou expirado)" if r.status_code == 401 else ""
    report("auth", FAIL, f"HTTP {r.status_code}{hint}")
    return False


def get_issue(client: httpx.Client, key: str) -> dict[str, Any] | None:
    r = client.get(f"/rest/api/3/issue/{key}", params={"fields": "summary,status"})
    if r.status_code != 200:
        report("getIssue", FAIL, f"HTTP {r.status_code} para {key}")
        return None
    fields = r.json()["fields"]
    status = fields["status"]["name"]
    report("getIssue", OK, f"{key} — {fields['summary']!r} em {status!r}")
    return {"summary": fields["summary"], "status": status}


def check_branch_name(summary: str, key: str) -> None:
    """Task 8.4: o slug vem do título da issue e precisa virar ref válido."""
    slug = re.sub(r"[^a-z0-9]+", "-", summary.lower()).strip("-")[:40].strip("-")
    branch = f"feat/spec-{key}-{slug}"
    proc = subprocess.run(
        ["git", "check-ref-format", "--branch", branch], capture_output=True, text=True
    )
    if proc.returncode == 0:
        report("branch name", OK, branch)
    else:
        report("branch name", FAIL, f"{branch} rejeitado pelo git")


def transitions_for(client: httpx.Client, key: str) -> dict[str, str]:
    """Mapa nome-da-coluna-destino -> transition id, a partir do status atual."""
    r = client.get(f"/rest/api/3/issue/{key}/transitions")
    if r.status_code != 200:
        return {}
    return {t["to"]["name"]: t["id"] for t in r.json().get("transitions", [])}


def move_to(client: httpx.Client, key: str, column: str) -> tuple[bool, str]:
    available = transitions_for(client, key)
    if column not in available:
        return False, f"destino indisponível (opções: {', '.join(sorted(available)) or 'nenhuma'})"
    r = client.post(
        f"/rest/api/3/issue/{key}/transitions", json={"transition": {"id": available[column]}}
    )
    if r.status_code == 204:
        return True, ""
    return False, f"HTTP {r.status_code} {r.text[:200]}"


def discover_columns(client: httpx.Client, project: str) -> list[str]:
    """Status realmente configurados no projeto, em vez de assumir os do design."""
    r = client.get(f"/rest/api/3/project/{project}/statuses")
    if r.status_code != 200:
        report("descobrir colunas", FAIL, f"HTTP {r.status_code}")
        return []
    seen: list[str] = []
    for issue_type in r.json():
        for status in issue_type["statuses"]:
            if status["name"] not in seen:
                seen.append(status["name"])
    report("descobrir colunas", OK, f"{len(seen)} status no projeto {project}")
    return seen


def check_columns_match_design(actual: list[str]) -> None:
    extra = [c for c in actual if c not in DESIGN_COLUMNS]
    missing = [c for c in DESIGN_COLUMNS if c not in actual]
    if not extra and not missing:
        report("colunas x design", OK, f"as {len(DESIGN_COLUMNS)} colunas batem")
        return
    detail = []
    if missing:
        detail.append(f"no design mas não no Jira: {', '.join(missing)}")
    if extra:
        detail.append(f"no Jira mas não no design: {', '.join(extra)}")
    report("colunas x design", FAIL, " | ".join(detail))


def check_transition_matrix(client: httpx.Client, key: str, COLUMNS: list[str]) -> None:
    """Percorre as 11 colunas e registra, de cada uma, quais destinos existem.

    É o teste de 'transições globais': cada linha da matriz deve ter 10 destinos.
    """
    print("\n  matriz de transições (linha = coluna atual, n = destinos alcançáveis)")
    incomplete: list[str] = []

    for column in COLUMNS:
        moved, err = move_to(client, key, column)
        if not moved:
            print(f"    {column:<30} — não consegui mover: {err}")
            incomplete.append(column)
            continue
        targets = set(transitions_for(client, key))
        missing = [c for c in COLUMNS if c != column and c not in targets]
        flag = "ok" if not missing else f"faltam {len(missing)}: {', '.join(missing)}"
        print(f"    {column:<30} n={len(targets):<3} {flag}")
        if missing:
            incomplete.append(column)

    if not incomplete:
        report("transições globais", OK, "toda coluna alcança todas as outras")
    else:
        report(
            "transições globais",
            FAIL,
            f"{len(incomplete)} coluna(s) sem alcance total — configure "
            '"Allow all statuses to transition to this one"',
        )


def check_adf_comment(client: httpx.Client, key: str) -> None:
    body = {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": NASTY}]},
                {
                    "type": "codeBlock",
                    "attrs": {"language": "python"},
                    "content": [{"type": "text", "text": 'print("spike ok")'}],
                },
            ],
        }
    }
    r = client.post(f"/rest/api/3/issue/{key}/comment", json=body)
    if r.status_code == 201:
        report("comentário ADF", OK, "aspas curvas, travessões, NBSP e code block aceitos")
    else:
        report("comentário ADF", FAIL, f"HTTP {r.status_code} {r.text[:300]}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--issue", required=True, help="key de um card descartável, ex.: SSAI-1")
    parser.add_argument("--write", action="store_true", help="permite mover o card e comentar")
    parser.add_argument(
        "--project",
        help="descobre os status reais do projeto em vez de usar a lista do design",
    )
    args = parser.parse_args()

    cfg = load_config()
    print(f"Jira: {cfg['base_url']} como {cfg['email']}\n")

    with make_client(cfg) as client:
        if not check_auth(client):
            return 1

        issue = get_issue(client, args.issue)
        if issue is None:
            return 1

        check_branch_name(issue["summary"], args.issue)

        columns = discover_columns(client, args.project) if args.project else DESIGN_COLUMNS
        if not columns:
            return 1
        if args.project:
            check_columns_match_design(columns)

        if not args.write:
            report("transições globais", SKIP, "requer --write")
            report("comentário ADF", SKIP, "requer --write")
        else:
            check_transition_matrix(client, args.issue, columns)
            check_adf_comment(client, args.issue)

            restored, err = move_to(client, args.issue, issue["status"])
            report(
                "restaurar coluna original",
                OK if restored else FAIL,
                issue["status"] if restored else err,
            )

    failed = [name for name, status, _ in results if status == FAIL]
    skipped = sum(1 for _, status, _ in results if status == SKIP)
    print(f"\n{len(results) - len(failed) - skipped} ok, {len(failed)} falha(s), {skipped} pulado(s)")
    if failed:
        print("falhou: " + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
