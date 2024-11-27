import argparse
import base64
import contextlib
import copy
import logging
import pathlib
import subprocess
import sys
import tempfile
import traceback
from typing import Optional

import yaml

import insights_ansible_playbook_lib as lib
from insights_ansible_playbook_lib import crypto
from insights_ansible_playbook_verifier.app import get_version_from_package

logger = logging.getLogger(__name__)


def send_signing_request(play_digest: bytes, key: str) -> bytes:
    """Use remote signing server to sign the digest.

    :param play_digest: Hash of a play.
    :param key: Name of the GPG key to use on the remote signing server.
    """
    logger.info("Requesting play signature from a signing server.")

    with tempfile.TemporaryDirectory(
        prefix=lib.TEMPORARY_STASH_DIRECTORY_PREFIX,
        dir=lib.TEMPORARY_STASH_DIRECTORY,
    ) as temp_dir:
        temp_path = pathlib.Path(temp_dir)

        digest_file = temp_path / "digest"
        digest_file.write_bytes(play_digest)

        subprocess.run(
            ["rpm-sign", "--detachsign", "--key", key, "--nat", str(digest_file)],
            check=True,
            capture_output=True,
        )

        return (temp_path / "digest.asc").read_bytes()


def sign_play_digest(play_digest: bytes, key: pathlib.Path) -> bytes:
    """Get the GPG signature of the play digest.

    :param play_digest: Hash of a play.
    :param key: Path to the GPG key to use.
    """
    logger.debug("Signing play.")

    if not key.is_file():
        raise RuntimeError(f"Key '{key}' does not exist.")

    with tempfile.TemporaryDirectory(
        prefix=lib.TEMPORARY_STASH_DIRECTORY_PREFIX,
        dir=lib.TEMPORARY_STASH_DIRECTORY,
    ) as temp_dir:
        temp_path = pathlib.Path(temp_dir)

        digest_file = temp_path / "digest"
        digest_file.write_bytes(play_digest)

        result = crypto.sign_file(digest_file, key)
        if not result.ok:
            raise RuntimeError(f"Could not sign the digest: {result}")
        return (temp_path / "digest.asc").read_bytes()


def sign_revocation_list(
    raw_data: list[dict],
    *,
    local_key: Optional[pathlib.Path],
    remote_key: Optional[str],
) -> None:
    """Sign revocation list.

    :param raw_data: A map containing the revocation play references.
    :param local_key: Path to private GPG key. Must not be used together with `remote_key`.
    :param remote_key: Name of remote GPG key. Must not be used together with `local_key`.
    """
    if len(raw_data) != 1:
        raise RuntimeError("Revocation file must contain exactly one entry.")
    if "revoked_playbooks" not in raw_data[0]:
        raise RuntimeError("Revocation file must contain key 'revoked_playbooks'.")

    data: dict = copy.deepcopy(raw_data[0])
    data["vars"] = {
        "insights_signature_exclude": "/vars/insights_signature",
        "insights_signature": "",
    }

    # Ensure 'revoked_playbooks' are the last element
    data["revoked_playbooks"] = data.pop("revoked_playbooks")

    cleaned_data: dict = lib.clean_play(data)
    serialized_data: bytes = lib.serialize_play(cleaned_data).encode("utf-8")
    digest: bytes = lib.create_play_digest(serialized_data)

    logger.debug(f"Serialized revocation list as {serialized_data!r}.")
    logger.debug(f"Revocation list digest is '{bytearray(digest).hex()}'.")

    signature: bytes
    if remote_key is not None:
        signature = send_signing_request(digest, key=remote_key)
    elif local_key is not None:
        signature = sign_play_digest(digest, key=local_key)
    else:
        raise RuntimeError("Either 'remote_key' or 'local_key' must be set.")

    data["vars"]["insights_signature"] = base64.b64encode(signature)

    yaml.dump([data], sys.stdout, sort_keys=False)


def sign_playbook(
    raw_plays: list[dict],
    *,
    local_key: Optional[pathlib.Path],
    remote_key: Optional[str],
) -> None:
    """Sign one or more plays in a playbook.

    :param raw_plays: Plays as they were loaded from the file.
    :param local_key: Path to private GPG key. Must not be used together with `remote_key`.
    :param remote_key: Name of remote GPG key. Must not be used together with `local_key`.
    """
    plays: list[dict] = []
    for i, raw_play in enumerate(raw_plays, 1):
        play_name: str = raw_play.get("name", "???")
        logger.debug(f"Preparing to sign play {play_name}.")
        play: dict = copy.deepcopy(raw_play)

        if "vars" not in play.keys():
            logger.debug("Filling in missing 'vars' map.")
            play["vars"] = {}
        if "insights_signature_exclude" not in play["vars"].keys():
            logger.debug("Filling in missing 'insights_signature_exclude' pair.")
            play["vars"]["insights_signature_exclude"] = (
                "/hosts,/vars/insights_signature"
            )

        if "insights_signature" not in play["vars"].keys():
            # The 'clean_play' method requires this to be included.
            # It will be overwritten later.
            play["vars"]["insights_signature"] = ""

        # Ensure 'tasks' are the last element
        if "tasks" in play.keys():
            play["tasks"] = play.pop("tasks")
        else:
            raise RuntimeError("Play does not contain key 'tasks'.")

        cleaned_play: dict = lib.clean_play(play)
        serialized_play: bytes = lib.serialize_play(cleaned_play).encode("utf-8")
        digest: bytes = lib.create_play_digest(serialized_play)

        logger.debug(f"Serialized play '{play_name}' as {serialized_play!r}")
        logger.debug(f"Play digest is '{bytearray(digest).hex()}'.")

        signature: bytes
        if remote_key is not None:
            signature = send_signing_request(digest, key=remote_key)
        elif local_key is not None:
            signature = sign_play_digest(digest, key=local_key)
        else:
            raise RuntimeError("Either 'remote_key' or 'local_key' must be set.")

        play["vars"]["insights_signature"] = base64.b64encode(signature)
        plays.append(play)
        logger.debug(f"Play {i}/{len(raw_plays)} ('{play_name}'): OK.")

    logger.info("All plays were signed.")
    yaml.dump(plays, sys.stdout, sort_keys=False)


def run() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--version",
        action="version",
        version=get_version_from_package(),
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Display logs",
    )
    parser.add_argument(
        "--revocation-list",
        action="store_true",
        help="Sign revocation list instead of a playbook",
    )
    keys = parser.add_mutually_exclusive_group(required=True)
    keys.add_argument(
        "--key",
        type=pathlib.Path,
        help="Path to private GPG key",
    )
    keys.add_argument(
        "--remote-key",
        type=str,
        help="Name of a key for a remote signing server",
    )
    playbook = parser.add_mutually_exclusive_group(required=True)
    playbook.add_argument(
        "--playbook",
        type=pathlib.Path,
        help="Path to playbook",
    )
    playbook.add_argument(
        "--stdin",
        action="store_true",
        help="Load playbook from stdin (the default)",
    )
    args = parser.parse_args()

    # Load playbook to sign
    raw_playbook: str = ""
    if args.stdin:
        with contextlib.suppress(KeyboardInterrupt):
            raw_playbook = sys.stdin.read()
    else:
        raw_playbook = args.playbook.read_text()
    if len(raw_playbook) == 0:
        logger.error("Received empty playbook.")
        raise RuntimeError("Received empty playbook.")

    # Load plays
    raw_plays: list[dict] = lib.parse_playbook(raw_playbook)
    if not raw_plays:
        raise lib.PreconditionError("Playbook contains no plays.")

    if args.revocation_list:
        logger.info("Signing revocation list.")
        return sign_revocation_list(
            raw_plays, local_key=args.key, remote_key=args.remote_key
        )

    logger.debug(f"Playbook contains {len(raw_plays)} plays.")
    return sign_playbook(raw_plays, local_key=args.key, remote_key=args.remote_key)


def main() -> None:
    debug: bool = "--debug" in sys.argv
    lib._configure_logging(debug=debug)

    try:
        run()
    except Exception as exc:
        logger.critical("Unhandled exception occurred, aborting.")
        if debug:
            traceback.print_exc()
        else:
            print(exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
