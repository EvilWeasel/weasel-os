"""Merge declarative Serena paths into user-owned configuration, preserving other settings."""
import json
import os
from pathlib import Path
import sys
import tempfile

import tomlkit
import yaml


def replace_if_changed(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text() == text:
        return
    fd, temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(text)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


home, executable, settings_path = sys.argv[1:]
home = Path(home)
serena_path = home / ".serena/serena_config.yml"
serena = yaml.safe_load(serena_path.read_text()) if serena_path.exists() else {}
serena = serena or {}
serena.setdefault("projects", [])
serena.setdefault("web_dashboard_open_on_launch", False)
serena.setdefault("web_dashboard_interface", "browser")
serena.setdefault("gui_log_window", False)
for language, settings in json.loads(Path(settings_path).read_text()).items():
    serena.setdefault("ls_specific_settings", {}).setdefault(language, {}).update(settings)
replace_if_changed(serena_path, yaml.safe_dump(serena, sort_keys=False))

codex_path = home / ".codex/config.toml"
codex = tomlkit.parse(codex_path.read_text()) if codex_path.exists() else tomlkit.document()
entry = codex.setdefault("mcp_servers", {}).setdefault("serena", {})
entry["command"] = executable
entry["args"] = ["start-mcp-server", "--context", "codex", "--project-from-cwd"]
entry["startup_timeout_sec"] = 60
entry["tool_timeout_sec"] = 120
replace_if_changed(codex_path, tomlkit.dumps(codex))
