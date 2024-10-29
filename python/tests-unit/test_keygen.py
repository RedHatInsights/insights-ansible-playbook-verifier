import os.path
import shutil
import tempfile

from unittest import mock

from insights_ansible_playbook_lib import _keygen


@mock.patch(
    "insights_ansible_playbook_lib._keygen.TEMPORARY_GPG_HOME_PARENT_DIRECTORY",
    "/tmp/",
)
def test_run_valid_gpg_command():
    """A valid GPG command can be executed."""
    home = tempfile.mkdtemp()

    # Run the test
    result = _keygen._run_gpg_command(
        ["/usr/bin/gpg", "--batch", "--homedir", home, "--version"],
    )

    # Verify results
    assert True is result.ok
    assert "gpg (GnuPG)" in result.stdout
    assert f"Home: {home}" in result.stdout
    assert "" == result.stderr
    assert 0 == result.return_code

    shutil.rmtree(home)


@mock.patch(
    "insights_ansible_playbook_lib._keygen.TEMPORARY_GPG_HOME_PARENT_DIRECTORY",
    "/tmp/",
)
def test_run_invalid_gpg_command():
    """An invalid GPG command can be detected."""
    home = tempfile.mkdtemp()

    # Run the test
    result = _keygen._run_gpg_command(
        ["/usr/bin/gpg", "--batch", "--homedir", home, "--invalid-command"],
    )

    # Verify results
    assert not result.ok
    assert "" == result.stdout
    assert "gpg: invalid option" in result.stderr
    assert 2 == result.return_code

    shutil.rmtree(home)


@mock.patch(
    "insights_ansible_playbook_lib._keygen.TEMPORARY_GPG_HOME_PARENT_DIRECTORY",
    "/tmp/",
)
def test_generate_gpg_key_pair():
    """A GPG key pair with a fingerprint can be generated."""
    home = tempfile.mkdtemp()

    # Run the test
    gpg_tmp_dir = _keygen._generate_keys()
    _keygen._export_key_pair(gpg_tmp_dir, home)
    fingerprint = _keygen._get_fingerprint(gpg_tmp_dir, home)

    # Verify results
    assert os.path.exists(gpg_tmp_dir)
    assert os.path.exists(gpg_tmp_dir + "/keygen")
    assert os.path.exists(home + "/key.public.gpg")
    assert os.path.exists(home + "/key.private.gpg")
    assert os.path.exists(home + "/key.fingerprint.txt")
    assert fingerprint == open(home + "/key.fingerprint.txt").read().strip()

    shutil.rmtree(gpg_tmp_dir)
    shutil.rmtree(home)
