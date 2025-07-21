from typing import List, Optional, Union
import pytest
import sys
from pytest_mock import MockerFixture
from _pytest.monkeypatch import MonkeyPatch

import editor


@pytest.fixture
def mock_find_executable(mocker: MockerFixture):
    """Mock the appropriate find_executable function based on Python version."""
    if sys.version_info >= (3, 12):
        # Python 3.12+ uses shutil.which
        return mocker.patch("shutil.which")
    else:
        # Python < 3.12 uses distutils.spawn.find_executable
        return mocker.patch("distutils.spawn.find_executable")


def test_get_default_editors() -> None:
    """Test that get_default_editors returns expected editors."""
    assert editor.get_default_editors() == ["editor", "vim", "emacs", "nano"]


@pytest.mark.parametrize(
    "editor_name,expected_args",
    [
        # Vim family editors
        ("vim", ["-f", "-o"]),
        ("gvim", ["-f", "-o"]),
        ("vim.basic", ["-f", "-o"]),
        ("vim.tiny", ["-f", "-o"]),
        # Other editors
        ("emacs", ["-nw"]),
        ("gedit", ["-w", "--new-window"]),
        ("nano", ["-R"]),
        ("code", ["-w", "-n"]),
        # Unknown editor
        ("unknown-editor", []),
    ],
)
def test_get_editor_args(editor_name: str, expected_args: List[str]) -> None:
    """Test editor-specific argument configuration."""
    assert editor.get_editor_args(editor_name) == expected_args


@pytest.mark.parametrize(
    "visual_value,editor_value,expected_editor",
    [
        ("test-visual", None, "test-visual"),  # VISUAL only
        (None, "test-editor", "test-editor"),  # EDITOR only
        ("test-visual", "test-editor", "test-visual"),  # VISUAL preferred over EDITOR
    ],
)
def test_get_editor_environment_variables(
    monkeypatch: MonkeyPatch,
    visual_value: Optional[str],
    editor_value: Optional[str],
    expected_editor: str,
) -> None:
    """Test get_editor uses environment variables with correct precedence."""
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)

    if visual_value is not None:
        monkeypatch.setenv("VISUAL", visual_value)
    if editor_value is not None:
        monkeypatch.setenv("EDITOR", editor_value)

    assert editor.get_editor() == expected_editor


def test_edit_with_editor_command_and_args(
    mocker: MockerFixture, monkeypatch: MonkeyPatch
) -> None:
    """Test edit() function handles EDITOR with command arguments."""
    # Set EDITOR to include command arguments
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.setenv("EDITOR", "emacsclient -c")

    mock_popen = mocker.patch("subprocess.Popen")
    mock_process = mocker.MagicMock()
    mock_popen.return_value = mock_process

    mock_open = mocker.mock_open(read_data=b"test content")
    mocker.patch("builtins.open", mock_open)
    mocker.patch("sys.stdin.isatty", return_value=True)
    mocker.patch("sys.stdout.isatty", return_value=True)

    result = editor.edit(filename="/tmp/test.txt")

    assert result == b"test content"
    mock_popen.assert_called_once_with(
        ["emacsclient", "-c", "-nw", "/tmp/test.txt"], close_fds=True, stdout=None
    )
    mock_process.communicate.assert_called_once()


def test_get_editor_fallback_success(
    mocker: MockerFixture, monkeypatch: MonkeyPatch, mock_find_executable
) -> None:
    """Test get_editor fallback to default editors."""
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)

    mock_get_default_editors = mocker.patch("editor.get_default_editors")
    mock_get_default_editors.return_value = ["vim", "nano"]
    mock_find_executable.side_effect = [None, "/usr/bin/nano"]

    assert editor.get_editor() == "/usr/bin/nano"

    mock_find_executable.assert_any_call("vim")
    mock_find_executable.assert_any_call("nano")


def test_get_editor_fallback_failure(
    mocker: MockerFixture,
    monkeypatch: MonkeyPatch,
    mock_find_executable,
) -> None:
    """Test get_editor raises EditorError when no editor found."""
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)

    mock_get_default_editors = mocker.patch("editor.get_default_editors")
    mock_get_default_editors.return_value = ["vim", "nano"]
    mock_find_executable.return_value = None

    with pytest.raises(editor.EditorError) as exc_info:
        editor.get_editor()

    assert "Unable to find a viable editor" in str(exc_info.value)


@pytest.mark.parametrize(
    "platform,expected_tty",
    [
        ("linux", "/dev/tty"),
        ("darwin", "/dev/tty"),  # macOS
        ("freebsd", "/dev/tty"),  # FreeBSD
        ("win32", "CON:"),
    ],
)
def test_get_tty_filename(
    mocker: MockerFixture, platform: str, expected_tty: str
) -> None:
    """Test get_tty_filename returns correct TTY device for different platforms."""
    mocker.patch("sys.platform", platform)
    assert editor.get_tty_filename() == expected_tty


def test_edit_with_filename(mocker: MockerFixture) -> None:
    """Test edit() function with existing filename."""
    mock_get_editor = mocker.patch("editor.get_editor")
    mock_get_editor_args = mocker.patch("editor.get_editor_args")
    mock_popen = mocker.patch("subprocess.Popen")

    mock_get_editor.return_value = "/usr/bin/vim"
    mock_get_editor_args.return_value = ["-f", "-o"]

    mock_process = mocker.MagicMock()
    mock_popen.return_value = mock_process

    mock_open = mocker.mock_open(read_data=b"test content")
    mocker.patch("builtins.open", mock_open)
    mocker.patch("sys.stdin.isatty", return_value=True)
    mocker.patch("sys.stdout.isatty", return_value=True)

    result = editor.edit(filename="/tmp/test.txt")

    assert result == b"test content"
    mock_popen.assert_called_once_with(
        ["/usr/bin/vim", "-f", "-o", "/tmp/test.txt"], close_fds=True, stdout=None
    )
    mock_process.communicate.assert_called_once()


@pytest.mark.parametrize(
    "input_content,expected_written_content",
    [
        pytest.param(b"initial content", b"initial content", id="bytes content"),
        pytest.param(
            "initial content",
            b"initial content",
            id="string content (auto-encoded to bytes)",
        ),
    ],
)
def test_edit_with_contents(
    mocker: MockerFixture,
    input_content: Union[str, bytes],
    expected_written_content: bytes,
) -> None:
    """Test edit() function with contents creating temporary file."""
    mock_get_editor = mocker.patch("editor.get_editor")
    mock_get_editor_args = mocker.patch("editor.get_editor_args")
    mock_popen = mocker.patch("subprocess.Popen")
    mock_tempfile = mocker.patch("tempfile.NamedTemporaryFile")

    mock_get_editor.return_value = "/usr/bin/vim"
    mock_get_editor_args.return_value = ["-f", "-o"]

    mock_temp = mocker.MagicMock()
    mock_temp.name = "/tmp/tmp123"
    mock_tempfile.return_value = mock_temp

    mock_process = mocker.MagicMock()
    mock_popen.return_value = mock_process

    # Mock file operations
    write_mock = mocker.mock_open()
    read_mock = mocker.mock_open(read_data=b"edited content")

    mock_open_func = mocker.patch("builtins.open")
    mock_open_func.side_effect = [
        write_mock.return_value,
        read_mock.return_value,
    ]

    mocker.patch("sys.stdin.isatty", return_value=True)
    mocker.patch("sys.stdout.isatty", return_value=True)

    result = editor.edit(contents=input_content)

    assert result == b"edited content"
    write_mock.return_value.write.assert_called_once_with(expected_written_content)
    mock_popen.assert_called_once_with(
        ["/usr/bin/vim", "-f", "-o", "/tmp/tmp123"], close_fds=True, stdout=None
    )


def test_edit_with_tty(mocker: MockerFixture) -> None:
    """Test edit() function with TTY mode."""
    mock_get_editor = mocker.patch("editor.get_editor")
    mock_get_editor_args = mocker.patch("editor.get_editor_args")
    mock_popen = mocker.patch("subprocess.Popen")
    mock_get_tty_filename = mocker.patch("editor.get_tty_filename")

    mock_get_editor.return_value = "/usr/bin/vim"
    mock_get_editor_args.return_value = ["-f", "-o"]
    mock_get_tty_filename.return_value = "/dev/tty"

    mock_process = mocker.MagicMock()
    mock_popen.return_value = mock_process

    mock_tty_file = mocker.MagicMock()
    read_mock = mocker.mock_open(read_data=b"test content")

    mock_open_func = mocker.patch("builtins.open")
    mock_open_func.side_effect = [mock_tty_file, read_mock.return_value]

    mocker.patch("sys.stdin.isatty", return_value=True)
    mocker.patch("sys.stdout.isatty", return_value=False)

    result = editor.edit(filename="/tmp/test.txt")

    assert result == b"test content"
    mock_popen.assert_called_once_with(
        ["/usr/bin/vim", "-f", "-o", "/tmp/test.txt"],
        close_fds=True,
        stdout=mock_tty_file,
    )


def test_edit_with_suffix(mocker: MockerFixture) -> None:
    """Test edit() function with custom suffix."""
    mock_get_editor = mocker.patch("editor.get_editor")
    mock_get_editor_args = mocker.patch("editor.get_editor_args")
    mock_popen = mocker.patch("subprocess.Popen")

    mock_get_editor.return_value = "/usr/bin/vim"
    mock_get_editor_args.return_value = ["-f", "-o"]

    mock_process = mocker.MagicMock()
    mock_popen.return_value = mock_process

    mock_tempfile = mocker.patch("tempfile.NamedTemporaryFile")
    mock_temp = mocker.MagicMock()
    mock_temp.name = "/tmp/tmp123.md"
    mock_tempfile.return_value = mock_temp

    mock_open = mocker.mock_open(read_data=b"test content")
    mocker.patch("builtins.open", mock_open)
    mocker.patch("sys.stdin.isatty", return_value=True)
    mocker.patch("sys.stdout.isatty", return_value=True)

    result = editor.edit(suffix=".md")

    mock_tempfile.assert_called_once_with(suffix=".md")
    assert result == b"test content"


def test_edit_explicit_use_tty_true(mocker: MockerFixture) -> None:
    """Test edit() function with explicit use_tty=True."""
    mock_get_editor = mocker.patch("editor.get_editor")
    mock_get_editor_args = mocker.patch("editor.get_editor_args")
    mock_popen = mocker.patch("subprocess.Popen")

    mock_get_editor.return_value = "/usr/bin/vim"
    mock_get_editor_args.return_value = ["-f", "-o"]

    mock_process = mocker.MagicMock()
    mock_popen.return_value = mock_process

    mock_tty_file = mocker.MagicMock()
    read_mock = mocker.mock_open(read_data=b"test content")

    mock_open_func = mocker.patch("builtins.open")
    mock_open_func.side_effect = [mock_tty_file, read_mock.return_value]
    mocker.patch("editor.get_tty_filename", return_value="/dev/tty")

    result = editor.edit(filename="/tmp/test.txt", use_tty=True)

    assert result == b"test content"
    mock_popen.assert_called_once_with(
        ["/usr/bin/vim", "-f", "-o", "/tmp/test.txt"],
        close_fds=True,
        stdout=mock_tty_file,
    )


def test_edit_explicit_use_tty_false(mocker: MockerFixture) -> None:
    """Test edit() function with explicit use_tty=False."""
    mock_get_editor = mocker.patch("editor.get_editor")
    mock_get_editor_args = mocker.patch("editor.get_editor_args")
    mock_popen = mocker.patch("subprocess.Popen")

    mock_get_editor.return_value = "/usr/bin/vim"
    mock_get_editor_args.return_value = ["-f", "-o"]

    mock_process = mocker.MagicMock()
    mock_popen.return_value = mock_process

    mock_open = mocker.mock_open(read_data=b"test content")
    mocker.patch("builtins.open", mock_open)

    result = editor.edit(filename="/tmp/test.txt", use_tty=False)

    assert result == b"test content"
    mock_popen.assert_called_once_with(
        ["/usr/bin/vim", "-f", "-o", "/tmp/test.txt"], close_fds=True, stdout=None
    )
