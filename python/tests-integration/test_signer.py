import os
import pathlib
import shutil
import subprocess
import tempfile

import pytest

DATA_DIRECTORY = pathlib.Path(__file__).parents[2].absolute() / "data"

_GPG_INSTRUCTIONS = """
Key-Type: EDDSA
  Key-Curve: ed25519
Subkey-Type: ECDH
  Subkey-Curve: cv25519
Name-Real: Integration test key
Expire-Date: 0
%no-protection
%commit
"""


@pytest.fixture
def ephemeral_gpg_keys(tmp_path: pathlib.Path) -> None:
    """Generate public and private GPG keys.

    :yields: Tuple of paths to private and public GPG key.
    """
    # Create fresh GPG keys
    instructions_file = tmp_path / "instructions"
    instructions_file.write_text(_GPG_INSTRUCTIONS)
    genkey = subprocess.run(
        [
            "gpg",
            "--batch",
            "--generate-key",
            "--pinentry-mode",
            "loopback",
            instructions_file,
        ],
        input=os.devnull,
        capture_output=True,
        check=False,
        text=True,
        env={"GNUPGHOME": str(tmp_path)},
    )
    print(genkey.stderr)
    genkey.check_returncode()

    # Save the public key
    pubkey = subprocess.run(
        ["gpg", "--export", "--armor"],
        capture_output=True,
        check=False,
        text=True,
        env={"GNUPGHOME": str(tmp_path)},
    )
    print(pubkey.stderr)
    pubkey.check_returncode()
    gpg_public = tmp_path / "public.gpg"
    gpg_public.write_text(pubkey.stdout)

    # Save the private key
    privkey = subprocess.run(
        [
            "gpg",
            "--export-secret-keys",
            "--pinentry-mode",
            "loopback",
            "--yes",
            "--armor",
        ],
        capture_output=True,
        check=False,
        text=True,
        env={"GNUPGHOME": str(tmp_path)},
    )
    print(privkey.stderr)
    privkey.check_returncode()
    gpg_private = tmp_path / "private.gpg"
    gpg_private.write_text(privkey.stdout)

    yield gpg_private, gpg_public


@pytest.mark.skipif(
    shutil.which("insights-ansible-playbook-signer") is None,
    reason="verifier is not installed",
)
@pytest.mark.parametrize(
    "playbook",
    [
        # official production playbooks
        "playbooks/insights_remove.yml",
        # custom playbooks signed by official Red Hat key
        "playbooks/document-from-hell.yml",
        # unsigned playbooks
        "playbooks-unsigned/sample.yml",
    ],
)
def test_end_to_end(
    ephemeral_gpg_keys: tuple[pathlib.Path, pathlib.Path], playbook: str
):
    """Test that we can sign and verify a playbook."""
    revocation_signing_result = subprocess.run(
        [
            "insights-ansible-playbook-signer",
            "--playbook",
            DATA_DIRECTORY / "revoked_playbooks.yml",
            "--revocation-list",
            "--key",
            ephemeral_gpg_keys[0],
            "--debug",
        ],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "LC_ALL": "C.UTF-8"},
    )
    print(revocation_signing_result.stderr.strip())
    revocation_signing_result.check_returncode()
    assert revocation_signing_result.returncode == 0
    revocation_list_file = tempfile.NamedTemporaryFile(
        prefix="revocation-list-", suffix=".yml"
    )
    with open(revocation_list_file.name, "w") as f:
        f.write(revocation_signing_result.stdout)

    playbook_signing_result = subprocess.run(
        [
            "insights-ansible-playbook-signer",
            "--playbook",
            DATA_DIRECTORY / playbook,
            "--key",
            ephemeral_gpg_keys[0],
            "--debug",
        ],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "LC_ALL": "C.UTF-8"},
    )
    print(playbook_signing_result.stderr.strip())
    playbook_signing_result.check_returncode()
    assert playbook_signing_result.returncode == 0

    reading_result = subprocess.run(
        [
            "insights-ansible-playbook-verifier",
            "--stdin",
            "--key",
            ephemeral_gpg_keys[1],
            "--revocation-list",
            revocation_list_file.name,
            "--debug",
        ],
        input=playbook_signing_result.stdout,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "LC_ALL": "C.UTF-8"},
    )
    print(reading_result.stderr.strip())
    reading_result.check_returncode()
    assert playbook_signing_result.stdout.strip() == reading_result.stdout.strip()
    assert playbook_signing_result.returncode == 0
