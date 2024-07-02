# Ansible playbook verifier

When some Red Hat Insights service instructs a RHEL system to take some action (disable password-based SSH access to root account, update all packages containing CVEs, convert from CentOS to RHEL), it does so by sending an Ansible playbook to the host system.

Before the host executes the playbook, it verifies the embedded GPG signature to ensure the playbook can be trusted. That is what the Ansible playbook verifier does.

Historically, the Verifier has been a Python application shipped via Insights Client through its Core. This repository replaces it.

**References:**

- [Red Hat Insights](https://consoledot.redhat.com/insights): Red Hat cloud services
- [yggdrasil](https://github.com/RedHatInsights/yggdrasil): MQTT broker that delivers playbooks from Insights to the host
- [rhc-worker-playbook](https://github.com/RedHatInsights/rhc-worker-playbook): Yggdrasil worker executing signed Ansible playbooks
- [rhc-worker-script](https://github.com/oamg/rhc-worker-script): Yggdrasil worker executing Python or Bash scripts from signed YAML files
- [insights-client](https://github.com/RedHatInsights/insights-client): The wrapper around Insights Core
- [insights-core](https://github.com/RedHatInsights/insights-core): The old Playbook verifier location (see `insights/client/apps/ansible/`)
