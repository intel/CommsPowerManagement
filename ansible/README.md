#README for comms_platform_provisioning
October 2020

## CONTENTS

- Introduction
- Requirements
- Role variables
- Example playbook
- Usage

## INTRODUCTION
An Ansible Collection with single role comms_power_provisioning,
that configures the system for low latency and power saving for
RHEL/CentOS/Debian and SUSE Linux distributions.

## REQUIREMENTS
- Ansible installed.

- Suse system registered with SUSE and base packages installed.

- Required global proxy settings setup according to the distribution.
  Inappropriate proxy settings might block the script from cloning repos
  or installing required tools packages.

## ROLE VARIABLES
All variables are stored in main.yml file under role's "default" directory.
Based on user needs the parameters has to be adjusted.

Note: Example low latency boot parameters are given in main.yml of "default"
directory. These parameters have to be adjusted based on user system need.


## EXAMPLE PLAYBOOK
Playbook to deploy low latency:
```
- name: Deploy commspower-platform-provisioning
  hosts: webservers
  roles:
    - role: ../roles/commspower-platform-provisioning
      state: lowlatency
```

Playbook to deploy powersaving:
```
- name: Deploy commspower-platform-provisioning
  hosts: webservers
  roles:
    - role: ../roles/commspower-platform-provisioning
      state: powersaving
```

## REQUIREMENTS
. Ansible* >= 2.9.4

## Usage
. Edit the main.yml file under the role's "default" directory to suit your needs.
. Edit ansible/playbooks/inventory/hosts to add targets under webservers.
. Run low latency provisioning as below
  ansible-playbook  -i ansible/playbooks/inventory/hosts ansible/playbooks/deploy-lowlatency.yml
. Run powersaving provisioning as below
  ansible-playbook  -i ansible/playbooks/inventory/hosts ansible/playbooks/deploy-powersaving.yml
