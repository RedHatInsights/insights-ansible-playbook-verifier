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

import yaml

import insights_ansible_playbook_lib as lib
from insights_ansible_playbook_lib import crypto
from insights_ansible_playbook_verifier.app import get_version_from_package

logger = logging.getLogger(__name__)


def send_signing_request(play_digest: bytes, key: str) -> bytes:
    """Let remove signing server sign the digest."""
    logger.info("Requesting play signature from a signing server.")
    with tempfile.TemporaryDirectory(
        prefix=lib.TEMPORARY_STASH_DIRECTORY_PREFIX,
        dir=lib.TEMPORARY_STASH_DIRECTORY,
    ) as temp_dir:
        temp_path = pathlib.Path(temp_dir)

        digest_file = temp_path / "digest"
        digest_file.write_bytes(play_digest)

        subprocess.run(
            ["rpm-sign", "--detachsign", "--key", key, "--nat", f"{digest_file!s}"],
            check=True,
            capture_output=True,
        )

        return (temp_path / "digest.asc").read_bytes()


def sign_play_digest(play_digest: bytes, key: pathlib.Path) -> bytes:
    """Get the GPG signature of the play digest."""
    logger.debug("Signing play.")

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
    logger.debug(f"Playbook contains {len(raw_plays)} plays.")

    # Sign plays
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
            logger.warning("Play does not include 'tasks', is that correct?")

        cleaned_play: dict = lib.clean_play(play)
        serialized_play: bytes = lib.serialize_play(cleaned_play).encode("utf-8")
        digest: bytes = lib.create_play_digest(serialized_play)

        logger.debug(f"Serialized play '{play_name}' as {serialized_play!r}")

        signature: bytes
        if args.remote_key:
            signature = send_signing_request(digest, key=args.remote_key)
        else:
            if not args.key.is_file():
                raise RuntimeError(f"Key {args.key}' does not exist.")
            signature = sign_play_digest(digest, key=args.key)

        play["vars"]["insights_signature"] = base64.b64encode(signature)
        plays.append(play)
        logger.debug(f"Play {i}/{len(raw_plays)} ('{play_name}'): OK.")

    logger.info("All plays were signed.")
    yaml.dump(plays, sys.stdout, sort_keys=False)


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
