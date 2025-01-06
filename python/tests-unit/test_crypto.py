import os.path
import pathlib
import pytest
import shutil
import subprocess
import tempfile

from unittest import mock

from insights_ansible_playbook_lib import crypto
from insights_ansible_playbook_lib import _keygen


GPG_OWNER = "insights-ansible-playbook-verifier test"


def _initialize_gpg_environment(home):
    """Save GPG keys and sign a file with them.

    The home directory is populated with the following files:
    - key.public.gpg
    - key.private.gpg
    - key.fingerprint.txt
    - file.txt
    - file.txt.asc
    """
    # Generate the keys and save them
    gpg_tmp_dir = _keygen._generate_keys()
    _keygen._export_key_pair(gpg_tmp_dir, home)

    # Import the public key
    # It is strictly not necessary to import both public and private keys,
    #  the private key should be enough.
    #  However, the Python 2.6 CI image requires that.
    process = subprocess.Popen(
        ["/usr/bin/gpg", "--homedir", home, "--import", f"{home}/key.public.gpg"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={"LC_ALL": "C.UTF-8"},
    )
    process.communicate()
    assert process.returncode == 0

    # Import the private key
    process = subprocess.Popen(
        ["/usr/bin/gpg", "--homedir", home, "--import", f"{home}/key.private.gpg"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={"LC_ALL": "C.UTF-8"},
    )
    process.communicate()
    assert process.returncode == 0

    # Get the fingerprint of the key
    gpg_fingerprint = _keygen._get_fingerprint(gpg_tmp_dir, home)
    assert os.path.exists(home + "/key.fingerprint.txt")

    # Create a file and sign it
    file = home + "/file.txt"
    with open(file, "w") as f:
        f.write("a signed message")
    process = subprocess.Popen(
        ["/usr/bin/gpg", "--homedir", home, "--detach-sign", "--armor", file],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={"LC_ALL": "C.UTF-8"},
    )
    process.communicate()
    assert process.returncode == 0

    # Ensure the signature has been created
    assert os.path.exists(home + "/file.txt.asc")

    return gpg_fingerprint


@mock.patch(
    "insights_ansible_playbook_lib.crypto.TEMPORARY_GPG_HOME_PARENT_DIRECTORY",
    "/tmp/",
)
def test_valid_signature():
    """A detached file signature can be verified."""
    home = tempfile.mkdtemp()
    gpg_fingerprint = _initialize_gpg_environment(home)

    # Run the test
    result = crypto.verify_gpg_signed_file(
        file=pathlib.Path(home) / "file.txt",
        signature=pathlib.Path(home) / "file.txt.asc",
        key=pathlib.Path(home) / "key.public.gpg",
    )
    shutil.rmtree(home, ignore_errors=True)

    # Verify results
    assert True is result.ok
    assert "" == result.stdout
    assert f'gpg: Good signature from "{GPG_OWNER}"' in result.stderr
    assert f"Primary key fingerprint: {gpg_fingerprint}" in result.stderr
    assert 0 == result.return_code

    assert not os.path.isfile(result._command._home)


@mock.patch(
    "insights_ansible_playbook_lib.crypto.TEMPORARY_GPG_HOME_PARENT_DIRECTORY",
    "/tmp/",
)
def test_invalid_signature():
    """A bad detached file signature can be detected."""
    home = tempfile.mkdtemp()
    gpg_fingerprint = _initialize_gpg_environment(home)

    # Change the contents of the file, making the signature incorrect
    with open(home + "/file.txt", "w") as f:
        f.write("an unsigned message")

    # Run the test
    result = crypto.verify_gpg_signed_file(
        file=pathlib.Path(home) / "file.txt",
        signature=pathlib.Path(home) / "file.txt.asc",
        key=pathlib.Path(home) / "key.public.gpg",
    )
    shutil.rmtree(home, ignore_errors=True)

    # Verify results
    assert not result.ok
    assert "" == result.stdout
    assert f'gpg: BAD signature from "{GPG_OWNER}"' in result.stderr
    assert f"Primary key fingerprint: {gpg_fingerprint}" not in result.stderr
    assert 1 == result.return_code

    assert not os.path.isfile(result._command._home)


@mock.patch(
    "insights_ansible_playbook_lib.crypto.TEMPORARY_GPG_HOME_PARENT_DIRECTORY",
    "/tmp/",
)
@mock.patch("subprocess.Popen")
@mock.patch.object(crypto.GPGCommand, "_cleanup", return_value=None)
def test_invalid_gpg_setup(
    mock_cleanup: mock.MagicMock,
    mock_popen: mock.MagicMock,
):
    """An invalid GPG setup can be detected."""
    gpg_command = crypto.GPGCommand(command=[], key=pathlib.Path("/dummy/key"))

    # Mock the process
    mock_process = mock.Mock()
    mock_process.communicate.return_value = (b"", b"GPG setup failed")
    mock_process.returncode = 1
    mock_popen.return_value = mock_process

    # Run the test
    result: crypto.GPGCommandResult = gpg_command.evaluate()

    # Verify results
    assert not result.ok
    assert "" == result.stdout
    assert "GPG setup failed" in result.stderr
    assert 1 == result.return_code


@mock.patch(
    "insights_ansible_playbook_lib.crypto.TEMPORARY_GPG_HOME_PARENT_DIRECTORY",
    "/tmp/",
)
def test_missing_public_key():
    """A missing public key can be detected."""
    home = tempfile.mkdtemp()
    _initialize_gpg_environment(home)

    # Remove the public key
    os.remove(home + "/key.public.gpg")

    # Run the test
    result: crypto.GPGCommandResult = crypto.verify_gpg_signed_file(
        file=pathlib.Path(home) / "file.txt",
        signature=pathlib.Path(home) / "file.txt.asc",
        key=pathlib.Path(home) / "key.public.gpg",
    )
    shutil.rmtree(home, ignore_errors=True)

    # Verify results
    assert not result.ok
    assert "" == result.stdout
    assert (
        f"gpg: can't open '{home}/key.public.gpg': No such file or directory"
        in result.stderr
    )
    assert 2 == result.return_code


@mock.patch(
    "insights_ansible_playbook_lib.crypto.TEMPORARY_GPG_HOME_PARENT_DIRECTORY",
    "/tmp/",
)
def test_invalid_public_key():
    """An invalid public key can be detected."""
    home = tempfile.mkdtemp()
    _initialize_gpg_environment(home)

    # Change the contents of the public key
    with open(home + "/key.public.gpg", "w") as f:
        f.write("invalid key")

    # Run the test
    result: crypto.GPGCommandResult = crypto.verify_gpg_signed_file(
        file=pathlib.Path(home) / "file.txt",
        signature=pathlib.Path(home) / "file.txt.asc",
        key=pathlib.Path(home) / "key.public.gpg",
    )
    shutil.rmtree(home, ignore_errors=True)

    # Verify results
    assert not result.ok
    assert "" == result.stdout
    assert "gpg: no valid OpenPGP data found" in result.stderr
    assert 2 == result.return_code


@mock.patch(
    "insights_ansible_playbook_lib.crypto.TEMPORARY_GPG_HOME_PARENT_DIRECTORY",
    "/tmp/",
)
def test_missing_signed_file():
    """A missing signed file can be detected."""
    home = tempfile.mktemp()

    # Run the test
    with pytest.raises(FileNotFoundError) as excinfo:
        crypto.verify_gpg_signed_file(
            file=pathlib.Path(home) / "file.txt",
            signature=pathlib.Path(home) / "file.txt.asc",
            key=pathlib.Path(home) / "key.public.gpg",
        )

    # Verify results
    assert "FileNotFoundError" in str(excinfo)
    assert not os.path.isfile(pathlib.Path(home) / "file.txt")
    assert not os.path.isdir(pathlib.Path(home))


@mock.patch(
    "insights_ansible_playbook_lib.crypto.TEMPORARY_GPG_HOME_PARENT_DIRECTORY",
    "/tmp/",
)
def test_missing_signature_file():
    """A missing signature file can be detected."""
    home = tempfile.mkdtemp()
    _initialize_gpg_environment(home)

    # Remove the signature file
    os.remove(home + "/file.txt.asc")

    # Run the test
    with pytest.raises(FileNotFoundError) as excinfo:
        crypto.verify_gpg_signed_file(
            file=pathlib.Path(home) / "file.txt",
            signature=pathlib.Path(home) / "file.txt.asc",
            key=pathlib.Path(home) / "key.public.gpg",
        )

    # Verify results
    assert "FileNotFoundError" in str(excinfo)
    assert os.path.isfile(pathlib.Path(home) / "file.txt")
    assert not os.path.isfile(pathlib.Path(home) / "file.txt.asc")

    shutil.rmtree(home, ignore_errors=True)
