#!/usr/bin/env python
'''
github : https://github.com/liangxiao1/mini_utils

This tool is for searching amis status in all regions and check whether they are supported for starting.

'''
import json
import os
import copy
import sys
import logging
import argparse
import boto3
from botocore.exceptions import ClientError
from operator import itemgetter
from yaml import load, dump
try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper

#/etc/dva.yaml
credential_file = 'data/dva_key.yaml'

def check_boot(ec2_resource=None,instance_type=None,ami=None,subnet=None,region=None):
    try:
        vm = ec2_resource.create_instances(
            ImageId=ami,
            InstanceType=instance_type,
            SubnetId=subnet,
            MaxCount=1,
            MinCount=1,
            DryRun=True,
        )[0]
    except ClientError as err:
        if 'DryRunOperation' in str(err):
            log.debug("%s can create in %s", region, ami)
            bootable = True
        elif 'Unsupported' in str(err):
            bootable = 'Unsupported'
            log.debug("Can not create in %s %s: %s", region, bootable, err)
        elif 'Elastic Network Adapter' in str(err):
            bootable = 'FalseNoENA'
            log.debug("Can not create in %s %s: %s. Try d2.xlarge without ENA,", region, bootable,err)
        else:
            bootable = False
            logging.info("Can not create in %s %s: %s", region, bootable, err)

    return bootable

parser = argparse.ArgumentParser(
    'Search/Filter AMIs crossing region.')
parser.add_argument('--filter', dest='filter', action='store',
                    help='SAP, RHEL-8.3 or other keywords, default is search name', required=False)
parser.add_argument('--region', dest='region', action='store',
                    help='regions to check, split by comma, default is all', required=False)
parser.add_argument('--region_skip', dest='region_skip', action='store',
                    help='regions not check, split by comma, default is none', required=False)
parser.add_argument('--filter_json', dest='filter_json', action='store',
                    help='{"Name":"name","Values":["*SAP*"]};{"Name":"description","Values":["*Provided by Red Hat*"]}', required=False)
parser.add_argument('--dir', dest='dir', action='store', default='/tmp',
                    help='save files to dir', required=False)
parser.add_argument('--tokenfile', dest='tokenfile', action='store', default="data/dva_key.yaml",
                    help='optional, credential file, default data/dva_key.yaml', required=False)
parser.add_argument('--target', dest='target', action='store', default="aws",
                    help='optional, can be aws or aws-china or aws-us-gov', required=False)
parser.add_argument('-d', dest='is_debug', action='store_true', default=False,
                    help='Run in debug mode', required=False)
parser.add_argument('-c', dest='is_check', action='store_true', default=False,
                    help='Check whether AMI bootable', required=False)
args = parser.parse_args()
log = logging.getLogger(__name__)
if args.is_debug:
    logging.basicConfig(level=logging.DEBUG,
                        format='%(levelname)s:%(message)s')
else:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(message)s')
if args.filter_json == None and args.filter == None:
    log.info("Please specify filter_json or filter in cmd")
    sys.exit(1)
credential_file = args.tokenfile
credential_file_format = "aws-us-gov: ['ec2_access_key','ec2_secret_key','subscription_username','subscription_password']"
if not os.path.exists(credential_file):
    log.error("%s not found, please create it and add your key into it as the following format, multilines support if have" % credential_file)
    log.info(credential_file_format)
else:
    with open(credential_file,'r') as fh:
         keys_data = load(fh, Loader=Loader)
    try:
        ACCESS_KEY = keys_data[args.target][0]
        SECRET_KEY = keys_data[args.target][1]
    except KeyError:
        log.info("%s credential cfg file read error, try use default", args.target)
        ACCESS_KEY = None
        SECRET_KEY = None

if ACCESS_KEY is None:
    client = boto3.client('ec2',region_name='us-west-2')
else:
    client = boto3.client(
        'ec2',
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
        region_name='us-west-2',
    )
region_list = client.describe_regions()['Regions']
regionids = []
for region in region_list:
    regionids.append(region['RegionName'])
regionids_tmp = copy.deepcopy(regionids)
# log.info(image_dict)
if args.is_check:
    log.info("AMI Name | AMI ID | Region Name | Public | Bootable")
else:
    log.info("AMI Name | AMI ID | Region Name | Public")
#for i in sorted(image_dict, key=itemgetter('region')):
for region in regionids:
    if args.region is not None:
        if region not in args.region.split(","):
            continue
    if args.region_skip is not None:
        if region in args.region_skip.split(","):
            continue
    bootable = False
    if ACCESS_KEY is None:
        client = boto3.client('ec2', region_name=region)
    else:
        client = boto3.client(
            'ec2',
            aws_access_key_id=ACCESS_KEY,
            aws_secret_access_key=SECRET_KEY,
            region_name=region,
        )
    if args.filter_json is not None:
        filters = []
        for filter in args.filter_json.split(';'):
            filters.append(json.loads(filter))
        #log.info(filters)

        images_list = client.describe_images(
                Filters=filters,
            )
    else:    
        images_list = client.describe_images(
                Filters=[
                {
                    'Name': 'name',
                    'Values': [
                        '*{}*'.format(args.filter),
                    ]
                },
            ],
            )
    subnet_list = client.describe_subnets()['Subnets']
    if ACCESS_KEY is None:
        ec2 = boto3.resource('ec2', region_name=region)
    else:
        ec2 = boto3.resource(
            'ec2',
            aws_access_key_id=ACCESS_KEY,
            aws_secret_access_key=SECRET_KEY,
            region_name=region,
        )
    if len(images_list['Images']) > 0:
        regionids_tmp.remove(region)
    for img in images_list['Images']:
        #log.info("{} {}".format(img['ImageId'], img['Name']))
        if 'x86_64' in img['Name']:
            instance_type = 'm5.large'
        else:
            instance_type = 'a1.large'
        if args.is_check:
            bootable = check_boot(ec2_resource=ec2,instance_type=instance_type,ami=img['ImageId'],subnet=subnet_list[0]['SubnetId'],region=region)
            if 'FalseNoENA' in str(bootable):
                log.info("Failed as ENA, 2nd check with d2.xlarge instance type without ENA.")
                instance_type = 'd2.xlarge'
                bootable = check_boot(ec2_resource=ec2,instance_type=instance_type,ami=img['ImageId'],subnet=subnet_list[0]['SubnetId'],region=region)
        if img['Public']:
            public_status = 'Public'
        else:
            public_status = 'Private'
        if args.is_check:
            log.info("%s %s %s %s %s", img['Name'], img['ImageId'], region, public_status, bootable)
        else:
            log.info("%s %s %s %s", img['Name'], img['ImageId'], region, public_status)
if len(regionids_tmp) > 0:
    log.info('Below regions no ami found: %s', regionids_tmp)
