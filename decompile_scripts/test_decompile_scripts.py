import sys

import pytest
import os
import shutil
from pathlib import Path
from unittest import mock
from unittest.mock import patch
from decompile_scripts import WotDecompiler


@pytest.fixture
def wot_decompiler():
    root = os.getcwd()
    tmpdir = Path(root) / '.tmp'
    game_path = tmpdir / "game_dir"
    game_path.mkdir(parents=True, exist_ok=True)
    script_dir = game_path / "src"
    script_dir.mkdir(parents=True, exist_ok=True)
    package_file = game_path / "res/packages"
    package_file.mkdir(parents=True, exist_ok=True)
    (package_file / 'scripts.pkg').touch(exist_ok=True)
    os.chdir(game_path)
    yield WotDecompiler(str(game_path))
    os.chdir(root)
    shutil.rmtree(tmpdir)


def test_validate_valid_path(wot_decompiler):
    game_path = wot_decompiler.validate(os.getcwd())
    assert game_path == os.getcwd()


def test_validate_invalid_path(wot_decompiler):
    with pytest.raises(AttributeError):
        wot_decompiler.validate("non_existing_path")


def test_find_pyc_files_no_files(wot_decompiler):
    files = wot_decompiler._find_pyc_files()
    assert len(files) == 0


def test_find_pyc_files_with_files(wot_decompiler):
    Path("src/test1.pyc").touch(exist_ok=True)
    Path("src/test2.pyc").touch(exist_ok=True)
    files = wot_decompiler._find_pyc_files()
    assert len(files) == 2


@pytest.mark.skip(reason="Rewrite this test")
@mock.patch("concurrent.futures.ProcessPoolExecutor")
def test_decompile_files_executor(mock_executor, wot_decompiler):
    mock_future = mock.Mock()
    mock_future.result.return_value = None
    mock_executor.return_value.__enter__.return_value.submit.return_value = mock_future
    files = ["file1", "file2"]
    result = wot_decompiler._decompile_files(files)
    assert len(result) == 0
    mock_executor.assert_called_once()
    mock_executor.return_value.__enter__.return_value.submit.assert_any_call(
        wot_decompiler._decompile_file_task, "file1")
    mock_executor.return_value.__enter__.return_value.submit.assert_any_call(
        wot_decompiler._decompile_file_task, "file2")


@pytest.mark.skip(reason="Find a way to mock static method")
def test_decompile_files_failed_to_decompile(wot_decompiler):
    files = ["file1", "file2"]

    def mock_task(file_path: str):
        if len(files) == 1:
            raise Exception()
        files.remove(file_path)

    with patch.object(wot_decompiler, "_decompile_file_task", autospec=True) as mocked_decompiler:
        mocked_decompiler.__class__._decompile_file_task = mock_task
        mocked_decompiler.__class__._decompile_files(files)


