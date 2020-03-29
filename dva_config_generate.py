#!/usr/bin/env python

'''
github : https://github.com/liangxiao1/mini_utils
This tool is for checking ec2 environment to generate configuration for dva run.
The cfg file is /etc/dva.yaml.
dva repo: https://github.com/RedHatQE/dva
'''
import json
import string
import os
import sys
if sys.version.startswith('2'):
    print('Only support run in python3')
    sys.exit(1)
import logging
import argparse
import boto3
from botocore.exceptions import ClientError
import shutil
from yaml import load, dump
try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper
#/etc/dva.yaml
credential_file = 'data/dva_key.yaml'

parser = argparse.ArgumentParser(
    'Generate configuration for dva running in /etc/dva.yaml')
parser.add_argument('--tag', dest='tag', action='store', default='virtqes1',
                    help='check resource by tag, default is virtqes1', required=False)
parser.add_argument('--pubkeyfile', dest='pubkeyfile', action='store',
                    help='specify pub keyfile', required=True)
parser.add_argument('--sshkeyfile', dest='sshkeyfile', action='store',
                    help='specify private ssh keyfile', required=True)
parser.add_argument('--tokenfile', dest='tokenfile', action='store', default="data/dva_key.yaml",
                    help='awscli token file', required=True)
parser.add_argument('--target', dest='target', action='store', default="aws",
                    help='optional, can be aws or aws-china or aws-us-gov', required=False)
parser.add_argument('--dir', dest='dir', action='store',
                    help='dir to save file', required=False)
parser.add_argument('-d', dest='is_debug', action='store_true', default=False,
                    help='Run in debug mode', required=False)
args = parser.parse_args()
log = logging.getLogger(__name__)
if args.is_debug:
    logging.basicConfig(level=logging.DEBUG,
                        format='%(levelname)s:%(message)s')
else:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(message)s')

credential_file = args.tokenfile
final_file = '%s/dva.yaml' % args.dir
credential_file_format = "aws-us-gov: ['ec2_access_key','ec2_secret_key','subscription_username','subscription_password']"

def vpc_check(vpcid, region):
    ec2 = boto3.resource('ec2', region_name=region)
    try:
        vpc = ec2.Vpc(vpcid)
        log.info("vpc init %s", vpcid)
    except Exception as error:
        log.info("vpc init error %s, %s", vpci, str(error))
        return False
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
            return False
    except Exception as error:
        log.info("default sg get error")
        return False
    try:
        sg = ec2.SecurityGroup(sg.id)
        ips = sg.ip_permissions
        for ip in ips:
            ip_ranges = ip['IpRanges']
            log.info(ip_ranges)
            for ip_range in ip_ranges:
                if '0.0.0.0/0' in ip_range['CidrIp']:
                    log.info("vpc check pass!")
                    return True
        return False
    except Exception as error:
        log.info("sg init error %s",sg.id)
        return False

if not os.path.exists(credential_file):
    log.error("%s not found in /etc, please create it and add your key into it as the following format, multilines support if have" % credential_file)
    log.info(credential_file_format)
    sys.exit(1)
with open(credential_file,'r') as fh:
     keys_data = load(fh, Loader=Loader)
subnet_info = ''
ssh_key_info = ''
keyname = 'virtqe_s1'
ACCESS_KEY = keys_data[args.target][0]
SECRET_KEY = keys_data[args.target][1]
subscription_username = keys_data[args.target][2]
subscription_password = keys_data[args.target][3]

default_regions = [ "cn-northwest-1", "us-gov-west-1", "us-west-2"]
for region in default_regions:
    try:
        client = boto3.client(
            'ec2',
            aws_access_key_id=ACCESS_KEY,
            aws_secret_access_key=SECRET_KEY,
            region_name=region,
        )
        region_list = client.describe_regions()['Regions']
        log.info("set default region: %s", region)
        break
    except ClientError as error:
        log.info("find default region...... skip %s", region)
        continue
#region_list = client.describe_regions()['Regions']
regionids = []
for region in region_list:
    regionids.append(region['RegionName'])
ssh_key_str = ''
subnet_str = ''
for region in regionids:
    client = boto3.client(
    'ec2',
    aws_access_key_id=ACCESS_KEY,
    aws_secret_access_key=SECRET_KEY,
    region_name=region,
    )
    subnet_id = None
    subnets = client.describe_subnets()['Subnets']
    for subnet in subnets:
        if subnet['MapPublicIpOnLaunch']:
            vpc_id = subnet['VpcId']
            if vpc_check(vpc_id, region):
                subnet_id = subnet['SubnetId']
                break
    if subnet_id is None:
        log.info("No ipv4 pub enabed subnets found in region %s", region)
    log.info("Found existing subnet: %s in region %s", subnet_id, region)
    ssh_key_str += '      %s: [%s,%s]\n' % (region, keyname, args.sshkeyfile)
    subnet_str += '    %s: [%s]\n' % (region, subnet_id)
    log.info('check %s key existing status in %s', keyname, region)
    pubkeyfile = args.pubkeyfile
    if not os.path.exists(pubkeyfile):
        log.info("%s not found!", pubkeyfile)
        sys.exit(1)

    #keyfile = '/home/xiliang/ec2/dva_keys/virtqe_s1.pub'
    with open(pubkeyfile, 'r') as fh:
        pubkeystr=fh.readlines()[0]

    try:
        response = client.import_key_pair(
            DryRun=False,
            KeyName=keyname,
            PublicKeyMaterial=pubkeystr
        )
        log.info("%s added!", keyname)
    except Exception as error:
        if 'Duplicate' in str(error):
            log.info("%s already exists", keyname)
        else:
            log.info('%s', error)

ssh_key_str = ssh_key_str.rstrip('\n')
subnet_str = subnet_str.rstrip('\n')
dva_templ = string.Template("""bugzilla: {password: password, user: user@example.com}
cloud_access:
  ec2:
    ec2_access_key: $ec2_access_key
    ec2_secret_key: $ec2_secret_key
    ssh:
$ssh_key_info
  openstack:
    ec2_access_key: AAAAAAAAAAAAAAAAAAAA
    ec2_secret_key: B0B0B0B0B0B0B0B0B0B0a1a1a1a1a1a1a1a1a1a1
    endpoint: 192.168.0.1
    path: /services/Cloud
    port: 8773
    ssh: [user, /home/user/.pem/openstack.pem]
  subscription_manager:
    subscription_username: $subscription_username
    subscription_password: $subscription_password
  subnet:
$subnet_info
#global_setup_script: /tmp/setup_script.sh
""")
final_cfg = dva_templ.substitute(ec2_access_key=ACCESS_KEY, ec2_secret_key=SECRET_KEY,ssh_key_info=ssh_key_str,
    subnet_info=subnet_str,subscription_username=subscription_username,subscription_password=subscription_password)
with open(final_file,'wt') as fh:
    fh.write(final_cfg)
    log.info("New file generated: %s", final_file)
