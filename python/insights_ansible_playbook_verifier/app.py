import argparse
import contextlib
import logging
import pathlib
import pkgutil
import sys
import traceback

import importlib.metadata

import insights_ansible_playbook_lib as lib

logger = logging.getLogger(__name__)


def read_revocation_playbook_from_package() -> str:
    """Read revocation playbook content saved in the package."""
    data: str = pkgutil.get_data(
        "insights_ansible_playbook_verifier",
        "data/revoked_playbooks.yml",
    ).decode("utf-8")  # type: ignore
    return data


def get_gpg_key_from_package() -> bytes:
    """Read the public GPG key to verify the plays with."""
    data: bytes = pkgutil.get_data(
        "insights_ansible_playbook_verifier",
        "data/public.gpg",
    )  # type: ignore
    return data


def get_version_from_package() -> str:
    """Read the package metadata to obtain version."""
    try:
        version = importlib.metadata.version("insights-ansible-playbook-verifier")
    except ImportError:
        version = "unknown"
    return version


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
        "--key",
        type=pathlib.Path,
        help="Path to custom GPG key to verify against",
    )
    playbook = parser.add_mutually_exclusive_group(required=True)
    playbook.add_argument(
        "--playbook",
        type=pathlib.Path,
        help="Path to playbook to load",
    )
    playbook.add_argument(
        "--stdin",
        action="store_true",
        help="Load playbook from stdin (the default)",
    )
    args = parser.parse_args()

    # Load public GPG key
    gpg_key: bytes = args.key.read_bytes() if args.key else get_gpg_key_from_package()

    # Load digests of revoked plays
    digests: set[bytes] = lib.get_revocation_digests(
        playbook=read_revocation_playbook_from_package(),
        gpg_key=gpg_key,
    )
    logger.debug("Revocation digests obtained, can proceed to verification.")

    # Load playbook with plays to verify
    raw_playbook: str
    if args.stdin:
        with contextlib.suppress(KeyboardInterrupt):
            raw_playbook = sys.stdin.read()
    else:
        raw_playbook = pathlib.Path(args.playbook).read_text()
    if len(raw_playbook) == 0:
        logger.error("Received empty playbook.")
        raise RuntimeError("Received empty playbook.")

    # Load plays
    plays: list[dict] = lib.parse_playbook(raw_playbook)
    if not plays:
        raise lib.PreconditionError("Playbook contains no plays.")
    logger.debug(f"Playbook contains {len(plays)} play(s).")

    # Verify plays
    for i, play in enumerate(plays, 1):
        play_name: str = play.get("name", "???")
        digest: bytes = lib.verify_play(play, gpg_key=gpg_key)
        if digest in digests:
            raise RuntimeError(
                f"Digest of play '{play_name}' is on revocation list: '{bytearray(digest).hex()}'."
            )
        else:
            logger.debug(f"Play {i}/{len(plays)} ('{play_name}'): OK.")

    logger.info("All plays are OK.")
    print(raw_playbook)


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
