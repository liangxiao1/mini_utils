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
                    help='credential file, default data/dva_key.yaml', required=False)
parser.add_argument('--target', dest='target', action='store', default="aws",
                    help='optional, can be aws or aws-china or aws-us-gov', required=False)
parser.add_argument('--output', dest='output', action='store', default="/tmp/dva.yaml",
                    help='save output to file name, default is /tmp/dva.yaml', required=False)
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
final_file = args.output
credential_file_format = "aws-us-gov: ['ec2_access_key','ec2_secret_key','subscription_username','subscription_password']"

def vpc_check(vpcid, region):
    '''
    check whether the vpc's default security group allow ssh connection
    '''
    ec2 = boto3.resource('ec2', region_name=region,  aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY)
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
        log.info("default sg get error: %s", str(error))
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

def igw_create(client, vpcid):
    '''
    create a new igw and attach to vpc
    '''

    ec2 = boto3.resource('ec2', region_name=region,  aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY)
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
                    'Value': keyname
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

def rt_update(client, vpc, igw):
    '''
    update default route table
    '''

    ec2 = boto3.resource('ec2', region_name=region,  aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY)
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
                    'Value': keyname
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

def sg_update(client, vpc, igw):
    '''
    update default security group
    '''

    ec2 = boto3.resource('ec2', region_name=region,  aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY)

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
                    'Value': keyname
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

def subnet_create(client, vpc):
    '''
    create a new subnet
    '''

    ec2 = boto3.resource('ec2', region_name=region,  aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY)
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
                    'Value': keyname
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

def vpc_create(client, region):
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
    ec2 = boto3.resource('ec2', region_name=region,  aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY)
    try:
        vpc = ec2.Vpc(vpcid)
        log.info("vpc init %s", vpcid)
        tag = vpc.create_tags(
            DryRun=False,
            Tags=[
                {
                    'Key': 'Name',
                    'Value': keyname
                },
            ]
        )
        log.info("added tag to vpc: %s", keyname)
        vpc.modify_attribute(
            EnableDnsHostnames={
                'Value': True
            }
        )
        log.info("Enabled dns support")
    except Exception as error:
        log.info(str(error))
        return False
    igw = igw_create(client, vpcid)
    if igw == None:
        return vpc
    rt = rt_update(client, vpc, igw)
    if rt == None:
        return vpc
    subnet = subnet_create(client, vpc)
    if subnet == None:
        return vpc
    sg = sg_update(client, vpc, igw)
    if sg == None:
        return vpc

if not os.path.exists(credential_file):
    log.error("%s not found, please create it and add your key into it as the following format, multilines support if have" % credential_file)
    log.info(credential_file_format)
    sys.exit(1)
with open(credential_file,'r') as fh:
     keys_data = load(fh, Loader=Loader)
subnet_info = ''
ssh_key_info = ''
keyname = 'virtqe_s1'
try:
    ACCESS_KEY = keys_data[args.target][0]
    SECRET_KEY = keys_data[args.target][1]
    subscription_username = keys_data[args.target][2]
    subscription_password = keys_data[args.target][3]
except KeyError:
    log.info("%s credential not found", args.target)
    sys.exit(1)

default_regions = {"aws-china":"cn-northwest-1","aws":"us-west-2","aws-us-gov":"us-gov-west-1"}
region_list = None
region = default_regions[args.target]
try:
    client = boto3.client(
        'ec2',
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
        region_name=region,
    )
    region_list = client.describe_regions()['Regions']
    log.info("Successfully init %s credential in %s", args.target, region)
except ClientError as error:
    log.info("Failed to init %s credential in %s", args.target, region)
    log.info("Error: %s", error)
    sys.exit(1)
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
        vpc = vpc_create(client, region)
        subnets = client.describe_subnets()['Subnets']
        for subnet in subnets:
            if subnet['MapPublicIpOnLaunch']:
                vpc_id = subnet['VpcId']
                if vpc_check(vpc_id, region):
                    subnet_id = subnet['SubnetId']
                    break
        if subnet_id is None:
            log.info("Create failed in region %s", region)
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
