from __future__ import annotations

import importlib


PLUGIN_MODULES = {
    "pokemon": "pixel_ops.plugins.pokemon.plugin",
    "spaceship": "pixel_ops.plugins.spaceship.plugin",
}


def available_plugins():
    plugins = [_load_plugin(name) for name in PLUGIN_MODULES]
    return {plugin.name: plugin for plugin in plugins}


def get_plugin(name: str):
    plugins = available_plugins()
    try:
        return plugins[name]
    except KeyError as error:
        supported = ", ".join(sorted(plugins))
        raise ValueError(f"Unknown plugin '{name}'. Supported plugins: {supported}") from error


def _load_plugin(name: str):
    module = importlib.import_module(PLUGIN_MODULES[name])
    return module.plugin()
