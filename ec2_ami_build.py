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
import tempfile
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
        self.session = boto3.session.Session(profile_name=args.profile, region_name=args.region)
        self.ec2 = self.session.resource('ec2', region_name=args.region)

        self.ami_id = args.ami_id
        self.key_name = args.key_name
        self.security_group_ids = args.security_group_ids
        self.subnet_id = args.subnet_id
        self.instance_type = args.instance_type
        self.region = args.region
        self.vm = None
    def vpc_check(self, vpcid, region):
        '''
        check whether the vpc's default security group allow ssh connection
        '''
        self.session = boto3.session.Session(profile_name=args.profile, region_name=region)
        ec2 = self.session.resource('ec2', region_name=region)
        try:
            vpc = ec2.Vpc(vpcid)
            log.info("vpc init %s", vpcid)
        except Exception as error:
            log.info("vpc init error %s, %s", vpci, str(error))
            return False
        try:
            sgs = vpc.security_groups.all()
        except Exception as error:
            log.info("default sg get error: %s", str(error))
            return False
        for sg in sgs:
            try:
                sg = ec2.SecurityGroup(sg.id)
                ips = sg.ip_permissions
                for ip in ips:
                    ip_ranges = ip['IpRanges']
                    log.info(ip_ranges)
                    for ip_range in ip_ranges:
                        if '0.0.0.0/0' in ip_range['CidrIp']:
                            log.info("find security group: %s vpc check pass!", sg.id)
                            self.security_group_ids = sg.id
                            return True
                log.info("Security group not found, please check manually")
                return False
            except Exception as error:
                log.info("sg init error %s",sg.id)
                return False
    def find_subnet(self):
        self.session = boto3.session.Session(profile_name=args.profile, region_name=self.region)
        client = self.session.client('ec2', region_name=self.region)
        subnet_id = None
        subnets = client.describe_subnets()['Subnets']
        for subnet in subnets:
            if subnet['MapPublicIpOnLaunch']:
                vpc_id = subnet['VpcId']
                if self.vpc_check(vpc_id, self.region):
                    self.subnet_id = subnet['SubnetId']
                    break
        if self.subnet_id is None:
            log.info("No ipv4 pub enabed subnets found in region %s", self.region)
            vpc = self.vpc_create(client, self.region)
            subnets = client.describe_subnets()['Subnets']
            for subnet in subnets:
                if subnet['MapPublicIpOnLaunch']:
                    vpc_id = subnet['VpcId']
                    if self.vpc_check(vpc_id, self.region):
                        self.subnet_id = subnet['SubnetId']
                        break
        if self.subnet_id is None:
            log.info("No suitale subnet found in %s, please check manually %s", self.region)
        log.info("Found existing subnet: %s in region %s", self.subnet_id, self.region)

    def igw_create(self, client, vpcid):
        '''
        create a new igw and attach to vpc
        '''
        self.session = boto3.session.Session(profile_name=args.profile, region_name=self.region)
        ec2 = self.session.resource('ec2', region_name=self.region)
        try:
            igw_new = client.create_internet_gateway(
                DryRun=False
            )
            igwid = igw_new['InternetGateway']['InternetGatewayId']
            log.info("New igw created %s", igwid)
            igw = ec2.InternetGateway(igwid)
            igw.create_tags(
                DryRun=False,
                Tags=[
                    {
                        'Key': 'Name',
                        'Value': args.tag
                    },
                ]
            )
            igw.attach_to_vpc(
                DryRun=False,
                VpcId=vpcid
            )
            return igw
        except Exception as err:
            if 'Resource.AlreadyAssociated' in str(err):
                return igw
            log.info(str(err))
            return None

    def rt_update(self, client, vpc, igw):
        '''
        update default route table
        '''
        self.session = boto3.session.Session(profile_name=args.profile, region_name=self.region)
        ec2 = self.session.resource('ec2', region_name=self.region)

        try:
            rts = vpc.route_tables.all()
            for i in rts:
                for x in i.associations_attribute:
                    if x['Main']:
                        log.info("found route table, %s", i.id)
                        rt = i
            #rt = vpc.create_route_table(
            #    DryRun=False,
            #
            #)
            #log.info("New route table created %s", rt.id)
            log.info("Update route table %s", rt.id)
            rt.create_tags(
                DryRun=False,
                Tags=[
                    {
                        'Key': 'Name',
                        'Value': args.tag
                    },
                ]
            )
            log.info("tag added")
            route = rt.create_route(
                DestinationCidrBlock='0.0.0.0/0',
                DryRun=False,
                GatewayId=igw.id,
            )

            return rt
        except Exception as err:
            log.info(str(err))
            return None

    def sg_update(self, client, vpc, igw):
        '''
        update default security group
        '''
        self.session = boto3.session.Session(profile_name=args.profile, region_name=self.region)
        ec2 = self.session.resource('ec2', region_name=self.region)
        try:
            sgs = vpc.security_groups.all()
            sg = None
            for i in sgs:
                log.debug("sg name %s", i.group_name)
                if "default" in i.group_name:
                    sg = i
                    break
            if sg == None:
                log.info("No default named security group")
                return None
        except Exception as error:
            log.info("default sg get error: %s", str(error))
            return None
        try:
            #sg = vpc.create_security_group(
            #    Description='virtqe s1',
            #    GroupName='default',
            #    DryRun=True
            #)
            #log.info("New security group created %s", sg.id)
            sg.create_tags(
                DryRun=False,
                Tags=[
                    {
                        'Key': 'Name',
                        'Value': args.tag
                    },
                ]
            )
            log.info("tag added")
            response = sg.authorize_ingress(
                IpPermissions=[
                    {
                        "PrefixListIds": [],
                        "FromPort": 22,
                        "IpRanges": [
                            {
                                "CidrIp": "0.0.0.0/0"
                            }
                        ],
                        "ToPort": 22,
                        "IpProtocol": "tcp",
                        "UserIdGroupPairs": [],
                        "Ipv6Ranges": []
                    },
                    {
                        "PrefixListIds": [],
                        "FromPort": -1,
                        "IpRanges": [],
                        "ToPort": -1,
                        "IpProtocol": "icmpv6",
                        "UserIdGroupPairs": [],
                        "Ipv6Ranges": [
                            {
                                "CidrIpv6": "::/0"
                            }
                        ]
                    },
                    {
                        "PrefixListIds": [],
                        "FromPort": -1,
                        "IpRanges": [
                            {
                                "CidrIp": "0.0.0.0/0"
                            }
                        ],
                        "ToPort": -1,
                        "IpProtocol": "icmp",
                        "UserIdGroupPairs": [],
                        "Ipv6Ranges": []
                    }
                ]
            )
            log.info("Enabled ssh port created %s", sg.id)

            return sg
        except Exception as err:
            log.info(str(err))
            return None

    def subnet_create(self, client, vpc):
        '''
        create a new subnet
        '''
        self.session = boto3.session.Session(profile_name=args.profile, region_name=self.region)
        ec2 = self.session.resource('ec2', region_name=self.region)
        try:
            subnet = vpc.create_subnet(
                CidrBlock='192.111.1.0/24',
                DryRun=False
            )

            log.info("New subnet created %s", subnet.id)
            subnet.create_tags(
                DryRun=False,
                Tags=[
                    {
                        'Key': 'Name',
                        'Value': args.tag
                    },
                ]
            )
            log.info("tag added")
            client.modify_subnet_attribute(
                MapPublicIpOnLaunch={
                    'Value': True
                },
                SubnetId=subnet.id
            )
            log.info("enabled ipv4 on launch")
            return subnet
        except Exception as err:
            log.info(str(err))
            return None

    def vpc_create(self, client, region):
        '''
        create a new vpc for test running
        '''
        log.info("create a new vpc for test running")
        try:
            vpc_new = client.create_vpc(
                CidrBlock='192.111.0.0/16',
                AmazonProvidedIpv6CidrBlock=True,
                DryRun=False,
                InstanceTenancy='default'
            )
        except Exception as err:
            log.info("Failed to create vpc %s", str(err))
        vpcid = vpc_new['Vpc']['VpcId']
        log.info("New vpc created %s", vpcid)
        self.session = boto3.session.Session(profile_name=args.profile, region_name=region)
        ec2 = self.session.resource('ec2', region_name=region)
        try:
            vpc = ec2.Vpc(vpcid)
            log.info("vpc init %s", vpcid)
            tag = vpc.create_tags(
                DryRun=False,
                Tags=[
                    {
                        'Key': 'Name',
                        'Value': args.tag
                    },
                ]
            )
            log.info("added tag to vpc: %s", args.tag)
            vpc.modify_attribute(
                EnableDnsHostnames={
                    'Value': True
                }
            )
            log.info("Enabled dns support")
        except Exception as error:
            log.info(str(error))
            return False
        igw = self.igw_create(client, vpcid)
        if igw == None:
            return vpc
        rt = self.rt_update(client, vpc, igw)
        if rt == None:
            return vpc
        subnet = self.subnet_create(client, vpc)
        if subnet == None:
            return vpc
        sg = self.sg_update(client, vpc, igw)
        if sg == None:
            return vpc

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
                #Placement={
                #    'AvailabilityZone': self.zone,
                #},
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
                logging.info("Can create in %s", self.region)
                return self.vm
            logging.error("Can not create in %s : %s", self.region, err)
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
    description="Create new ami from existing AMIs \
    eg.  python ec2_ami_build.py -c --ami-id xxxx --key_name xxxx  --keyfile xxxx --region us-west-2 --pkgs xxxx")

parser.add_argument('-d', dest='is_debug', action='store_true',
                    help='run in debug mode', required=False)
parser.add_argument('--ami-id', dest='ami_id', default=None, action='store',
                    help='base ami id', required=True)
parser.add_argument('--user', dest='user', default="ec2-user", action='store',
                    help='user for ssh login, default is ec2-user', required=False)
parser.add_argument('--keyfile', dest='keyfile', default=None, action='store',
                    help='keyfile for ssh login', required=True)
parser.add_argument('--profile', dest='profile', default='default', action='store',
                    help='option, profile name in aws credential config file, default is default', required=False)
parser.add_argument('--key_name', dest='key_name', default=None, action='store',
                    help='key pairs name for create instance', required=True)
parser.add_argument('--security_group_ids', dest='security_group_ids', default=None, action='store',
                    help='security_group_ids, will auto find one if not specified', required=False)
parser.add_argument('--subnet_id', dest='subnet_id', default=None, action='store',
                    help='subnet_id, will auto find one if not specified', required=False)
parser.add_argument('--instance_type', dest='instance_type', default='t2.large', action='store',
                    help='specify instance type, default is t2.large', required=False)
parser.add_argument('--region', dest='region', default="us-west-2", action='store',
                    help='which zone you are using, default is us-west-2 ', required=True)
parser.add_argument('--timeout', dest='timeout', default=None, action='store',
                    help='bare metal can set to 8hrs each, others can be 7200 each, default it 28800s', required=False)
parser.add_argument('--tag', dest='tag', default=None, action='store',
                    help='resource tag to identify,default is virtqe', required=False)
parser.add_argument('--pkg_url', dest='pkg_url', default=None, action='store',
                    help='specify it which pkgs are not in repo, seperate by ","', required=False)
parser.add_argument('--repo_url', dest='repo_url', default=None, action='store',
                    help='specify it if sync with repo, or pkg dependency,seperate by ","', required=False)
parser.add_argument('--pkgs',dest='pkgs',default=None,action='store',help='if repo is accessible, specify pkg names which you want to add',required=False)
parser.add_argument('--cmds',dest='cmds',default=None,action='store',help='excute cmd before starting to create ami',required=False)
parser.add_argument('--proxy_url', dest='proxy_url', default=None, action='store',
                    help='specify it if pkg/repo url is internal only, format IP:PORT', required=False)

args = parser.parse_args()
log = logging.getLogger(__name__)
FORMAT = "%(levelname)s:FUNC-%(funcName)s:%(message)s"

if args.is_debug:
    logging.basicConfig(level=logging.DEBUG, format=FORMAT)
else:
    logging.basicConfig(level=logging.INFO, format=FORMAT)


def create_ami():
    signal.signal(signal.SIGHUP, sig_handler)
    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGQUIT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)
    VM = EC2VM()
    if args.subnet_id is None:
        VM.find_subnet()
    if VM.subnet_id is None:
        sys.exit(1)
    if VM.security_group_ids is None:
        sys.exit(1)
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
                log.info("Terminate instance %s" % vm.id)
                vm.terminate()
                sys.exit(1)
            if args.keyfile is None:
                log.info('No key specified, use defaut!')
                ssh_client.load_system_host_keys()
                ssh_client.connect(vm.public_dns_name, username=args.user)
            else:
                log.info('Use key: {}'.format(args.keyfile))
                if not os.path.exists(args.keyfile):
                    log.error("{} not found".format(args.keyfile))
                    log.info("Terminate instance %s" % vm.id)
                    vm.terminate()
                    sys.exit(1)
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
            log.info("Retry again, timeout 180s!")
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
    if args.repo_url is None or len(args.repo_url) <= 20:
        run_cmd(ssh_client, "sudo yum repolist --enabled")
        ret = run_cmd(ssh_client, "sudo yum search kernel-debug")
        if ret != 0:
            log.info("Try to enable default repo if no repo_url specified!")
            run_cmd(ssh_client, "sudo sed  -i 's/enabled=0/enabled=1/g' /etc/yum.repos.d/ami.repo")
    if args.repo_url is not None and len(args.repo_url) > 20:
        if args.proxy_url is not None:
            repo_temp = string.Template('''
[repo$id]
name=repo$id
baseurl = $repo_url
enabled=1
gpgcheck=0
proxy=http://127.0.0.1:8080
            ''')
        else:
            repo_temp = string.Template('''
[repo$id]
name=repo$id
baseurl = $repo_url
enabled=1
gpgcheck=0
            ''')
        fh, tmp_repo_file = tempfile.mkstemp(suffix='_ami.repo',  dir='/tmp', text=False)
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
        run_cmd(ssh_client, 'sudo yum remove -y kernel-debug')
        run_cmd(ssh_client, 'sudo yum remove -y kernel-debug-core kernel-debug-modules')
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
        if os.path.exists(tmp_repo_file):
            os.unlink(tmp_repo_file)
            log.info("delete tempfile %s", tmp_repo_file)

        for i in range(1,20):
            ret_val = run_cmd(ssh_client, 'sudo yum update -y --allowerasing')
            if ret_val > 0:
                log.error("Failed to update system, try again! max:20 now:%s" % i)
                time.sleep(5)
                continue
            break
        if ret_val > 0:
            log.error("Failed to update system again, exit!")
            vm.terminate()
            sys.exit(ret_val)
    if args.pkgs is not None:
        for i in range(1,50):
            ret_val = run_cmd(ssh_client, 'sudo yum install -y %s' % args.pkgs.replace(',',' '))
            if ret_val > 0:
                log.error("Failed to update system, try again! max:50 now:%s" % i)
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
    run_cmd(ssh_client, 'sudo yum install -y python3')
    run_cmd(ssh_client, 'sudo pip3 install -U os-tests')
    if args.cmds is not None:
        run_cmd(ssh_client, 'sudo {}'.format(args.cmds))
    if args.repo_url is not None:
        run_cmd(ssh_client, "sudo sed  -i 's/enabled=1/enabled=0/g' /etc/yum.repos.d/ami.repo")
        run_cmd(ssh_client, 'cat /etc/yum.repos.d/ami.repo')
    run_cmd(ssh_client, "sudo mkdir -p /etc/systemd/system/nm-cloud-setup.service.d")
    run_cmd(ssh_client, "sudo bash -c \"echo -e '[Service]\nEnvironment=NM_CLOUD_SETUP_EC2=yes\n' > /etc/systemd/system/nm-cloud-setup.service.d/override.conf\"")
    #run_cmd(ssh_client, "sudo sed -i 's/#Environment=NM_CLOUD_SETUP_EC2=yes/Environment=NM_CLOUD_SETUP_EC2=yes/g' /usr/lib/systemd/system/nm-cloud-setup.service")
    if ret_val > 0:
        log.error("Failed to update system!")
        vm.terminate()
        sys.exit(ret_val)
    log.info("Start to create AMI ......")
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
        try:
            if image.state == 'available':
                break
            image.reload()
            time.sleep(5)
        except ClientError as err:
            log.info('%s', err)
    log.info("Terminate instance %s" % vm.id)
    vm.terminate()
    log.info("New AMI:%s" % image.id)
    return image.id


if __name__ == '__main__':
    create_ami()
