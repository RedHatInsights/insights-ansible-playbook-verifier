# Contributing to Insights Ansible playbook verifier

## Security

Since we are dealing with PGP, you should ensure you aren't including private key material in your commits. We recommend you to install `gitleaks` package and add it to pre-commit or pre-push script. For example:

```bash
#!/bin/bash
set -euo pipefail

gitleaks detect --verbose
make check
make test
make integration
```

Our `gitleaks` configuration explicitly ignores `python/tests-unit/test_crypto.py` that includes dummy private key we use to run tests of the `crypto` module; be extra careful when changing this file.

## Conventional Commits

When making a contribution, follow the [Conventional Commits](https://www.conventionalcommits.org) guidelines.

tl;dr, the commit description consists of:

- Title
  - Prefix with type and optional scope: `feat:`, `fix:`, `chore(ci):`, `test:`.
  - One-liner that continues the sentence "When applied, this patch will...": `Fix CI on RHEL 9`, `Update method signatures`, `Ensure temporary GPG home is deleted`.
  - Is under 72 characters long.
- One empty line
- External issue tracker references
  - Each tracker is on its own line.
  - Jira: `* Card ID: CCT-581`.
  - GitHub: `* Resolves: #47`.
- One empty line
- Description
    - Describes the cause, additional context or testing requirements.
    - Is wrapped to 72 characters (unless it contains content that doesn't handle line breaks).


## Certificate of Origin

By contributing to this project you agree to the [Developer Certificate of Origin (DCO)](https://developercertificate.org/). This document was created by the Linux Kernel community and is a simple statement that you, as a contributor, have the legal right to make the contribution.

The full text of the DCO follows:

```
Developer Certificate of Origin
Version 1.1

Copyright (C) 2004, 2006 The Linux Foundation and its contributors.

Everyone is permitted to copy and distribute verbatim copies of this
license document, but changing it is not allowed.


Developer's Certificate of Origin 1.1

By making a contribution to this project, I certify that:

(a) The contribution was created in whole or in part by me and I
    have the right to submit it under the open source license
    indicated in the file; or

(b) The contribution is based upon previous work that, to the best
    of my knowledge, is covered under an appropriate open source
    license and I have the right under that license to submit that
    work with modifications, whether created in whole or in part
    by me, under the same open source license (unless I am
    permitted to submit under a different license), as indicated
    in the file; or

(c) The contribution was provided directly to me by some other
    person who certified (a), (b) or (c) and I have not modified
    it.

(d) I understand and agree that this project and the contribution
    are public and that a record of the contribution (including all
    personal information I submit with it, including my sign-off) is
    maintained indefinitely and may be redistributed consistent with
    this project or the open source license(s) involved.
```
