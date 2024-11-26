import pathlib
import unittest.mock

import insights_ansible_playbook_lib as lib
import pytest


DATA = pathlib.Path(__file__).parents[2].absolute() / "data"
GPG_KEY = (DATA / "public.gpg").read_bytes()
REVOKED = (DATA / "revoked_playbooks.yml").read_text()
PLAYBOOKS = pathlib.Path(__file__).parents[2].absolute() / "data" / "playbooks"


class TestParsePlaybook:
    """The reference verifier used YAML 1.2.

    PyYAML seems to be using YAML 1.1 by default, so we have to ensure we parse it correctly.
    """

    def test_all(self):
        """Test that all plays loaded if present."""
        raw = "\n".join(
            [
                "---",
                "- name: first dictionary",
                "  key: value",
                "- name: second dictionary",
                "  key: value",
            ]
        )
        expected = [
            {"name": "first dictionary", "key": "value"},
            {"name": "second dictionary", "key": "value"},
        ]

        actual = lib.parse_playbook(raw)

        assert actual == expected

    def test_integers(self):
        raw = "- [1, 2, 3]"
        expected = [[1, 2, 3]]

        actual = lib.parse_playbook(raw)

        assert actual == expected

    def test_floats(self):
        raw = "- [1.0, 2.0, 3.0]"
        expected = [[1.0, 2.0, 3.0]]

        actual = lib.parse_playbook(raw)

        assert actual == expected

    def test_true(self):
        raw = "- bool: [true, True, TRUE]\n  string: [y, yes, Yes, YES, on, On, ON]"
        expected = [
            {
                "bool": [True, True, True],
                "string": ["y", "yes", "Yes", "YES", "on", "On", "ON"],
            }
        ]

        actual = lib.parse_playbook(raw)

        assert actual == expected


class TestCleanPlaybook:
    def test_ok(self):
        raw = {
            "name": "good playbook",
            "hosts": "localhost",
            "vars": {
                "insights_signature_exclude": "/hosts,/vars/insights_signature/",
                "insights_signature": b"data",
            },
            "tasks": [],
        }
        expected = {
            "name": "good playbook",
            "vars": {"insights_signature_exclude": "/hosts,/vars/insights_signature/"},
            "tasks": [],
        }

        actual: dict = lib.clean_play(raw)
        assert actual == expected

    def test_requires_vars(self):
        raw = {"name": "bad playbook", "tasks": [{"name": "a task"}]}

        with pytest.raises(
            lib.PreconditionError,
            match="does not have the key 'vars",
        ):
            lib.clean_play(raw)

    def test_requires_signature_exclude(self):
        raw = {"name": "bad playbook", "vars": {}, "tasks": [{"name": "a task"}]}

        with pytest.raises(
            lib.PreconditionError,
            match="does not have the key 'vars/insights_signature_exclude'",
        ):
            lib.clean_play(raw)

    def test_too_shallow_exclude(self):
        raw = {"vars": {"insights_signature_exclude": "/"}}

        with pytest.raises(
            lib.PreconditionError,
            match="too deep or shallow",
        ):
            lib.clean_play(raw)

    def test_too_deep_exclude(self):
        raw = {"vars": {"insights_signature_exclude": "/vars/nested/key"}}

        with pytest.raises(
            lib.PreconditionError,
            match="too deep or shallow",
        ):
            lib.clean_play(raw)

    def test_forbidden_exclude(self):
        raw = {"vars": {"insights_signature_exclude": "/name"}}

        with pytest.raises(
            lib.PreconditionError,
            match="cannot be excluded",
        ):
            lib.clean_play(raw)

    def test_missing_simple(self):
        raw = {"vars": {"insights_signature_exclude": "/hosts"}}

        with pytest.raises(
            lib.PreconditionError,
            match="Variable field '/hosts' is not present in the play.",
        ):
            lib.clean_play(raw)

    def test_missing_nested(self):
        raw = {"vars": {"insights_signature_exclude": "/vars/insights_signature"}}

        with pytest.raises(
            lib.PreconditionError,
            match="Variable field '/vars/insights_signature' is not present in the play.",
        ):
            lib.clean_play(raw)


class TestCreatePlayDigest:
    @pytest.mark.parametrize("file", ("insights_remove", "document-from-hell"))
    def test_ok(self, file: str):
        raw: bytes = (PLAYBOOKS / f"{file}.serialized.bin").read_bytes()
        expected: bytes = (PLAYBOOKS / f"{file}.digest.bin").read_bytes()

        actual: bytes = lib.create_play_digest(raw)

        assert actual == expected


class TestVerifyPlaybook:
    @pytest.mark.parametrize("file", ("insights_remove", "document-from-hell"))
    def test_ok(self, file: str):
        raw: str = (PLAYBOOKS / f"{file}.yml").read_text()
        expected: bytes = (PLAYBOOKS / f"{file}.digest.bin").read_bytes()

        parsed_play: dict = lib.parse_playbook(raw)[0]
        digest: bytes = lib.verify_play(parsed_play, gpg_key=GPG_KEY)

        assert digest == expected

    def test_no_signature(self):
        parsed_play = {
            "name": "bad playbook",
            "hosts": "localhost",
            "vars": {
                "insights_signature_exclude": "/hosts,/vars/insights_signature/",
            },
            "tasks": [],
        }

        with pytest.raises(
            lib.PreconditionError,
            match="does not contain a signature",
        ):
            lib.verify_play(parsed_play, gpg_key=GPG_KEY)


class TestGetRevocationDigests:
    def test_ok(self):
        expected = {
            bytes(
                bytearray.fromhex(
                    "8ddc7c9fb264aa24d7b3536ecf00272ca143c2ddb14a499cdefab045f3403e9b"
                )
            ),
            bytes(
                bytearray.fromhex(
                    "40a6e9af448208759bc4ef59b6c678227aae9b3f6291c74a4a8767eefc0a401f"
                )
            ),
        }

        actual: set[bytes] = lib.get_revocation_digests(
            playbook=REVOKED, gpg_key=GPG_KEY
        )

        assert actual == expected

    @unittest.mock.patch(
        "insights_ansible_playbook_lib.crypto.verify_gpg_signed_file",
        return_value=unittest.mock.MagicMock(ok=False),
    )
    def test_bad_signature(self, _):
        """Test that validation failure raises an exception."""
        with pytest.raises(
            lib.GPGValidationError,
            match="Play digest does not match its signature",
        ):
            lib.get_revocation_digests(playbook=REVOKED, gpg_key=GPG_KEY)
