#!/usr/bin/python3
# -*- coding: utf-8 -*-



from __future__ import print_function
import argparse
import sys
import subprocess
import os
import urllib
from zipfile import ZipFile
from shutil import rmtree
from urllib.parse import urlparse


spark_versions = \
    {
        "3.4.0": {"hadoop_versions": ["3.3"]},
    }

parser = argparse.ArgumentParser(description='Spark cluster deploy tools for Openstack.',
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog='Usage real-life examples:\t\n'
                                        '   ./spark-openstack -k key -i ~/.ssh/id_rsa -s 2 -t spark.large -a 20545e58-59de-4212-a83f-3703b31622cf -n computations-net -f external_network --deploy-spark launch spark-cluster\n'
                                        '   ./spark-openstack destroy spark-cluster\n'
                                        'Look through README.md for more advanced usage examples.\n'
                                        'Apache 2.0, ISP RAS 2016 (http://ispras.ru/en).\n')

parser.add_argument('act', type=str, choices=["launch", "destroy", "get-master", "config", "runner"])
parser.add_argument('cluster_name', help="Name for your cluster")
parser.add_argument('option', nargs='?')
parser.add_argument('-k', '--key-pair')
parser.add_argument("-i", "--identity-file")
parser.add_argument("-s", "--slaves", type=int)
parser.add_argument("-n", "--virtual-network", help="Your virtual Openstack network id for cluster. If have only one network, you may not specify it")
parser.add_argument("-f", "--floating-ip-pool", help="Floating IP pool")
parser.add_argument("-t", "--instance-type")
parser.add_argument("-m", "--master-instance-type", help="master instance type, defaults to same as slave instance type")
parser.add_argument("-a", "--image-id")
parser.add_argument("-w", help="ignored")

parser.add_argument("--create", action="store_true", help="Note that cluster should be created")
parser.add_argument("--deploy-spark", action="store_true", help="Should we deploy Spark (with Hadoop)")
parser.add_argument("--spark-version", default="3.4.0", help="Spark version to use")
parser.add_argument("--hadoop-version", help="Hadoop version to use")
parser.add_argument("--hadoop-user", default="ubuntu", help="User to use/create for cluster members")
parser.add_argument("--ansible-bin", help="path to ansible (and ansible-playbook, default='')")

parser.add_argument("--sync", action="store_true",
                    help="Sync Openstack operations (may not work with some Openstack environments)")

parser.add_argument("--tags", help="Ansible: run specified tags")
parser.add_argument("--skip-tags", help="Ansible: skip specified tags")


#parser.add_argument("--step", action="store_true", help="Execute play step-by-step")

args, unknown = parser.parse_known_args()
if args.tags is not None:
    unknown.append("--tags")
    unknown.append(args.tags)

if args.skip_tags is not None:
    unknown.append("--skip-tags")
    unknown.append(args.skip_tags)

if args.master_instance_type is None:
    args.master_instance_type = args.instance_type

if "_" in args.cluster_name:
    print("WARNING: '_' symbols in cluster name are not supported, replacing with '-'")
    args.cluster_name = args.cluster_name.replace('_', '-')

ansible_cmd = "ansible"
ansible_playbook_cmd = "ansible-playbook"
if args.ansible_bin is not None:
    ansible_cmd = os.path.join(args.ansible_bin, "ansible")
    ansible_playbook_cmd = os.path.join(args.ansible_bin, "ansible-playbook")


def make_extra_vars():
    extra_vars = dict()
    extra_vars["act"] = args.act
    extra_vars["n_slaves"] = args.slaves
    extra_vars["cluster_name"] = args.cluster_name
    extra_vars["os_image"] = args.image_id
    extra_vars["os_key_name"] = args.key_pair
    extra_vars["flavor"] = args.instance_type
    extra_vars["master_flavor"] = args.master_instance_type
    extra_vars["floating_ip_pool"] = args.floating_ip_pool
    extra_vars["virtual_network"] = args.virtual_network
    extra_vars["ansible_user"] = args.hadoop_user
    extra_vars["ansible_ssh_private_key_file"] = args.identity_file

    extra_vars["os_project_name"] = os.getenv('OS_PROJECT_NAME') or os.getenv('OS_TENANT_NAME')
    if not extra_vars["os_project_name"]:
        print("It seems that you h aven't sources your Openstack OPENRC file; quiting")
        exit(-1)

    extra_vars["os_auth_url"] = os.getenv('OS_AUTH_URL')
    if not extra_vars["os_auth_url"]:
        print("It seems that you haven't sources your Openstack OPENRC file; quiting")
        exit(-1)

    extra_vars["hadoop_user"] = args.hadoop_user

    if args.act == 'launch':
        extra_vars["create_cluster"] = args.create
        extra_vars["deploy_spark"] = args.deploy_spark
        # extra_vars["mountnfs"] = args.mountnfs
        extra_vars["spark_version"] = args.spark_version
        if args.hadoop_version:
            if args.hadoop_version not in spark_versions[args.spark_version]["hadoop_versions"]:
                print("Chosen Spark version doesn't support selected Hadoop version")
                exit(-1)
            extra_vars["hadoop_version"] = args.hadoop_version
        else:
            extra_vars["hadoop_version"] = spark_versions[args.spark_version]["hadoop_versions"][-1]
        print("Deploying Apache Spark %s with Apache Hadoop %s"
              % (extra_vars["spark_version"], extra_vars["hadoop_version"]))
    
    extra_vars["sync"] = "sync" if args.sync else "async"

    return extra_vars


def err(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)

def parse_host_ip(resp):
    """parse ansible debug output with var=hostvars[inventory_hostname].ansible_ssh_host and return host"""
    parts1 = resp.split("=>")
    if len(parts1) != 2: err("unexpected ansible output")
    parts2 = parts1[1].split(":")
    if len(parts2) != 3: err("unexpected ansible output")
    parts3 = parts2[1].split('"')
    if len(parts3) != 3: err("unexpected ansible output")
    return parts3[1]

def get_master_ip():
    vars = make_extra_vars()
    vars['extended_role'] = 'master'
    res = subprocess.check_output([ansible_playbook_cmd,
                                   "--extra-vars", repr(vars),
                                   "get_ip.yml"])
    return parse_host_ip(res.decode())

def get_ip(role):
    vars = make_extra_vars()
    vars['extended_role'] = role
    res = subprocess.check_output([ansible_playbook_cmd,
                                   "--extra-vars", repr(vars),
                                   "get_ip.yml"])
    return parse_host_ip(res.decode())

def ssh_output(host, cmd):
    return subprocess.check_output(["ssh", "-q", "-t", "-o", "StrictHostKeyChecking=no",
                                    "-o", "UserKnownHostsFile=/dev/null",
                                    "-i", args.identity_file, "ubuntu@" + host, cmd])

def ssh_first_slave(master_ip, cmd):
    #can't do `head -n1 /opt/spark/conf/slaves` since it's not deployed yet
    return ssh_output(master_ip, "ssh %s-slave-1 '%s'" % (args.cluster_name, cmd.replace("'", "'\\''")))

#FIXME: copied from https://github.com/amplab/spark-ec2/blob/branch-1.5/deploy_templates.py
def get_worker_mem_mb(master_ip):
    if args.spark_worker_mem_mb is not None:
        return args.spark_worker_mem_mb
    mem_command = "cat /proc/meminfo | grep MemTotal | awk '{print $2}'"

    ssh_first_slave_ = ssh_first_slave(master_ip, mem_command)
    if type(ssh_first_slave_) != "int":
        print(ssh_first_slave_)

    slave_ram_kb = int(ssh_first_slave_)
    slave_ram_mb = slave_ram_kb // 1024
    # Leave some RAM for the OS, Hadoop daemons, and system caches
    if slave_ram_mb > 100*1024:
        slave_ram_mb = slave_ram_mb - 15 * 1024 # Leave 15 GB RAM
    elif slave_ram_mb > 60*1024:
        slave_ram_mb = slave_ram_mb - 10 * 1024 # Leave 10 GB RAM
    elif slave_ram_mb > 40*1024:
        slave_ram_mb = slave_ram_mb - 6 * 1024 # Leave 6 GB RAM
    elif slave_ram_mb > 20*1024:
        slave_ram_mb = slave_ram_mb - 3 * 1024 # Leave 3 GB RAM
    elif slave_ram_mb > 10*1024:
        slave_ram_mb = slave_ram_mb - 2 * 1024 # Leave 2 GB RAM
    else:
        slave_ram_mb = max(512, slave_ram_mb - 1300) # Leave 1.3 GB RAM
    return slave_ram_mb


def get_master_mem(master_ip):
    mem_command = "cat /proc/meminfo | grep MemTotal | awk '{print $2}'"
    master_ram_kb = int(ssh_output(master_ip, mem_command))
    master_ram_mb = master_ram_kb // 1024
    # Leave some RAM for the OS, Hadoop daemons, and system caches
    if master_ram_mb > 100*1024:
        master_ram_mb = master_ram_mb - 15 * 1024 # Leave 15 GB RAM
    elif master_ram_mb > 60*1024:
        master_ram_mb = master_ram_mb - 10 * 1024 # Leave 10 GB RAM
    elif master_ram_mb > 40*1024:
        master_ram_mb = master_ram_mb - 6 * 1024 # Leave 6 GB RAM
    elif master_ram_mb > 20*1024:
        master_ram_mb = master_ram_mb - 3 * 1024 # Leave 3 GB RAM
    elif master_ram_mb > 10*1024:
        master_ram_mb = master_ram_mb - 2 * 1024 # Leave 2 GB RAM
    else:
        master_ram_mb = max(512, master_ram_mb - 1300) # Leave 1.3 GB RAM
    return "%s" % master_ram_mb


def get_slave_cpus(master_ip):
    return int(ssh_first_slave(master_ip, "nproc"))





cmdline = [ansible_playbook_cmd]
cmdline.extend(unknown)

extra_vars = make_extra_vars()

if args.act == "launch":
    cmdline_create = cmdline[:]
    cmdline_create.extend(["-v", "main.yml", "--extra-vars", repr(extra_vars)])
    subprocess.call(cmdline_create)
    master_ip = get_master_ip()
    print("Cluster launched successfully; Master IP is %s"%(master_ip))
elif args.act == "destroy":
    res = subprocess.check_output([ansible_cmd,
                                   "--extra-vars", repr(make_extra_vars()),
                                   "-m", "debug", "-a", "var=groups['%s_slaves']" % args.cluster_name,
                                   args.cluster_name + "-master"])
    extra_vars = make_extra_vars()
    cmdline_create = cmdline[:]
    cmdline_create.extend(["main.yml", "--extra-vars", repr(extra_vars)])
    subprocess.call(cmdline_create)
elif args.act == "get-master":
    print(get_master_ip())
elif args.act == "config":
    extra_vars = make_extra_vars()
    extra_vars['roles_dir'] = '../roles'

    cmdline_inventory = cmdline[:]
    if args.option == 'restart-spark': #Skip installation tasks, run only detect_conf tasks
        cmdline_inventory.extend(("--skip-tags", "spark_install"))

    elif args.option == 'restart-cassandra':
        cmdline_inventory.extend(("--skip-tags", "spark_install,cassandra"))

    cmdline_inventory.extend(["%s.yml" % args.option, "--extra-vars", repr(extra_vars)])
    subprocess.call(cmdline_inventory)
elif args.act == "runner":
    cmdline_create = cmdline[:]
    cmdline_create.extend(["prepare_internal_runner.yml", "--extra-vars",  repr(extra_vars)])
    subprocess.call(cmdline_create)
    runner_ip = get_ip('runner')
    print("Runner ready; IP is %s"%(runner_ip))
else:
    err("unknown action: " + args.act)
