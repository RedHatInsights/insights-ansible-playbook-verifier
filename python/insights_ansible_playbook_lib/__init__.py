import base64
import copy
import dataclasses
import hashlib
import logging
import os
import pathlib
import sys
import tempfile

import yaml

from insights_ansible_playbook_lib import crypto
from insights_ansible_playbook_lib.serialization import serialize_play, Loader


logger = logging.getLogger(__name__)


VARIABLE_FIELDS: list[str] = ["hosts", "vars"]


# Try to use the special /var/lib/ directory.
if os.geteuid() == 0 and os.path.isdir("/var/lib/insights-ansible-playbook-verifier/"):
    TEMPORARY_STASH_DIRECTORY = "/var/lib/insights-ansible-playbook-verifier/"
    TEMPORARY_STASH_DIRECTORY_PREFIX = "files-"
else:
    TEMPORARY_STASH_DIRECTORY = "/tmp/"
    TEMPORARY_STASH_DIRECTORY_PREFIX = "insights-ansible-playbook-verifier-files-"


def _configure_logging(debug: bool = False) -> None:
    main_logger = logging.getLogger()

    if debug:
        main_logger.setLevel(logging.DEBUG)
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter(
                fmt=(
                    "{asctime} "
                    "\033[33m{levelname}\033[0m "
                    "\033[32m{name}:{funcName}:{lineno}\033[0m "
                    "\033[2m{message}\033[0m"
                ),
                datefmt="%Y-%m-%d %H:%M:%S",
                style="{",
            )
        )
        main_logger.addHandler(handler)
    else:
        main_logger.setLevel(logging.WARNING)
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter(
                fmt="{levelname} {name}:{lineno} {message}",
                style="{",
            )
        )
        main_logger.addHandler(handler)


class PreconditionError(RuntimeError):
    pass


@dataclasses.dataclass(frozen=True)
class GPGValidationError(RuntimeError):
    message: str
    serialized_play: bytes
    digest: bytes
    signature: bytes


def parse_playbook(playbook: str) -> list[dict]:
    """Parse a raw playbook into a list of plays."""
    logger.info("Parsing playbook.")
    content: list[dict] = yaml.load(playbook, Loader=Loader)  # type: ignore
    return content


def clean_play(play: dict) -> dict:
    """Remove variable fields from the play."""
    logger.info(f"Cleaning play '{play.get('name')}'.")

    if "insights_signature_exclude" not in play.get("vars", {}):
        raise PreconditionError(
            "The play does not have the key 'vars/insights_signature_exclude', "
            "cannot exclude dynamic fields."
        )

    fields: list[str] = play["vars"]["insights_signature_exclude"].split(",")
    result: dict = copy.deepcopy(play)

    for field in fields:
        elements: list[str] = [string for string in field.split("/") if string != ""]
        if len(elements) not in (1, 2):
            raise PreconditionError(
                f"Variable field '{field}' is too deep or shallow, only one or two levels are allowed."
            )
        if elements[0] not in VARIABLE_FIELDS:
            raise PreconditionError("Variable field '{field}' cannot be excluded.")

        if len(elements) == 1:
            if elements[0] not in result.keys():
                raise PreconditionError(
                    f"Variable field '{field}' is not present in the play."
                )
            logger.debug(f"Excluding variable field '{field}'.")
            del result[elements[0]]
        else:
            if elements[1] not in result[elements[0]].keys():
                raise PreconditionError(
                    f"Variable field '{field}' is not present in the play."
                )
            logger.debug(f"Excluding variable field '{field}'.")
            del result[elements[0]][elements[1]]

    return result


def create_play_digest(play: bytes) -> bytes:
    """Hash the play using SHA256."""
    logger.debug("Creating play digest.")

    sha = hashlib.sha256()
    sha.update(play)
    return sha.digest()


def verify_play(play: dict, gpg_key: bytes) -> bytes:
    """Verify play's signature.

    :param play: Parsed play.
    :param gpg_key: Content of public GPG key.
    :raises PreconditionError: Play doesn't contain a signature.
    :raises GPGValidationError: Digest does not match its signature.
    :returns: Play digest.
    """
    play_name: str = play.get("name", "???")
    logger.info(f"Preparing to verify play '{play_name}'.")

    b64_signature: str = play.get("vars", {}).get("insights_signature", "")
    if b64_signature == "":
        raise PreconditionError(f"The play '{play_name}' does not contain a signature.")

    cleaned_play: dict = clean_play(play)
    serialized_play: bytes = serialize_play(cleaned_play).encode("utf-8")
    digest: bytes = create_play_digest(serialized_play)
    signature: bytes = base64.b64decode(b64_signature)

    with tempfile.TemporaryDirectory(
        dir=TEMPORARY_STASH_DIRECTORY,
        prefix=TEMPORARY_STASH_DIRECTORY_PREFIX,
    ) as temp_dir:
        temp_path = pathlib.Path(temp_dir)

        digest_file = temp_path / "digest"
        digest_file.write_bytes(digest)
        signature_file = temp_path / "signature"
        signature_file.write_bytes(signature)
        key_file = temp_path / "key"
        key_file.write_bytes(gpg_key)

        logger.info(f"Cryptographically verifying play '{play_name}'.")
        result: crypto.GPGCommandResult = crypto.verify_gpg_signed_file(
            digest_file, signature_file, key_file
        )

        if not result.ok:
            logger.error(
                f"Play content failed to match its digest's signature: {serialized_play!r}."
            )
            raise GPGValidationError(
                "Play digest does not match its signature.",
                serialized_play=serialized_play,
                digest=digest,
                signature=signature,
            )

        return digest


def get_revocation_digests(playbook: str, gpg_key: bytes) -> set[bytes]:
    """Loads and verifies playbook containing revoked digests

    :param playbook: Content of the playbook containing digests of revoked plays.
    :param gpg_key: Content of GPG public key.
    :returns: Set of digests of plays that have been revoked.
    """
    logger.info("Loading revocation digests.")

    parsed_plays: list[dict] = parse_playbook(playbook)

    if len(parsed_plays) != 1:
        raise PreconditionError(
            "Playbook containing hashes of revoked plays may only include one play."
        )
    play: dict = parsed_plays[0]

    _ = verify_play(play, gpg_key=gpg_key)

    revoked: list[dict] = play.get("revoked_playbooks", [])
    digests = set(bytes(bytearray.fromhex(item["hash"])) for item in revoked)
    return digests
