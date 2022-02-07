#README for comms_platform_provisioning
October 2020

## CONTENTS

- Introduction
- Requirements
- Role variables
- Example playbook
- Usage

## INTRODUCTION
An Ansible collection with single role comms_power_provisioning, that
 configures the system for `lowlatency`, `powersaving`, `lowpower` and `very-lowpower`.

## PREREQUISITES
- System with any of the below listed distros and with Ansible >= 2.9.4 installed.
  RHEL/CentOS/Debian/SUSE.

- Required global proxy settings setup according to the distribution.
 Inappropriate proxy settings might block the script from cloning repos
 or installing required tools packages.

## ROLE VARIABLES
All variables are stored in main.yml file under role's "default" directory.
Based on user needs the parameters has to be adjusted.

**Note**: Example `lowlatency` boot parameters are given in main.yml of "default"
directory. These parameters have to be adjusted based on user system need.


## EXAMPLE PLAYBOOK
Playbook to deploy `lowlatency`:
```
- name: Deploy commspower-platform-provisioning
  hosts: webservers
  roles:
    - role: ../roles/commspower-platform-provisioning
      state: lowlatency
```

Playbook to deploy `powersaving`:
```
- name: Deploy commspower-platform-provisioning
  hosts: webservers
  roles:
    - role: ../roles/commspower-platform-provisioning
      state: powersaving
```

Playbook to deploy either `lowpower` or `very-lowpower` provisioning on selected cores. The "state" will be set to either `lowpower` or `very-lowpower` during the run based on the action variable. More about this playbook can be found in below section.
```
- name: Deploy commspower-platform-provisioning
hosts: webservers
  roles:
    - role: ../roles/commspower-platform-provisioning
      state: lowpower or very-lowpower
```

## Usage
  . Edit the `main.yml` file under the role's "default" directory to suit your needs.

  . Edit ansible/playbooks/inventory/hosts to add targets under webservers.

  . Run `lowlatency` provisioning as below
  ```
  ansible-playbook  -i ansible/playbooks/inventory/hosts ansible/playbooks/deploy-lowlatency.yml
  ```
  . Run `powersaving` provisioning as below
  ```
  ansible-playbook  -i ansible/playbooks/inventory/hosts ansible/playbooks/deploy-powersaving.yml
  ```
. Run `lowpower` and `very-lowpower` provisioning as below.
  The playbook `deploy-powerupdown.yml` will take care of setting the
  system to below profiles.

   ```lowpower```

   This profile turns the C6 C-state `on` or `off` for the list of cores the
   user wants. User has to specify the list of cores and C6 C-state as
   `on` or `off`.

  ```very-lowpower```

  This profile turns C6 C-state `on` or `off` for the list of cores the user
  wants. It will also lower the max frequency of the cores by the given number
  of bins. User has to specify the list of cores on which C6 C-state should be
  `on` or `off`. Also, user has to specify the number of bins by which max frequency
  of the listed cores should be lowered. The user should specify the core list,
  C6 C-state, bins and action details as variables in either of the below files.

  ```
  /etc/ansible/hosts
  /etc/ansible/hosts.yaml
  /etc/ansible/group_vars/<serversgroup.yml>
  Example: /etc/ansible/group_vars/webservers.yaml
  ```
 The action sections with variables should be added like below. The number of actions can vary. 

 **Note:** Do not add actions with an empty core list.

 ```
  actions_to_apply:
    - action: lowpower
      c6state: 'on'
      core_list:
        - 10
        - 11
    - action: very-lowpower
      bins_to_lower: 2
      c6state: 'off'
      core_list:
        - 1
        - 3
    - action: very-lowpower
      bins_to_lower: 4
      c6state: 'off'
      core_list:
        - 8
        - 9
 ```

  ```
  ansible-playbook  -i ansible/playbooks/inventory/hosts ansible/playbooks/deploy-powerupdown.yml
  ```
