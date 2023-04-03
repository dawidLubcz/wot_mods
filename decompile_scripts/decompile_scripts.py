"""
Module for decompiling .pyc files in the World of Tanks game directory.
"""

import os
import sys
import zipfile
import uncompyle6
from multiprocessing import cpu_count
import concurrent.futures
from pathlib import Path


class WotDecompiler:
    SCRIPT_DIR = "./src"
    SCRIPT_PACKAGE_PATH = "./res/packages/scripts.pkg"

    def __init__(self, game_path=''):
        """
        Initialize WotDecompiler instance.

        :param game_path: str, optional, path to the World of Tanks game directory
        """
        self._game_path = WotDecompiler.validate(game_path)

    @staticmethod
    def validate(game_path):
        """
        Validate the provided game path.

        :param game_path: str, path to the World of Tanks game directory
        :return: str, validated game path
        """
        if os.environ.get('WOT_GAME_PATH', None):
            if Path(os.environ['WOT_GAME_PATH']).exists():
                game_path = os.environ['WOT_GAME_PATH']
                return game_path
            raise AttributeError(f"WOT_GAME_PATH env variable set to not existing path: {game_path}")

        if not Path(game_path).exists():
            raise AttributeError(f"WOT_GAME_PATH env variable not set "
                                 f"and game path param set to not existing path: {game_path}")
        return game_path

    @staticmethod
    def _find_pyc_files() -> list:
        """
        Find .pyc files in the script directory.

        :return: list, paths to the .pyc files
        """
        scr_dir = Path(WotDecompiler.SCRIPT_DIR)
        if not scr_dir.exists():
            raise FileNotFoundError(f"{WotDecompiler.SCRIPT_DIR} folder does not exist")
        pyc_files = []
        for pyc_file in scr_dir.rglob("*.pyc"):
            pyc_files.append(str(pyc_file))
        return pyc_files

    @staticmethod
    def _unzip_file_scripts():
        """
        Unzip the scripts package to the script directory.
        """
        scripts_package_path = Path(WotDecompiler.SCRIPT_PACKAGE_PATH)
        if not scripts_package_path.exists():
            raise FileNotFoundError(f"{WotDecompiler.SCRIPT_PACKAGE_PATH} file does not exist")
        with zipfile.ZipFile(WotDecompiler.SCRIPT_PACKAGE_PATH, 'r') as zip_ref:
            output_folder = WotDecompiler.SCRIPT_DIR
            os.makedirs(output_folder, exist_ok=True)
            zip_ref.extractall(output_folder)

    @staticmethod
    def _decompile_file_task(file_path: str):
        """
         Task for decompiling a single .pyc file.

         :param file_path: str, path to the .pyc file
         """
        cwd = os.getcwd()
        decompiled_file_path = Path(cwd) / (os.path.splitext(file_path)[0] + ".py")
        file_path = Path(cwd) / file_path
        with open(decompiled_file_path, 'w') as f:
            uncompyle6.decompile_file(str(file_path), f)

    @staticmethod
    def _decompile_files(files: list):
        """
        Decompile the provided list of .pyc files.

        :param files: list, paths to the .pyc files
        :return: list, paths to the files that failed to decompile
        """
        done_count = 0
        failed_to_decompile = []

        with concurrent.futures.ProcessPoolExecutor(max_workers=cpu_count()) as executor:
            future_to_file = {executor.submit(WotDecompiler._decompile_file_task, file): file for file in files}
            for future in concurrent.futures.as_completed(future_to_file):
                file = future_to_file[future]
                try:
                    future.result()
                except Exception:
                    failed_to_decompile.append(file)
                done_count += 1
                sys.stdout.write(f"\r{done_count}/{len(files)} - {done_count / len(files) * 100:.2f}%")
        sys.stdout.flush()
        return failed_to_decompile

    def decompile(self):
        """
        Decompile .pyc files located in the WoT game directory.

        Returns:
            failed_to_decompile (list): A list of files that failed to decompile.
        """
        previous_location = os.getcwd()
        os.chdir(self._game_path)

        try:
            WotDecompiler._unzip_file_scripts()
            files = WotDecompiler._find_pyc_files()
            print(f"decompile: Found {len(files)} files")
            WotDecompiler._decompile_files(files=files)
        finally:
            os.chdir(previous_location)


def main():
    WotDecompiler("D:\\World_of_Tanks\\World_of_Tanks_EU").decompile()


if __name__ == '__main__':
    main()
