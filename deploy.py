#!/usr/bin/env python3

from pathlib import Path
import os
import re
import shutil

config = {
    'game_path': '/mnt/d/World_of_Tanks/World_of_Tanks_EU/',
    'client_mod_path': 'scripts/client/gui/mods'
}

class ModDeploy:
    def __init__(self, game_path: Path) -> None:
        if not game_path.exists():
            raise ValueError(f"ModDeploy: Game path not exists [{game_path}]")
        self._game_path = game_path
        self._mods_location = Path(os.getcwd())

    def _compile_mod(self, py_file: str) -> str:
        pyc = py_file + 'c'
        py = py_file
        print(f"Compilation started: {py} -> {pyc}")
        os.system(f"python -m py_compile {py} {pyc}")
        return pyc

    def _deploy_mod(self, pyc_file: str) -> None:
        res_mods = self._game_path / "res_mods"
        version_re = re.compile(r"[\d.]+")
        version_re2 = re.compile(r"^(\d+)\.(\d+)\.(\d+)\.(\d+)$")

        versions = []
        # TODO
        # If format will change from X.X.X.X this part of code has to be adjusted to proper sorting mechanism
        for item in res_mods.glob("*"):
            if version_re.match(item.name):
                version_dir = item.name
                match = version_re2.match(version_dir)
                if match:
                    n1 = int(match.group(1))
                    n2 = int(match.group(2))
                    n3 = int(match.group(3))
                    n4 = int(match.group(4))

                    if n1 > 99 or n2 > 99 or n3 > 99 or n4 > 99:
                        raise ValueError(f"ModDeploy: version directory exceeded 99: {version_dir}")  

                    # 99 max for each number
                    value = n1 * pow(10, 6) + n2 * pow(10, 4) + n3 * pow(10, 2) + n4
                    versions.append((item.name, value, item))
                else:
                    print(f"Warning! Not supported directory name: {version_dir}")
        versions = sorted(versions, key=lambda x: x[1], reverse=True)
        version_dir = versions[0][2]
        deploy_path = version_dir / config['client_mod_path']

        shutil.copy2(pyc_file, deploy_path)
        print(f"Pyc file deployed: {pyc_file} -> {deploy_path}")

    def scan_and_deploy(self) -> None:
        for dir in self._mods_location.glob("*"):
            if dir.is_dir() and not str(dir.name).startswith('.'):
                for f in dir.glob("*.py"):
                    if f.name.startswith("mod_"):
                        pyc = self._compile_mod(str(f.resolve()))
                        self._deploy_mod(pyc)


if len(config['game_path']) == 0:
    print("Action required! You need to set path to the game in 'config' dictionary in deploy.py file.")
else:
    o = ModDeploy(Path(config['game_path']))
    o.scan_and_deploy()
