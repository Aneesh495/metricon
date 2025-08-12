from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        if version == "editable":
            return
        directory = Path(self.root) / "web" / "dist"
        if not (directory / "index.html").is_file():
            raise RuntimeError("Run npm ci and npm run build before building a distribution wheel")
        build_data.setdefault("force_include", {})[str(directory)] = "metricon/web_dist"
