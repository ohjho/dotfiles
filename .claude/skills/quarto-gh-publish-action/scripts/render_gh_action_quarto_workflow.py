# /// script
# requires-python = ">=3.10"
# dependencies = ["typer>=0.12", "loguru>=0.7"]
# ///
"""Render a GitHub Actions workflow that builds a Quarto website and deploys it to GitHub Pages.

The ``quarto-gh-publish-action`` skill interviews the user, then calls this script with one
flag per answer so the workflow file is generated the same way every time instead of being
typed by hand::

    uv run scripts/render_gh_action_quarto_workflow.py --self-test
    uv run scripts/render_gh_action_quarto_workflow.py --quarto-version 1.6.39 \\
        -i '.claude/**' -i CLAUDE.md -o .github/workflows/publish.yml
    uv run scripts/render_gh_action_quarto_workflow.py --mechanism gh-pages --pr-check -o -
    uv run scripts/render_gh_action_quarto_workflow.py --runtime python -p pandas --dispatch

Two deployment mechanisms are supported:

``artifact`` (default)
    A ``build`` job renders the site and uploads ``_site/`` with
    ``actions/upload-pages-artifact``; a ``deploy`` job publishes it with
    ``actions/deploy-pages``. No ``gh-pages`` branch. The repository's Pages source must be
    set to "GitHub Actions" once.

``gh-pages``
    One ``publish`` job renders the site and pushes the output to the ``gh-pages`` branch
    with ``quarto-dev/quarto-actions/publish``. Requires a one-time local
    ``quarto publish gh-pages`` to create the branch and ``_publish.yml``; the Pages source
    is that branch.

``--pr-check`` adds a ``pull_request`` trigger that renders but never deploys, expressed as
``if: github.event_name != 'pull_request'`` on the deploy steps rather than a second render.

Output is assembled from string templates rather than a YAML dumper so comments and key
order are stable and the result diffs cleanly against a hand-written file. Exit codes:
``0`` written, ``1`` self-test failed, ``2`` usage or validation error.
"""

from __future__ import annotations

import doctest
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional

import typer
from loguru import logger

VERSION_RE = re.compile(r"^(release|pre-release|\d+\.\d+\.\d+)$")
DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$", re.I)
PR_GUARD = "github.event_name != 'pull_request'"
PR_GROUP = "${{ github.event_name == 'pull_request' && format('pr-{0}', github.event.pull_request.number) || 'pages' }}"


class Mechanism(str, Enum):
    """How the rendered site reaches GitHub Pages."""

    ARTIFACT = "artifact"
    GH_PAGES = "gh-pages"


class Runtime(str, Enum):
    """Which execution engine the runner installs for executable code cells."""

    NONE = "none"
    PYTHON = "python"
    R = "r"


@dataclass(frozen=True)
class WorkflowConfig:
    """Every knob the workflow exposes, with the same defaults as the CLI.

    Attributes:
        mechanism: ``artifact`` (Pages artifact + deploy-pages) or ``gh-pages`` (branch).
        quarto_version: ``release``, ``pre-release``, or an exact ``N.N.N``.
        branch: Branch that triggers deploys and that pull requests target.
        push: Emit the ``push`` trigger.
        dispatch: Emit ``workflow_dispatch``.
        pr_check: Emit a ``pull_request`` trigger that renders but does not deploy.
        schedule: Optional 5-field cron expression.
        paths_ignore: Paths whose changes should not trigger the workflow.
        cancel_in_progress: Cancel an in-flight run when a new one starts.
        runtime: ``none``, ``python``, or ``r``.
        python_packages: Extra Python packages (Jupyter is always installed).
        python_requirements: A requirements file instead of a package list.
        python_version: Python version for ``actions/setup-python``.
        r_packages: Extra R packages (rmarkdown and knitr are always installed).
        custom_domain: Domain written to ``CNAME`` inside the rendered output.
        site_dir: Quarto ``output-dir``; the folder that gets uploaded.
        name: Workflow display name.
        header: Emit the explanatory comment block at the top of the file.
    """

    mechanism: Mechanism = Mechanism.ARTIFACT
    quarto_version: str = "release"
    branch: str = "main"
    push: bool = True
    dispatch: bool = False
    pr_check: bool = False
    schedule: Optional[str] = None
    paths_ignore: tuple = field(default_factory=tuple)
    cancel_in_progress: bool = False
    runtime: Runtime = Runtime.NONE
    python_packages: tuple = field(default_factory=tuple)
    python_requirements: Optional[str] = None
    python_version: str = "3.12"
    r_packages: tuple = field(default_factory=tuple)
    custom_domain: Optional[str] = None
    site_dir: str = "_site"
    name: str = "Publish Quarto site"
    header: bool = True


# --------------------------------------------------------------------------- validation


def validate(cfg: WorkflowConfig) -> List[str]:
    """Return every reason the config cannot be rendered; empty when it is valid.

    Args:
        cfg: The configuration to check.

    Returns:
        Human-readable error strings, one per problem.

    Example:
        >>> validate(WorkflowConfig())
        []
        >>> validate(WorkflowConfig(quarto_version="v1.6.39"))
        ['--quarto-version must be release, pre-release, or N.N.N without a leading v (got v1.6.39)']
        >>> validate(WorkflowConfig(python_packages=("pandas",)))
        ['--python-package requires --runtime python']
        >>> validate(WorkflowConfig(schedule="daily"))
        ['--schedule must be a 5-field cron expression like "0 6 * * 1" (got daily)']
        >>> validate(WorkflowConfig(push=False))
        ['no trigger left: enable at least one of --push, --dispatch, --pr-check, --schedule']
        >>> validate(WorkflowConfig(push=False, dispatch=True, paths_ignore=("docs/**",)))
        ['--paths-ignore only applies to push and pull_request triggers']
    """
    errors: List[str] = []
    if not VERSION_RE.match(cfg.quarto_version):
        errors.append(
            "--quarto-version must be release, pre-release, or N.N.N without a leading v "
            f"(got {cfg.quarto_version})"
        )
    if not cfg.branch.strip():
        errors.append("--branch must not be empty")
    if cfg.schedule is not None and len(cfg.schedule.split()) != 5:
        errors.append(f'--schedule must be a 5-field cron expression like "0 6 * * 1" (got {cfg.schedule})')
    if not (cfg.push or cfg.dispatch or cfg.pr_check or cfg.schedule):
        errors.append("no trigger left: enable at least one of --push, --dispatch, --pr-check, --schedule")
    if cfg.paths_ignore and not (cfg.push or cfg.pr_check):
        errors.append("--paths-ignore only applies to push and pull_request triggers")
    if cfg.python_packages and cfg.runtime is not Runtime.PYTHON:
        errors.append("--python-package requires --runtime python")
    if cfg.python_requirements and cfg.runtime is not Runtime.PYTHON:
        errors.append("--python-requirements requires --runtime python")
    if cfg.python_packages and cfg.python_requirements:
        errors.append("use either --python-package or --python-requirements, not both")
    if cfg.r_packages and cfg.runtime is not Runtime.R:
        errors.append("--r-package requires --runtime r")
    if cfg.custom_domain is not None and not DOMAIN_RE.match(cfg.custom_domain):
        errors.append(f"--custom-domain must be a bare hostname like blog.example.com (got {cfg.custom_domain})")
    if not cfg.site_dir.strip() or cfg.site_dir.startswith("/"):
        errors.append("--site-dir must be a relative directory like _site")
    return errors


# --------------------------------------------------------------------------- blocks


def quote(value: str) -> str:
    """Wrap a YAML scalar in double quotes, escaping embedded quotes.

    Example:
        >>> quote('.claude/**')
        '".claude/**"'
        >>> quote('say "hi"')
        '"say \\\\"hi\\\\""'
    """
    return '"' + value.replace('"', '\\"') + '"'


def header_comment(cfg: WorkflowConfig) -> List[str]:
    """Explain the file to the next reader: mechanism, one-time setup, runtime policy.

    Example:
        >>> lines = header_comment(WorkflowConfig())
        >>> lines[0]
        '# Render the Quarto site and deploy it to GitHub Pages.'
        >>> any('Source: "GitHub Actions"' in l for l in lines)
        True
        >>> any('quarto publish gh-pages' in l for l in header_comment(WorkflowConfig(mechanism=Mechanism.GH_PAGES)))
        True
        >>> header_comment(WorkflowConfig(header=False))
        []
    """
    if not cfg.header:
        return []
    lines = ["# Render the Quarto site and deploy it to GitHub Pages.", "#"]
    if cfg.mechanism is Mechanism.ARTIFACT:
        lines += [
            "# One-time setup in the repo: Settings -> Pages -> Build and deployment ->",
            '# Source: "GitHub Actions". No gh-pages branch is used; the rendered output',
            "# is uploaded as a Pages artifact and deployed from there.",
        ]
    else:
        lines += [
            "# One-time setup: run `quarto publish gh-pages` locally once to create the",
            "# gh-pages branch and _publish.yml, commit _publish.yml, then set Settings ->",
            "# Pages -> Source to the gh-pages branch (root). Every run afterwards renders",
            "# here and pushes the output to that branch.",
        ]
    lines.append("#")
    if cfg.runtime is Runtime.NONE:
        lines += [
            "# No Python or R is installed. Posts should freeze computational output",
            "# (freeze: true) and commit _freeze/ so the runner never executes code cells.",
        ]
    elif cfg.runtime is Runtime.PYTHON:
        lines += ["# Python and Jupyter are installed so executable cells run on the runner."]
    else:
        lines += ["# R, rmarkdown and knitr are installed so executable cells run on the runner."]
    if cfg.pr_check:
        lines += ["#", "# Pull requests render the site as a check but never deploy."]
    if cfg.custom_domain:
        lines += ["#", f"# CNAME is written into the output on every run so {cfg.custom_domain} sticks."]
    lines.append("")
    return lines


def triggers_block(cfg: WorkflowConfig) -> List[str]:
    """Emit the ``on:`` block.

    Example:
        >>> print("\\n".join(triggers_block(WorkflowConfig(paths_ignore=(".claude/**",)))))
        on:
          push:
            branches: [main]
            paths-ignore:
              - ".claude/**"
        >>> print("\\n".join(triggers_block(WorkflowConfig(push=False, dispatch=True, schedule="0 6 * * 1"))))
        on:
          workflow_dispatch:
          schedule:
            - cron: "0 6 * * 1"
        >>> "  pull_request:" in triggers_block(WorkflowConfig(pr_check=True))
        True
    """
    lines = ["on:"]
    ignore = ["    paths-ignore:"] + [f"      - {quote(p)}" for p in cfg.paths_ignore] if cfg.paths_ignore else []
    if cfg.push:
        lines += ["  push:", f"    branches: [{cfg.branch}]"] + ignore
    if cfg.pr_check:
        lines += ["  pull_request:", f"    branches: [{cfg.branch}]"] + ignore
    if cfg.dispatch:
        lines.append("  workflow_dispatch:")
    if cfg.schedule:
        lines += ["  schedule:", f"    - cron: {quote(cfg.schedule)}"]
    return lines


def permissions_block(cfg: WorkflowConfig) -> List[str]:
    """Least privilege for the chosen mechanism.

    Example:
        >>> permissions_block(WorkflowConfig())
        ['permissions:', '  contents: read', '  pages: write', '  id-token: write']
        >>> permissions_block(WorkflowConfig(mechanism=Mechanism.GH_PAGES))
        ['permissions:', '  contents: write']
    """
    if cfg.mechanism is Mechanism.ARTIFACT:
        return ["permissions:", "  contents: read", "  pages: write", "  id-token: write"]
    return ["permissions:", "  contents: write"]


def concurrency_block(cfg: WorkflowConfig) -> List[str]:
    """One deploy at a time; PR checks get their own group when ``pr_check`` is on.

    Example:
        >>> concurrency_block(WorkflowConfig())
        ['concurrency:', '  group: pages', '  cancel-in-progress: false']
        >>> concurrency_block(WorkflowConfig(pr_check=True, cancel_in_progress=True))[1]
        "  group: ${{ github.event_name == 'pull_request' && format('pr-{0}', github.event.pull_request.number) || 'pages' }}"
        >>> concurrency_block(WorkflowConfig(mechanism=Mechanism.GH_PAGES))[1]
        '  group: gh-pages'
    """
    base = "pages" if cfg.mechanism is Mechanism.ARTIFACT else "gh-pages"
    group = PR_GROUP.replace("'pages'", f"'{base}'") if cfg.pr_check else base
    return ["concurrency:", f"  group: {group}", f"  cancel-in-progress: {'true' if cfg.cancel_in_progress else 'false'}"]


def step(name: str, *body: str, guard: bool = False) -> List[str]:
    """Format one step; ``guard`` adds the pull-request ``if:``.

    Example:
        >>> step("Render site", "run: quarto render")
        ['      - name: Render site', '        run: quarto render']
        >>> step("Deploy", "uses: x@v1", guard=True)[1]
        "        if: github.event_name != 'pull_request'"
    """
    lines = [f"      - name: {name}"]
    if guard:
        lines.append(f"        if: {PR_GUARD}")
    lines += [f"        {b}" for b in body]
    return lines


def quarto_setup_step(cfg: WorkflowConfig) -> List[str]:
    """The ``quarto-actions/setup`` step with the requested version.

    Example:
        >>> quarto_setup_step(WorkflowConfig(quarto_version="1.6.39"))[-1]
        '          version: 1.6.39'
    """
    return step("Set up Quarto", "uses: quarto-dev/quarto-actions/setup@v2", "with:", f"  version: {cfg.quarto_version}")


def runtime_steps(cfg: WorkflowConfig) -> List[str]:
    """Steps that install Python + Jupyter or R + knitr, or nothing.

    Example:
        >>> runtime_steps(WorkflowConfig())
        []
        >>> "\\n".join(runtime_steps(WorkflowConfig(runtime=Runtime.PYTHON, python_packages=("pandas",)))).count("uv pip install --system jupyter pandas")
        1
        >>> "\\n".join(runtime_steps(WorkflowConfig(runtime=Runtime.PYTHON, python_requirements="requirements.txt"))).count("-r requirements.txt")
        1
        >>> "            any::tidyverse" in runtime_steps(WorkflowConfig(runtime=Runtime.R, r_packages=("tidyverse",)))
        True
    """
    if cfg.runtime is Runtime.NONE:
        return []
    if cfg.runtime is Runtime.PYTHON:
        install = (
            f"run: uv pip install --system jupyter -r {cfg.python_requirements}"
            if cfg.python_requirements
            else "run: uv pip install --system " + " ".join(("jupyter",) + tuple(cfg.python_packages))
        )
        return (
            step("Set up Python", "uses: actions/setup-python@v5", "with:", f"  python-version: {quote(cfg.python_version)}")
            + step("Set up uv", "uses: astral-sh/setup-uv@v5")
            + step("Install Python packages", install)
        )
    pkgs = ["any::rmarkdown", "any::knitr"] + [f"any::{p}" for p in cfg.r_packages]
    return step("Set up R", "uses: r-lib/actions/setup-r@v2", "with:", "  use-public-rspm: true") + step(
        "Install R packages", "uses: r-lib/actions/setup-r-dependencies@v2", "with:", "  packages: |", *[f"    {p}" for p in pkgs]
    )


def cname_step(cfg: WorkflowConfig) -> List[str]:
    """Write ``CNAME`` into the output so a custom domain survives every deploy.

    Example:
        >>> cname_step(WorkflowConfig())
        []
        >>> cname_step(WorkflowConfig(custom_domain="blog.example.com"))[-1]
        '        run: echo "blog.example.com" > _site/CNAME'
    """
    if not cfg.custom_domain:
        return []
    return step("Write CNAME", f"run: echo {quote(cfg.custom_domain)} > {cfg.site_dir}/CNAME")


def build_job(cfg: WorkflowConfig) -> List[str]:
    """The render job for the ``artifact`` mechanism.

    Example:
        >>> lines = build_job(WorkflowConfig())
        >>> lines[0], lines[1]
        ('  build:', '    runs-on: ubuntu-latest')
        >>> "\\n".join(build_job(WorkflowConfig(pr_check=True))).count(PR_GUARD)
        2
    """
    return (
        ["  build:", "    runs-on: ubuntu-latest", "    steps:"]
        + step("Check out", "uses: actions/checkout@v4")
        + quarto_setup_step(cfg)
        + runtime_steps(cfg)
        + step("Configure Pages", "uses: actions/configure-pages@v5", guard=cfg.pr_check)
        + step("Render site", "run: quarto render")
        + cname_step(cfg)
        + step("Upload Pages artifact", "uses: actions/upload-pages-artifact@v3", "with:", f"  path: {cfg.site_dir}", guard=cfg.pr_check)
    )


def deploy_job(cfg: WorkflowConfig) -> List[str]:
    """The ``deploy-pages`` job for the ``artifact`` mechanism.

    Example:
        >>> deploy_job(WorkflowConfig())[:3]
        ['  deploy:', '    needs: build', '    runs-on: ubuntu-latest']
        >>> deploy_job(WorkflowConfig(pr_check=True))[1]
        "    if: github.event_name != 'pull_request'"
    """
    lines = ["  deploy:"]
    if cfg.pr_check:
        lines.append(f"    if: {PR_GUARD}")
    lines += [
        "    needs: build",
        "    runs-on: ubuntu-latest",
        "    environment:",
        "      name: github-pages",
        "      url: ${{ steps.deployment.outputs.page_url }}",
        "    steps:",
    ]
    return lines + step("Deploy to GitHub Pages", "id: deployment", "uses: actions/deploy-pages@v4")


def publish_job(cfg: WorkflowConfig) -> List[str]:
    """The single render-and-push job for the ``gh-pages`` mechanism.

    Example:
        >>> text = "\\n".join(publish_job(WorkflowConfig(mechanism=Mechanism.GH_PAGES, pr_check=True)))
        >>> text.count("run: quarto render"), text.count("render: false"), text.count(PR_GUARD)
        (1, 1, 1)
    """
    return (
        ["  publish:", "    runs-on: ubuntu-latest", "    steps:"]
        + step("Check out", "uses: actions/checkout@v4")
        + quarto_setup_step(cfg)
        + runtime_steps(cfg)
        + step("Render site", "run: quarto render")
        + cname_step(cfg)
        + step(
            "Publish to gh-pages",
            "uses: quarto-dev/quarto-actions/publish@v2",
            "with:",
            "  target: gh-pages",
            "  render: false",
            "env:",
            "  GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}",
            guard=cfg.pr_check,
        )
    )


def render(cfg: WorkflowConfig) -> str:
    """Assemble the whole workflow file.

    Args:
        cfg: A validated configuration (call :func:`validate` first).

    Returns:
        The YAML text, ending in a newline.

    Example:
        >>> text = render(WorkflowConfig(quarto_version="1.6.39",
        ...                              paths_ignore=(".claude/**", "CLAUDE.md", ".gitignore"), header=False))
        >>> print(text[:text.index("permissions:")].rstrip())
        name: Publish Quarto site
        <BLANKLINE>
        on:
          push:
            branches: [main]
            paths-ignore:
              - ".claude/**"
              - "CLAUDE.md"
              - ".gitignore"
        >>> "cancel-in-progress: false" in render(WorkflowConfig())
        True
        >>> render(WorkflowConfig(pr_check=True)).count(PR_GUARD)
        3
        >>> "  deploy:" in render(WorkflowConfig(mechanism=Mechanism.GH_PAGES))
        False
        >>> render(WorkflowConfig()).endswith("\\n")
        True
    """
    jobs = ["jobs:"]
    if cfg.mechanism is Mechanism.ARTIFACT:
        jobs += build_job(cfg) + [""] + deploy_job(cfg)
    else:
        jobs += publish_job(cfg)
    blocks = [
        header_comment(cfg) + [f"name: {cfg.name}"],
        triggers_block(cfg),
        permissions_block(cfg),
        concurrency_block(cfg),
        jobs,
    ]
    return "\n\n".join("\n".join(b) for b in blocks) + "\n"


# --------------------------------------------------------------------------- CLI

app = typer.Typer(add_completion=False, help=__doc__.split("\n\n")[0])


def configure_logging(verbose: bool) -> None:
    """Route loguru to stderr at INFO, or DEBUG with ``--verbose``."""
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if verbose else "INFO", format="<level>{level:<7}</level> {message}")


def self_test() -> int:
    """Run the module doctests and return the failure count."""
    result = doctest.testmod(sys.modules[__name__], optionflags=doctest.NORMALIZE_WHITESPACE)
    logger.info(f"{result.attempted} tests, {result.failed} failed")
    return result.failed


@app.command()
def main(
    mechanism: Mechanism = typer.Option(Mechanism.ARTIFACT, "--mechanism", help="artifact: upload-pages-artifact + deploy-pages. gh-pages: quarto-actions/publish to the gh-pages branch."),
    quarto_version: str = typer.Option("release", "--quarto-version", help="release, pre-release, or an exact N.N.N (no leading v)."),
    branch: str = typer.Option("main", "--branch", help="Branch that deploys; also the pull_request target."),
    push: bool = typer.Option(True, "--push/--no-push", help="Trigger on pushes to --branch."),
    dispatch: bool = typer.Option(False, "--dispatch/--no-dispatch", help="Add a manual workflow_dispatch trigger."),
    pr_check: bool = typer.Option(False, "--pr-check/--no-pr-check", help="Render on pull requests without deploying."),
    schedule: Optional[str] = typer.Option(None, "--schedule", help='5-field cron, e.g. "0 6 * * 1".'),
    paths_ignore: List[str] = typer.Option([], "--paths-ignore", "-i", help="Path pattern that should not trigger a run (repeatable)."),
    cancel_in_progress: bool = typer.Option(False, "--cancel-in-progress/--no-cancel-in-progress", help="Cancel an in-flight run when a new one starts (default: queue)."),
    runtime: Runtime = typer.Option(Runtime.NONE, "--runtime", help="Engine for executable cells: none, python, or r."),
    python_package: List[str] = typer.Option([], "--python-package", "-p", help="Extra Python package (repeatable; jupyter is always installed)."),
    python_requirements: Optional[str] = typer.Option(None, "--python-requirements", help="Install from this requirements file instead of -p."),
    python_version: str = typer.Option("3.12", "--python-version", help="Python version for actions/setup-python."),
    r_package: List[str] = typer.Option([], "--r-package", help="Extra R package (repeatable; rmarkdown and knitr are always installed)."),
    custom_domain: Optional[str] = typer.Option(None, "--custom-domain", help="Write this hostname to CNAME in the rendered output."),
    site_dir: str = typer.Option("_site", "--site-dir", help="Quarto output-dir; the folder that is uploaded."),
    name: str = typer.Option("Publish Quarto site", "--name", help="Workflow display name."),
    header: bool = typer.Option(True, "--header/--no-header", help="Emit the explanatory comment block at the top."),
    output: Path = typer.Option(Path(".github/workflows/publish.yml"), "--output", "-o", help="Destination file; '-' prints to stdout."),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing --output."),
    run_self_test: bool = typer.Option(False, "--self-test", help="Run the doctests and exit; nothing is written."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Debug logging."),
) -> None:
    """Render a GitHub Actions workflow that publishes a Quarto website to GitHub Pages."""
    configure_logging(verbose)
    if run_self_test:
        raise typer.Exit(code=1 if self_test() else 0)

    cfg = WorkflowConfig(
        mechanism=mechanism,
        quarto_version=quarto_version,
        branch=branch,
        push=push,
        dispatch=dispatch,
        pr_check=pr_check,
        schedule=schedule,
        paths_ignore=tuple(paths_ignore),
        cancel_in_progress=cancel_in_progress,
        runtime=runtime,
        python_packages=tuple(python_package),
        python_requirements=python_requirements,
        python_version=python_version,
        r_packages=tuple(r_package),
        custom_domain=custom_domain,
        site_dir=site_dir,
        name=name,
        header=header,
    )
    logger.debug(f"config: {cfg}")
    errors = validate(cfg)
    if errors:
        for err in errors:
            logger.error(err)
        raise typer.Exit(code=2)

    text = render(cfg)
    if str(output) == "-":
        sys.stdout.write(text)
        return
    if output.exists() and not force:
        logger.error(f"{output} exists; pass --force to overwrite it (diff it first)")
        raise typer.Exit(code=2)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text)
    logger.info(f"wrote {output} ({mechanism.value}, quarto {quarto_version}, runtime {runtime.value})")


if __name__ == "__main__":
    app()
