import dataclasses
import errno
import logging
import os
import os.path
import pathlib
import shutil
import tempfile
import subprocess
import typing

logger = logging.getLogger(__name__)


# We try to use the special /var/lib/ directory in which gnupg has SELinux
# permissions to write to.
if os.geteuid() == 0 and os.path.isdir("/var/lib/insights-ansible-playbook-verifier/"):
    TEMPORARY_GPG_HOME_PARENT_DIRECTORY = "/var/lib/insights-ansible-playbook-verifier/"
    TEMPORARY_GPG_HOME_PARENT_DIRECTORY_PREFIX = "gpg-"
else:
    TEMPORARY_GPG_HOME_PARENT_DIRECTORY = "/tmp/"
    TEMPORARY_GPG_HOME_PARENT_DIRECTORY_PREFIX = (
        "insights-ansible-playbook-verifier-gpg-"
    )


@dataclasses.dataclass(frozen=True)
class GPGCommandResult:
    """Output of a GPGCommand.

    :param ok: Result of an operation.
    :param return_code: Return code of an operation.
    :param stdout: Standard output of the command.
    :param stderr: Standard error of the command.
    :param _command: An optional reference to the GPGCommand object that created the result.
    """

    ok: bool
    return_code: int
    stdout: str
    stderr: str
    _command: typing.Optional["GPGCommand"]

    def __str__(self) -> str:
        return "<{cls} ok={ok} return_code={code} stdout={out} stderr={err}>".format(
            cls=self.__class__.__name__,
            ok=self.ok,
            code=self.return_code,
            out=self.stdout,
            err=self.stderr,
        )


class GPGCommand:
    """GPG command run in a temporary environment.

    :param command: The command to be executed.
    :param key: Path to the GPG public key to check against.
    :param _home: Path to the temporary GPG home directory.
    :param _raw_command: The last invoked command.
    """

    def __init__(self, command: list[str], key: pathlib.Path):
        self.command: list[str] = command
        self.key: pathlib.Path = key
        self._home: typing.Optional[str] = None
        self._raw_command: typing.Optional[list[str]] = None

    def __str__(self) -> str:
        return "<{cls} _home={home} _raw_command={raw}>".format(
            cls=self.__class__.__name__, home=self._home, raw=self._raw_command
        )

    def _setup(self) -> GPGCommandResult:
        """Prepare GPG environment."""
        self._home = tempfile.mkdtemp(
            dir=TEMPORARY_GPG_HOME_PARENT_DIRECTORY,
            prefix=TEMPORARY_GPG_HOME_PARENT_DIRECTORY_PREFIX,
        )

        logger.debug(f"Will use temporary environment in '{self._home}'.")
        result: GPGCommandResult = self._run(["--import", f"{self.key.absolute()!s}"])
        if not result.ok:
            logger.error(f"Failed to import key '{self.key!s}': {result}")
        return result

    def _supports_cleanup_socket(self) -> bool:
        """Queries for the version of GPG binary.

        :returns: `True` if the gnupg is known for supporting `--kill all`.
        """
        version_process = subprocess.Popen(
            ["/usr/bin/gpg", "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            env={"GNUPGHOME": self._home, "LC_ALL": "C.UTF-8"},  # type: ignore
        )
        stdout, stderr = version_process.communicate()
        if version_process.returncode != 0:
            stderr = "\n".join(
                "stderr: {line}".format(line=line)
                for line in stderr.split("\n")
                if len(line)
            )
            logger.warning(f"Could not query for GPG version:\n{stderr}")
            return False

        for line in stdout.split("\n"):
            if line.startswith("gpg (GnuPG) "):
                version = line.split(" ")[-1]  # type: str
                break
        else:
            stdout = "\n".join(
                "stdout: {line}".format(line=line)
                for line in stdout.split("\n")
                if len(line)
            )
            logger.debug(
                f"Could not query for GPG version: output not recognized:\n{stdout}."
            )
            return False

        version_info = tuple(int(v) for v in version.split("."))
        if len(version_info) < 3:
            logger.debug(
                "GPG version is not recognized: '{version}'.".format(version=version)
            )
            return False

        # `gpgconf --kill` was added in GnuPG 2.1.0-beta2 and `--kill all` exists since 2.1.18.
        # - 2.1.0b1: commit 7c03c8cc65e68f1d77a5a5a497025191fe5df5e9 in GPG's repository.
        # - 2.1.18: https://lists.gnupg.org/pipermail/gnupg-announce/2017q1/000401.html
        #
        # RHEL versions come with the following gpg versions:
        # - 6.10: 2.0.14
        # - 7.9:  2.0.22
        # - 8.9:  2.2.20
        # - 9.3:  2.3.3
        # which means this code should return `True` for RHEL 8 and above.
        return version_info >= (2, 1, 18)

    def _cleanup_socket(self) -> None:
        """Stop GPG socket in its home directory."""
        # GPG writes a temporary socket file for the gpg-agent into the home
        # directory. This is only supported since gnupg 2.1.18 (RHEL 8).
        shutdown_process = subprocess.Popen(
            ["/usr/bin/gpgconf", "--kill", "all"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            env={"GNUPGHOME": self._home, "LC_ALL": "C.UTF-8"},  # type: ignore
        )
        _, stderr = shutdown_process.communicate()
        if shutdown_process.returncode == 0:
            logger.debug("Killed GPG agent.")
        else:
            stderr = "\n".join(
                "stderr: {line}".format(line=line)
                for line in stderr.split("\n")
                if len(line)
            )
            logger.warning(
                "Could not kill the GPG agent, "
                f"got return code {shutdown_process.returncode}: \n{stderr}."
            )

    def _cleanup(self) -> None:
        """Clean up GPG environment."""
        if self._supports_cleanup_socket():
            self._cleanup_socket()

        # Older systems do not support `gpgconf --kill`.
        # The socket may remove its socket file after `rmtree()` has determined
        # it should be deleted, but before the actual deletion occurs.
        # This would cause a FileNotFoundError/OSError.
        for _ in range(5):
            try:
                shutil.rmtree(self._home)  # type: ignore
                logger.debug("Deleted temporary directory.")
                break
            except OSError as exc:
                if exc.errno == errno.ENOENT:
                    # The file has already been removed by the `gpg-agent`.
                    continue
                raise
        else:
            logger.debug(f"Could not clean up temporary GPG directory '{self._home}'.")

    def _run(self, command: list[str]) -> "GPGCommandResult":
        """Run the actual command.

        :returns: The result of the shell command.
        """
        self._raw_command = ["/usr/bin/gpg", "--homedir", self._home] + command  # type: ignore
        process = subprocess.Popen(
            self._raw_command,  # type: ignore
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={"LC_ALL": "C.UTF-8"},
        )
        stdout, stderr = process.communicate()

        result = GPGCommandResult(
            ok=process.returncode == 0,
            return_code=process.returncode,
            stdout=stdout.decode("utf-8"),
            stderr=stderr.decode("utf-8"),
            _command=self,
        )

        if result.ok:
            logger.debug(f"GPG command {command}: ok.")
        else:
            logger.debug(f"GPG command {command} returned non-zero code: {result}.")

        return result

    def evaluate(self) -> "GPGCommandResult":
        """Run the command.

        :returns: The result of the shell command.
        """
        try:
            setup_result = self._setup()
            if not setup_result.ok:
                logger.debug("GPG setup failed.")
                return setup_result

            return self._run(self.command)
        finally:
            self._cleanup()


def verify_gpg_signed_file(
    file: pathlib.Path, signature: pathlib.Path, key: pathlib.Path
) -> GPGCommandResult:
    """
    Verify a file that was signed using GPG.

    :param file: A path to the signed file.
    :param signature: A path to the detached signature.
    :param key: Path to the public GPG key on the filesystem to check against.

    :returns: Evaluated GPG command.
    """
    if not file.is_file():
        logger.debug(f"Cannot verify signature of '{file}', file does not exist")
        raise FileNotFoundError(f"File '{file}' not found")

    if not signature.is_file():
        logger.debug(
            f"Cannot verify signature of '{file!s}', signature '{signature!s}' does not exist."
        )
        raise FileNotFoundError(
            f"Signature '{signature!s}' of file '{file!s}' not found."
        )

    gpg = GPGCommand(command=["--verify", str(signature), str(file)], key=key)

    logger.debug(f"Starting GPG verification process for '{file}'.")
    result: GPGCommandResult = gpg.evaluate()

    if result.ok:
        logger.debug(f"Signature verification of '{file}' passed.")
    else:
        logger.error(f"Signature verification of '{file}' failed.")

    return result


def sign_file(file: pathlib.Path, key: pathlib.Path) -> GPGCommandResult:
    """
    Sign a file using GPG.

    :param file: File to be signed.
    :param key: Path to the private GPG key on the filesystem.

    :return: Evaluated GPG command.
    """
    if not file.is_file():
        logger.debug(f"Cannot sign file '{file}', file does not exist.")
        raise FileNotFoundError(f"File '{file}' not found")

    if not key.is_file():
        logger.debug(f"Cannot sign file '{file}', key does not exist.")
        raise FileNotFoundError(f"Key '{key}' not found")

    gpg = GPGCommand(command=["--detach-sign", "--armor", str(file)], key=key)

    logger.debug(f"Starting GPG signing process for '{file}'.")
    result: GPGCommandResult = gpg.evaluate()

    if result.ok:
        logger.debug(f"File '{file}' was signed.")
    else:
        logger.error(f"File '{file}' could not be signed.")

    return result
