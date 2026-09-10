# dotfiles
configs, scripts, tools

- [Scripts](#scripts) — self-contained Python scripts, runnable with `uv run` locally or from their GitHub Pages URL
- [Screen sessions](#screen-sessions) — recreate GNU `screen` sessions after a reboot from `configs/screens.yaml`
- [Claude Code](#claude-code) — run Claude Code against OpenRouter or Ollama via `.env`

## Scripts

The scripts in [`scripts/`](scripts/) are self-contained ([PEP 723](https://peps.python.org/pep-0723/) inline deps) and can be run directly from this repo with [`uv`](https://docs.astral.sh/uv/).

These are served via [GitHub Pages](https://ohjho.github.io/dotfiles/) so the remote URL is short:

```sh
uv run https://ohjho.github.io/dotfiles/scripts/convert_media.py --help
uv run https://ohjho.github.io/dotfiles/scripts/probe_media.py --help
```

> The longer `https://raw.githubusercontent.com/ohjho/dotfiles/main/scripts/<name>.py` form keeps working too.

for scripts that requires environment variables ( see [.env.example](.env.example)) you could run it like:
```sh
uv run --env-file .env https://ohjho.github.io/dotfiles/scripts/upload_imgbb.py path/to/image.jpg
```

## Screen sessions

[`configs/screens.yaml`](configs/screens.yaml) describes the GNU `screen` sessions (and the servers inside them) to bring back after a reboot; [`scripts/screen_sessions.py`](scripts/screen_sessions.py) does the work:

```sh
uv run scripts/screen_sessions.py status     # what is running vs. the manifest
uv run scripts/screen_sessions.py launch     # recreate whatever is missing (existing sessions are skipped)
uv run scripts/screen_sessions.py snapshot   # dump the live layout as YAML to curate into the manifest
```

Outside the repo both the script and the manifest are fetched from GitHub Pages: `uv run https://ohjho.github.io/dotfiles/scripts/screen_sessions.py status`.

> **Why a custom script?** macOS ships GNU screen 4.00.03 (2006), which cannot list a session's windows or their working directories, so the script discovers them by walking the process tree with `psutil`. If you are willing to switch to [tmux](https://github.com/tmux/tmux), none of this is needed: [tmuxp](https://github.com/tmux-python/tmuxp) already loads sessions from YAML (`tmuxp load` ≈ `launch`, `tmuxp freeze` ≈ `snapshot`), and [libtmux](https://github.com/tmux-python/libtmux) exposes each window's cwd and running command natively, so the `status` view would be a few dozen lines instead of this CLI and skill.

## Claude Code

by setting some simple environment variables you can run Claude Code on [OpenRouter](https://openrouter.ai/apps/claude-code) or Ollama using [.env.example](.env.example) (first `cp .env.example .env` and set your models and API key):
```sh
# if you have pipx installed dotenv-cli
dotenv claude

# or just using uv
uv run --no-project --env-file .env -- claude
```

* for running the Ollam, please comment out the Openrouter in `.env.example` and uncomment the Ollama section. Those environment variables basically replace what [`ollama launch claude`](https://docs.ollama.com/integrations/claude-code) does. First make sure that you've ran `ollama serve` and if using cloud model please also run `ollama login`.
