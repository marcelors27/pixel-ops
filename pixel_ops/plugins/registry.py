from __future__ import annotations

from pixel_ops.plugins.pokemon.plugin import PokemonPlugin


def available_plugins():
    plugins = [PokemonPlugin()]
    return {plugin.name: plugin for plugin in plugins}


def get_plugin(name: str):
    plugins = available_plugins()
    try:
        return plugins[name]
    except KeyError as error:
        supported = ", ".join(sorted(plugins))
        raise ValueError(f"Unknown plugin '{name}'. Supported plugins: {supported}") from error
