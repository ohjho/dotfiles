# dotfiles
configs, scripts, tools

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

## Claude Code

by setting some simple environment variables you can run Claude Code on [OpenRouter](https://openrouter.ai/apps/claude-code) or Ollama using [.env.example](.env.example) (first `cp .env.example .env` and set your models and API key):
```sh
# if you have pipx installed dotenv-cli
dotenv claude

# or just using uv
uv run --no-project --env-file .env -- claude
```

* for running the Ollam, please comment out the Openrouter in `.env.example` and uncomment the Ollama section. Those environment variables basically replace what [`ollama launch claude`](https://docs.ollama.com/integrations/claude-code) does. First make sure that you've ran `ollama serve` and if using cloud model please also run `ollama login`.
