Name:     insights-ansible-playbook-verifier
Version:  0.1.0
Release:  0%{dist}
Summary:  Ansible playbook verifier for Red Hat Insights
License:  MIT

URL:      https://github.com/RedHatInsights/%{name}
# Source0:  %{url}/archive/refs/tags/v%{version}.tar.gz
Source0:  %{name}-%{version}.tar.gz

BuildArch: noarch

BuildRequires: python3-devel
Requires: gpg
%generate_buildrequires
%pyproject_buildrequires

%description
insights-ansible-playbook-verifier package cryptographically verifies Ansible
playbooks generated by Red Hat Insights.

%prep
%autosetup -p1

%build
%pyproject_wheel

%install
%pyproject_install insights_ansible_playbook_lib insights_ansible_playbook_verifier
mkdir -p %{buildroot}/%{_libexecdir}
mv %{buildroot}%{_bindir}/%{name} %{buildroot}%{_libexecdir}
mkdir -p %{buildroot}/%{_localstatedir}/lib/%{name}/
%pyproject_save_files insights_ansible_playbook_lib insights_ansible_playbook_verifier

%check
%pyproject_check_import insights_ansible_playbook_lib insights_ansible_playbook_verifier

%files -n %{name} -f %{pyproject_files}
%{_libexecdir}/%{name}
%attr(700,root,root) %dir %{_localstatedir}/lib/%{name}/
%license LICENSE

%changelog
%autochangelog
