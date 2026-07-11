# YAML configuration

YAML is optional for a minimal run and recommended for repeatable or advanced work.

```bash
uv run mudidi config validate examples/configs/production/directory-inference.yaml
uv run mudidi run --config examples/configs/production/directory-inference.yaml --dry-run
```

Configuration rules:

- `version` is currently `1`.
- `kind` must match the command.
- Paths are relative to the YAML file.
- Unknown fields fail validation.
- Explicit CLI options override YAML; YAML overrides built-in defaults.
- Lists supplied on the CLI replace YAML lists.
- API keys remain in `.env`.

See the generated [configuration schema](../reference/config.md).
