#!/bin/bash
set -eu
set -x

# get to project root
cd ../../../

# Check for GitHub pull request ID and install build if needed.
# This is for the downstream PR jobs.
[ -z "${ghprbPullId+x}" ] || ./systemtest/copr-setup.sh

# This is for ad-hoc and compose testing.
if ! dnf info insights-ansible-playbook-verifier &>/dev/null; then
  dnf -y install insights-ansible-playbook-verifier
fi

dnf --setopt install_weak_deps=False install -y \
  python3-pytest

PATH=/usr/libexec:$PATH pytest \
  --junit-xml=./junit.xml \
  -v python/tests-integration/
