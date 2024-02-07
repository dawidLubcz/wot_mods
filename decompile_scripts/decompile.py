"""
Program for decompiling source files in the game World Of Tanks.
Requires Python 3.9 or newer and the installed *.pyc files decompiler, uncompyle6.

To run the program, set the environment variable WOT_PATH to point to the game directory,
or provide the wot_path parameter to the script.
After running the program, a 'src' directory will be created in the main game directory,
containing both compiled and decompiled game files.
"""

import os
import sys
import logging


def get_logger():
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)  # Ustaw poziom logowania na DEBUG
    formatter = logging.Formatter('%(asctime)s %(levelname)-8s %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    return logger


g_logger = get_logger()
if sys.version_info < (3, 9):
    g_logger.error("The program requires Python 3.9 or newer.")
    sys.exit(1)


import argparse
import zipfile
import subprocess
from multiprocessing import cpu_count
import concurrent.futures
from pathlib import Path


class PythonDecompiler:
    def decompile_file(self, input_file, output_file) -> None:
        raise NotImplementedError()
    
    def validate(self) -> (bool, str):
        raise NotImplementedError()


class Uncompyle6(PythonDecompiler):
    def decompile_file(self, input_file, output_file):
        p = subprocess.Popen(["uncompyle6", "-o", output_file, input_file],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output, error = p.communicate()
        if p.returncode != 0:
            g_logger.warning(f"Failed to decompile {input_file}")
    
    def validate(self):
        try:
            subprocess.run(["uncompyle6", "--help"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        except subprocess.CalledProcessError as e:
            return False, str(e)
        return True, ""


class WotDecompiler:
    SCRIPT_PACKAGE_PATH = "./res/packages/scripts.pkg"

    def __init__(self, game_path='', output_path='./src', decompiler=Uncompyle6()):
        """
        Initialize WotDecompiler instance.

        :param game_path: str, optional, path to the World of Tanks game directory
        """
        self._game_path = WotDecompiler.validate(game_path, decompiler)
        self._out_dir = output_path
        self._decompiler = decompiler

    @staticmethod
    def validate(game_path, decompiler):
        """
        Validate the provided game path.

        :param game_path: str, path to the World of Tanks game directory
        :return: str, validated game path
        """
        if os.environ.get('WOT_GAME_PATH', None):
            if not Path(os.environ['WOT_GAME_PATH']).exists():
                raise AttributeError(f"WOT_GAME_PATH env variable set to not existing path: {game_path}")
            game_path = os.environ['WOT_GAME_PATH']

        if len(game_path) == 0 or not Path(game_path).exists():
            raise AttributeError(f"WOT_GAME_PATH env variable not set "
                                 f"and game path param set to not existing path: {game_path}")

        is_os, msg = decompiler.validate()
        if not is_os:
            raise ValueError(f"Failed to validate decompiler: {msg}")

        return game_path

    def _find_pyc_files(self) -> list:
        """
        Find .pyc files in the script directory.

        :return: list, paths to the .pyc files
        """
        scr_dir = Path(self._out_dir)
        if not scr_dir.exists():
            raise FileNotFoundError(f"{self._out_dir} folder does not exist")
        pyc_files = []
        for pyc_file in scr_dir.rglob("*.pyc"):
            pyc_files.append(str(pyc_file))
        return pyc_files

    def _unzip_file_scripts(self):
        """
        Unzip the scripts package to the script directory.
        """
        scripts_package_path = Path(WotDecompiler.SCRIPT_PACKAGE_PATH)
        if not scripts_package_path.exists():
            raise FileNotFoundError(f"{WotDecompiler.SCRIPT_PACKAGE_PATH} file does not exist")
        with zipfile.ZipFile(WotDecompiler.SCRIPT_PACKAGE_PATH, 'r') as zip_ref:
            output_folder = self._out_dir
            os.makedirs(output_folder, exist_ok=True)
            zip_ref.extractall(output_folder)

    def _decompile_file_task(self, file_path: str):
        """
         Task for decompiling a single .pyc file.

         :param file_path: str, path to the .pyc file
         """
        cwd = os.getcwd()
        decompiled_file_path = Path(cwd) / (os.path.splitext(file_path)[0] + ".py")
        file_path = Path(cwd) / file_path
        self._decompiler.decompile_file(file_path, decompiled_file_path)


    def _decompile_files(self, files: list):
        """
        Decompile the provided list of .pyc files.

        :param files: list, paths to the .pyc files
        :return: list, paths to the files that failed to decompile
        """
        done_count = 0
        failed_to_decompile = []

        with concurrent.futures.ProcessPoolExecutor(max_workers=cpu_count()) as executor:
            future_to_file = {executor.submit(self._decompile_file_task, file): file for file in files}
            for future in concurrent.futures.as_completed(future_to_file):
                file = future_to_file[future]
                try:
                    future.result()
                except Exception:
                    sys.stdout.write('\n')
                    sys.stdout.flush()
                    failed_to_decompile.append(file)
                done_count += 1
                sys.stdout.write(f"\r{done_count}/{len(files)} - {done_count / len(files) * 100:.2f}%")
        sys.stdout.write('\n')
        sys.stdout.flush()
        return failed_to_decompile

    def _save_fails_to_file(self, file_failed_to_decompile: list, file_name: str = 'failed.log') -> None:
        path = Path(os.getcwd()) / '.tmp'
        path.mkdir(parents=True, exist_ok=True)
        with open(str(path / file_name), 'w') as f:
            for failed_item in file_failed_to_decompile:
                f.write(f"{Path(self._game_path) / failed_item}\n")
            g_logger.error(f"Failed to save file: {str(path / file_name)}")

    def decompile(self):
        """
        Decompile .pyc files located in the WoT game directory.

        Returns:
            failed_to_decompile (list): A list of files that failed to decompile.
        """
        previous_location = os.getcwd()
        os.chdir(self._game_path)

        failed_to_decompile = []
        try:
            g_logger.info("decompile: Unzip scripts package")
            self._unzip_file_scripts()
            g_logger.info("decompile: Find pyc files")
            files = self._find_pyc_files()
            g_logger.info(f"decompile: Found {len(files)} files, proc found={cpu_count()}")
            failed_to_decompile = self._decompile_files(files=files)
        finally:
            os.chdir(previous_location)
            self._save_fails_to_file(file_failed_to_decompile=failed_to_decompile)


def main():
    def create_arg_parser():
        # Utwórz obiekt parsera argumentów
        parser = argparse.ArgumentParser(description="WOT pyc decompiler")

        # Dodaj opcjonalne argumenty do parsera z domyślnymi wartościami
        parser.add_argument("-p", "--wot_path", action='store', default="", help="Path to the WOT game directory")
        parser.add_argument("-o", "--output_path", action='store', default="./src", help="Path to the output directory where decompiled file will be stored, default=./src")
        return parser.parse_args()

    parser = create_arg_parser()
    WotDecompiler(parser.wot_path, parser.output_path).decompile()


if __name__ == '__main__':
    main()
