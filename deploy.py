#!/usr/bin/env python3

__doc__ = """
Script for compiling and uploading wot modification into the proper location in the game.
To use this script you have to set 'game_path' dictionary field in the config obj.
'game_path' should point to the root folder of the game.
"""

from pathlib import Path
import os
import re
import shutil

config = {
    'game_path': '/mnt/d/World_of_Tanks/World_of_Tanks_EU/',
    'client_mod_path': 'scripts/client/gui/mods'
}

class ModDeploy:
    """Class for building and deploying wot modification"""

    def __init__(self, game_path: Path) -> None:
        if not game_path.exists():
            raise ValueError(f"ModDeploy: Game path not exists [{game_path}]")
        self._game_path = game_path
        self._mods_location = Path(os.getcwd())

    def _compile_mod(self, py_file: str) -> str:
        pyc_file = py_file + 'c'
        print(f"Compilation started: {py_file} -> {pyc_file}")
        os.system(f"python -m py_compile {py_file} {pyc_file}")
        return pyc_file

    def _deploy_mod(self, pyc_file: str) -> None:
        res_mods = self._game_path / "res_mods"
        version_re = re.compile(r"[\d.]+")
        version_re2 = re.compile(r"^(\d+)\.(\d+)\.(\d+)\.(\d+)$")

        versions = []
        # TODO
        # If format will change from X.X.X.X this part of code
        # has to be adjusted to proper sorting mechanism
        for item in res_mods.glob("*"):
            if version_re.match(item.name):
                version_dir = item.name
                match = version_re2.match(version_dir)
                if match:
                    number1 = int(match.group(1))
                    number2 = int(match.group(2))
                    number3 = int(match.group(3))
                    number4 = int(match.group(4))

                    if number1 > 99 or number2 > 99 or number3 > 99 or number4 > 99:
                        raise ValueError(f"ModDeploy: version directory exceeded 99: {version_dir}")

                    # 99 max for each number
                    value = number1 * pow(10, 6) + number2 * pow(10, 4) +\
                            number3 * pow(10, 2) + number4
                    versions.append((item.name, value, item))
                else:
                    print(f"Warning! Not supported directory name: {version_dir}")
        versions = sorted(versions, key=lambda x: x[1], reverse=True)
        version_dir = versions[0][2]
        deploy_path = version_dir / config['client_mod_path']

        if not os.path.exists(deploy_path):
            os.makedirs(deploy_path)
        shutil.copy2(pyc_file, deploy_path)
        print(f"Pyc file deployed: {pyc_file} -> {deploy_path}")

    def scan_and_deploy(self) -> None:
        """Look for mods subfolders, compile and deploy."""

        for directory in self._mods_location.glob("*"):
            if directory.is_dir() and not str(directory.name).startswith('.'):
                for file in directory.glob("*.py"):
                    if file.name.startswith("mod_"):
                        pyc = self._compile_mod(str(file.resolve()))
                        self._deploy_mod(pyc)


def main():
    """Entry function"""

    if len(config['game_path']) == 0:
        print("Action required! You need to set path to the game in' \
               config' dictionary in deploy.py file.")
    else:
        mod_deploy = ModDeploy(Path(config['game_path']))
        mod_deploy.scan_and_deploy()


if __name__ == "__main__":
    main()
