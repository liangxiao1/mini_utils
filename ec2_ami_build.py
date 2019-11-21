#!/usr/bin/env python
'''
github : https://github.com/liangxiao1/mini_utils

This tool is for buiding  a new ami from an existing ami with updating,installing new pkgs.

'''

from __future__ import print_function
import string
import logging
import argparse
import os
import sys
import random
import boto3
from botocore.exceptions import ClientError
import signal
import re

import socket
import select
import threading
import paramiko

import wget

import time

import pdb
import string

default_port = 22

ret_val = 0
def sig_handler(signum, frame):
    logging.info('Got signal %s, exit!', signum)
    sys.exit(0)


def handler(chan, host, port):
    sock = socket.socket()
    try:
        sock.connect((host, port))
    except Exception as e:
        log.debug("Forwarding request to %s:%d failed: %r" %
                  (host, port, e))
        return

    log.debug(
        "Connected!  Tunnel open %r -> %r -> %r"
        % (chan.origin_addr, chan.getpeername(), (host, port))
    )
    retry_count = 0
    while True:
        r, w, x = select.select([sock, chan], [], [])
        if sock in r:
            data = sock.recv(1024)
            if len(data) == 0:
                retry_count+=1
                if retry_count>100:
                    log.debug("No data received from sock")
                    break
            else:
                chan.send(data)
        if chan in r:
            data = chan.recv(1024)
            if len(data) == 0:
                if retry_count>100:
                    log.debug("No data received from chan")
                    break
            else:
                sock.send(data)
    chan.close()
    sock.close()
    log.debug("Tunnel closed from %r" % (chan.origin_addr,))


def reverse_forward_tunnel(server_port, remote_host, remote_port, transport):
    transport.request_port_forward("", server_port)

    while True:
        chan = transport.accept(1000)
        if chan is None:
            continue
        thr = threading.Thread(
            target=handler, args=(chan, remote_host, remote_port)
        )
        thr.setDaemon(True)
        thr.start()


class EC2VM:
    def __init__(self):
        self.ec2 = boto3.resource('ec2')

        self.ami_id = args.ami_id
        self.key_name = args.key_name
        self.security_group_ids = args.security_group_ids
        self.subnet_id = args.subnet_id
        self.instance_type = args.instance_type
        self.zone = args.zone
        self.vm = None

    def create(self, wait=True):
        try:
            self.vm = self.ec2.create_instances(
                ImageId=self.ami_id,
                InstanceType=self.instance_type,
                KeyName=self.key_name,
                SecurityGroupIds=[
                    self.security_group_ids,
                ],
                SubnetId=self.subnet_id,
                MaxCount=1,
                MinCount=1,
                Placement={
                    'AvailabilityZone': self.zone,
                },
                # DryRun=True,
                TagSpecifications=[
                    {
                        'ResourceType': 'instance',
                        'Tags': [
                            {
                                'Key': 'Name',
                                'Value': args.tag
                            },
                        ]
                    },
                ]
            )[0]

        except ClientError as err:
            if 'DryRunOperation' in str(err):
                logging.info("Can create in %s", self.zone)
                return self.vm
            logging.error("Can not create in %s : %s", self.zone, err)
            return None
        return self.vm


def get_pkg_name(s=None):
    tmp_list = s.split('-')
    x = ''
    for i in tmp_list:
        if i[0].isdigit():
            break
        x += i+'-'
    return x.rstrip('-')


def run_cmd(ssh_client, cmd, timeout=1800):
    log.info("Run %s" % cmd)
    stdin, stdout, stderr = ssh_client.exec_command(
        cmd, timeout=timeout)
    while not stdout.channel.exit_status_ready() and stdout.channel.recv_exit_status():
        time.sleep(60)
        log.info("Wait command complete......")
    try:
        log.info("cmd output:")
        for line in stdout.readlines():
            log.info("%s" % line.rstrip('\n'))
        log.info("cmd error:")
        for line in stderr.readlines():
            log.info("%s" % line.rstrip('\n'))

    except Exception as e:
        log.info("Cannot get output/error from above command: %s" % e)
    ret = stdout.channel.recv_exit_status()
    log.info("cmd return: %s" % ret)
    return ret


parser = argparse.ArgumentParser(
    description="Generate instance type yaml file for avocado-cloud test. \
    eg.  python ec2_ami_build.py -c --ami-id xxxx --key_name xxxx --security_group_ids xxxx --subnet_id xxxx --region us-west-2 ")

parser.add_argument('-d', dest='is_debug', action='store_true',
                    help='run in debug mode', required=False)
parser.add_argument('--ami-id', dest='ami_id', default=None, action='store',
                    help='base ami id', required=False)
parser.add_argument('--user', dest='user', default=None, action='store',
                    help='user for login', required=False)
parser.add_argument('--keyfile', dest='keyfile', default=None, action='store',
                    help='keyfile for login', required=False)
parser.add_argument('--key_name', dest='key_name', default=None, action='store',
                    help='key name for create instance', required=False)
parser.add_argument('--security_group_ids', dest='security_group_ids', default=None, action='store',
                    help='security_group_ids', required=False)
parser.add_argument('--subnet_id', dest='subnet_id', default=None, action='store',
                    help='subnet_id', required=False)
parser.add_argument('--instance_type', dest='instance_type', default='t2.large', action='store',
                    help='specify instance type, default is t2.large', required=False)
parser.add_argument('--zone', dest='zone', default=None, action='store',
                    help='which zone you are using ', required=False)
parser.add_argument('--timeout', dest='timeout', default=None, action='store',
                    help='bare metal can set to 8hrs each, others can be 7200 each, default it 28800s', required=False)
parser.add_argument('--tag', dest='tag', default=None, action='store',
                    help='resource tag to identify,default is virtqe', required=False)
parser.add_argument('--pkg_url', dest='pkg_url', default=None, action='store',
                    help='specify it which pkgs are not in repo, seperate by ","', required=False)
parser.add_argument('--repo_url', dest='repo_url', default=None, action='store',
                    help='specify it if sync with repo, or pkg dependency,seperate by ","', required=False)
parser.add_argument('--pkgs',dest='pkgs',default=None,action='store',help='if repo is accessible, specify pkg names which you want to add',required=False)
parser.add_argument('--proxy_url', dest='proxy_url', default=None, action='store',
                    help='specify it if pkg/repo url is internal only, format IP:PORT', required=False)


args = parser.parse_args()
log = logging.getLogger(__name__)
FORMAT = "%(levelname)s:FUNC-%(funcName)s:%(message)s"

if args.is_debug:
    logging.basicConfig(level=logging.DEBUG, format=FORMAT)
else:
    logging.basicConfig(level=logging.INFO, format=FORMAT)


def main():
    signal.signal(signal.SIGHUP, sig_handler)
    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGQUIT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)
    VM = EC2VM()
    vm = VM.create()
    if vm is None:
        sys.exit(1)
    vm.wait_until_running()
    vm.reload()
    log.info("Instance created: %s" % vm.id)
    log.info("Instacne ip:%s" % vm.public_dns_name)

    log.info("Try to make connection to it ......")
    ssh_client = paramiko.SSHClient()
    ssh_client.load_system_host_keys()
    ssh_client.set_missing_host_key_policy(paramiko.WarningPolicy())
    start_time = time.time()
    while True:
        try:
            end_time = time.time()
            if end_time-start_time > 180:
                log.info("Unable to make connection!")
                sys.exit(1)
            if args.keyfile is None:
                ssh_client.load_system_host_keys()
                ssh_client.connect(vm.public_dns_name, username=args.user)
            else:
                ssh_client.connect(
                    vm.public_dns_name,
                    username=args.user,
                    key_filename=args.keyfile,
                    look_for_keys=False,
                    timeout=180
                )
            break
        except Exception as e:
            log.info("*** Failed to connect to %s:%d: %r" %
                     (vm.public_dns_name, default_port, e))
            log.info("Retry more times!")
            time.sleep(10)
    if args.proxy_url is not None:
        log.info(
            "Now forwarding remote port 8080 to %s ..."
            % (args.proxy_url)
        )

        try:
            th_reverse = threading.Thread(target=reverse_forward_tunnel, args=(
                8080, args.proxy_url.split(':')[0], int(args.proxy_url.split(':')[
                    1]), ssh_client.get_transport()))
            th_reverse.setDaemon(True)
            th_reverse.start()
        except KeyboardInterrupt:
            print("C-c: Port forwarding stopped.")
            sys.exit(0)
        cmd = 'uname -a'
        run_cmd(ssh_client, cmd)
    if args.repo_url is not None:
        repo_temp = string.Template('''
[repo$id]
name=repo$id
baseurl = $repo_url
enabled=1
gpgcheck=0
proxy=http://127.0.0.1:8080
        ''')
        tmp_repo_file = '/tmp/ami.repo'
        if os.path.exists(tmp_repo_file):
            os.unlink(tmp_repo_file)
        id = 0
        with open(tmp_repo_file, 'a') as fh:
            for repo in args.repo_url.split(','):
                repo_str = repo_temp.substitute(id=id, repo_url=repo)
                log.info("Add new repo %s to %s" % (repo_str, tmp_repo_file))
                fh.writelines(repo_str)
                id += 1
        log.debug("Updated %s" % tmp_repo_file)
        with open(tmp_repo_file, 'r') as fh:
            for line in fh.readlines():
                log.debug(line)
        run_cmd(ssh_client, 'sudo rm -rf /etc/yum.repos.d/ami.repo')
        run_cmd(ssh_client, 'sudo yum repolist enabled')
        run_cmd(ssh_client, 'sudo yum-config-manager --disable rh*')
        run_cmd(ssh_client, 'sudo yum repolist enabled')
        ftp_client = ssh_client.open_sftp()
        ftp_client.put(tmp_repo_file, "/tmp/ami.repo")
        run_cmd(ssh_client, 'sudo mv /tmp/ami.repo /etc/yum.repos.d/ami.repo')
        run_cmd(ssh_client, 'ls -l /etc/yum.repos.d/')
        run_cmd(ssh_client, 'cat /etc/yum.repos.d/ami.repo')
        run_cmd(ssh_client, 'sudo bash -c "echo "" > /var/log/secure"')
        run_cmd(ssh_client, 'sudo  rm -rf /var/log/cloud-init.log')
        run_cmd(ssh_client, 'sudo  rm -rf /var/log/cloud-init-output.log')
        run_cmd(ssh_client, 'sudo bash -c "echo "minrate=200" >> /etc/yum.conf"')
        run_cmd(ssh_client, 'sudo bash -c "echo "timeout=1800" >> /etc/yum.conf"')
        for i in range(1,10):
            ret_val = run_cmd(ssh_client, 'sudo yum update -y')
            if ret_val > 0:
                log.error("Failed to update system, try again! max:10 now:%s" % i)
                time.sleep(5)
                continue
            break
        if ret_val > 0:
            log.error("Failed to update system again, exit!")
            vm.terminate()
            sys.exit(ret_val)
    if args.pkgs is not None:
        for i in range(1,10):
            ret_val = run_cmd(ssh_client, 'sudo yum install -y %s' % args.pkgs.replace(',',' '))
            if ret_val > 0:
                log.error("Failed to update system, try again! max:10 now:%s" % i)
                time.sleep(5)
                continue
            break
        if ret_val > 0:
            log.error("Failed to update system again, exit!")
            vm.terminate()
            sys.exit(ret_val)
    if args.pkg_url is not None:
        pkg_names = ''
        for pkg in args.pkg_url.split(','):
            pkg_name = pkg.split('/')[-1]
            pkg_name_no_ver = get_pkg_name(s=pkg_name)
            log.info("Download %s from %s to /tmp/" % (pkg_name, pkg))
            wget.download(pkg, '/tmp/%s' % pkg_name)
            time.sleep(2)
            log.info("Copy it to %s /tmp" % vm.public_dns_name)
            ftp_client = ssh_client.open_sftp()
            ftp_client.put("/tmp/%s" % pkg_name, "/tmp/%s" % pkg_name)
            pkg_names += ' /tmp/%s' % pkg_name
            if 'cloud-init' in pkg_name:
                run_cmd(ssh_client, 'sudo  rm -rf /var/lib/cloud/*')
                run_cmd(ssh_client, 'sudo  rm -rf /var/run/cloud-init/')
                run_cmd(ssh_client, 'sudo rpm -e %s' % pkg_name_no_ver)
        log.info("Install %s to instance!" % pkg_names)
        cmd = 'sudo yum localinstall -y %s' % pkg_names
        ret_val = run_cmd(ssh_client, cmd)
        if ret_val > 0:
            cmd = 'sudo rpm -ivh %s --force' % pkg_names
            ret_val = run_cmd(ssh_client, cmd)
        if 'cloud-init' in pkg_name:
            stdin, stdout, stderr = ssh_client.exec_command(
                'sudo  /bin/cp -f /etc/cloud/cloud.cfg.rpmsave /etc/cloud/cloud.cfg', timeout=1800)
    if ret_val > 0:
        log.error("Failed to update system!")
        vm.terminate()
        sys.exit(ret_val)
    image = vm.create_image(
        BlockDeviceMappings=[
            {
                'DeviceName': vm.root_device_name,
                'VirtualName': 'ephemeral0',
                'Ebs': {
                    'DeleteOnTermination': True,
                    'VolumeSize': 10,
                    'VolumeType':  'gp2',
                    'Encrypted': False
                },
                'NoDevice': ''
            },
        ],
        Description=args.tag,
        Name=args.tag,
        NoReboot=False
    )
    while True:
        if image.state == 'available':
            break
        image.reload()
        time.sleep(5)
    log.info("Terminate instance %s" % vm.id)
    vm.terminate()
    log.info("New AMI:%s" % image.id)
    return image.id


if __name__ == '__main__':
    main()
