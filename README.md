# Spark cluster deployment tools for Pouta (and other OpenStack based clouds)

This project provides scripts for Apache Spark cluster autodeploy in Pouta environment with optional useful tools. These playbooks may help you to install following:

* Apache Hadoop
* Apache Spark

This repositories is customized to run on Pouta clouds and is forked from https://github.com/ispras/spark-openstack.git developed by IPRAS (http://www.ispras.ru/en/). This repository is distributed with Apache 2.0 license. You are welcome to contribute.



Installation
============

1. Install Ansible.

2. Install Ansible Collection Openstack Cloud: `ansible-galaxy collection install openstack.cloud`


Configuration
=============

1. Download (unless already done so) <project-name>-openrc.sh from your Openstack Web UI
    (Project > Compute > Access & Security > API Access > Download OpenStack RC File)

    If you don't want to enter password each time and don't care about security, replace

        read -sr OS_PASSWORD_INPUT
        export OS_PASSWORD=$OS_PASSWORD_INPUT

    with (replace &lt;password&gt; with your password)

        export OS_PASSWORD="<password>"

    WARNING - it's not secure; do not do that.

2. Before running `./spark-openstack` this file must be sourced (once per shell session):

        source /path/to/your/<project>-openrc.sh

3. Download/upload key pair.
    You'll need both the name of key pair (Key Pair Name column in  Access & Security > Key Pairs) and prite key file.
    Make sure that only user can read private key file (`chmod og= <key-file-name>`).
    Make sure private key does **not** have a passphrase.

Running
=======

* To create a cluster, source your <project>-openrc.sh file and run 

        cd spark-openstack/ansible
        ./spark_openstack_cmd.py --create -k <key-pair-name> -i <private-key> -s <n-slaves> \
           -t <instance-type> -a <os-image-id> -n <virtual-network> -f <floating-ip-pool> \
           [--deploy-spark] launch <cluster-name>

    replacing <xxx> with values of:

    * `<key-pair-name>` - key pair name
    * `<private-key>` - path to private key file
    * `<n-slaves>` - number of slaves
    * `<instance-type>` - instance flavor that exists in your Openstack environment (e.g. spark.large)
    * `<virtual-network>` - your virtual network name or ID (in Neutron or Nova-networking)
    * `<floating-ip-pool>` - floating IP pool name
    * `<cluster-name>` - name of the cluster (prefix 'surname' is a good practice)

    With this command would be created cluster with choosed number of slaves. Arguments to Spark autodeploy:

    * `--deploy-spark` - Deploy Spark with default version (3.4.0) and Hadoop with default version 3.3.5

    Spark-specific optional arguments:

    * `--spark-version <version>` use specific Spark version. Default is 3.4.0.
    * `--hadoop-version <version>` use specific Hadoop version for Spark. Default is the latest supported in Spark.
    * `--spark-worker-mem-mb <mem>` don't auto-detect spark worker memory and use specified value, can be useful if other
        processes on slave nodes (e.g. python) need more memory, default for 10Gb-20Gb RAM slaves is to leave 2Gb to
        system/other processes; example: `--spark-worker-mem-mb 10240`
    * `--master-instance-type <instance-type>` use another instance flavor for master

    Example:
    ```sh
    ./spark_openstack_cmd.py --create --deploy-spark -k mykeypair -i /home/al/.ssh/id_rsa -s 3 \
    -t standard.large -a 07c6f4c1-97ae-481e-abfb-e799ec52caf7 -n c55bc796-841f-4704-a1a2-8f29bb9a699a -f public \
    launch spark-cluster
    ```

* To destroy a cluster, run (**NOT TESTED**)

        ./spark_openstack_cmd.py -k <key-pair-name> -i <private-key> -s <n-slaves> \
           -t <instance-type> -a <os-image-id> destroy <cluster-name>

    all parameter values are same as for `launch` command

* All tools can be installed both during cluster creation and on an existing cluster.
  If a cluster has already been created, remove the option `--create`. This will speed up the deployment process.
  

Important notes
=======

* Please remeber to narrow down Security Group rules for the installed cluster, They are currently too open to avoid cluster lock in if cluster is installed from different IP pool and accessed form other.
*If any of actions fail after all instances are in active state, you can easily rerun the script and it will finish the work quite fast
* If you have only one virtual network in your Openstack project you may not specify it in options, it will be picked up automatically
* All unknown arguments are passed to `ansible-playbook`
## Tested configurations

Ansible: 2.14.5

Python: 3.11

Python Openstack SDK: 1.0.1

Ansible Collection Openstack Cloud 1.10.0

Management machine OS: macOS Ventura

Guest OS:

* Ubuntu 22.04


## Known issues

* Limited support for security groups in Openstack. Current rules allow all the traffic ingress and egress. PLEASE MODIFY THESE SECURITY GROUPS TO ALLOW THE IP SUBNETS WHICH SHOULD HAVE ACCESS TO CLUSTER.
