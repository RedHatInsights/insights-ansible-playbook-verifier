VERSION?=0.0.0
BUILDROOT?=/etc/mock/default.cfg

.PHONY: build
build: build-py
	sed -i "s|Version:.*|Version:  $(VERSION)|" insights-ansible-playbook-verifier.spec
	@echo "Built $(VERSION)"

.PHONY: build-py
build-py:
	@echo "Building Python package" && \
	cp data/public.gpg python/insights_ansible_playbook_verifier/data/public.gpg
	cp data/revoked_playbooks.yml python/insights_ansible_playbook_verifier/data/revoked_playbooks.yml
	sed -i "s|version = .*|version = '$(VERSION)'|" pyproject.toml


.PHONY: test
test: test-py

.PHONY: test-py
test-py:
	PYTHONPATH=python/ pytest python/tests-unit/ -v


.PHONY: integration
integration: integration-py

.PHONY: integration-py
integration-py:
	PYTHONPATH=python/ pytest python/tests-integration/ -v


.PHONY: check
check: check-py
	gitleaks git --verbose

.PHONY: check-py
check-py:
	ruff check python/
	ruff format --diff python/
	mypy


.PHONY: tarball
tarball:
	mkdir -p "rpm/"
	rm -rf rpm/insights-ansible-playbook-verifier-$(VERSION).tar.gz
	git ls-files -z | xargs -0 tar \
		--create --gzip \
		--transform "s|^|/insights-ansible-playbook-verifier-$(VERSION)/|" \
		--file rpm/insights-ansible-playbook-verifier-$(VERSION).tar.gz

.PHONY: srpm
srpm:
	rpmbuild -bs \
		--define "_sourcedir `pwd`/rpm" \
		--define "_srcrpmdir `pwd`/rpm" \
		insights-ansible-playbook-verifier.spec

.PHONY: rpm
rpm: build tarball srpm
	mock \
		--root $(BUILDROOT) \
		--rebuild \
		--resultdir "rpm/" \
		rpm/insights-ansible-playbook-verifier-*.src.rpm


.PHONY: clean
clean: clean-rpm

.PHONY: clean-rpm
clean-rpm:
	rm -f rpm/*
