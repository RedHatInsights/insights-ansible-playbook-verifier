VERSION?=0.0.0

.PHONY: build
build: build-py
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
	gitleaks detect --verbose

.PHONY: check-py
check-py:
	ruff check python/
	ruff format --diff python/
	mypy
