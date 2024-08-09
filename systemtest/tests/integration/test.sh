#!/bin/bash
set -eu
set -x

# get to project root
cd ../../../

dnf --setopt install_weak_deps=False install -y \
  python3-pytest

PATH=/usr/libexec:$PATH pytest -v python/tests-integration/
