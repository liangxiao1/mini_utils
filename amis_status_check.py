#!/usr/bin/env python
'''
github : https://github.com/liangxiao1/mini_utils

This tool is for checking amis status in all regions and check whether they are supported for starting.

'''
import json
import os
import sys
if sys.version.startswith('2.'):
    import urllib2 as request
else:
    import urllib.request as request
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
import concurrent.futures

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
    'Dump image information and generate yamls for dva run!')
parser.add_argument('--task_url', dest='task_url', action='store',
                    help='image build task url', required=True)
parser.add_argument('--dir', dest='dir', action='store', default='/tmp',
                    help='save files to dir', required=False)
parser.add_argument('--tokenfile', dest='tokenfile', action='store', default="/etc/dva_keys.yaml",
                    help='credential file, default /etc/dva_keys.yaml', required=False)
parser.add_argument('--target', dest='target', action='store', default="aws",
                    help='optional, can be aws or aws-china or aws-us-gov', required=False)
parser.add_argument('-d', dest='is_debug', action='store_true', default=False,
                    help='Run in debug mode', required=False)
parser.add_argument('--profile', dest='profile', default='default', action='store',
                    help='option, profile name in aws credential config file, default is default', required=False)
args = parser.parse_args()
log = logging.getLogger(__name__)
if args.is_debug:
    logging.basicConfig(level=logging.DEBUG,
                        format='%(levelname)s:%(message)s')
else:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(message)s')

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

task_url = args.task_url.replace('push','task')
json_url = task_url + "/log/images.json?format=raw"
s = request.urlopen(json_url)
log.info('Get data from %s', s.geturl())
task_id = task_url.rstrip('/').split('/')[-1]
# print(s.read().decode('utf-8'))
json_file = '%s/images.json' % args.dir
if os.path.exists(json_file):
    os.unlink(json_file)
    log.debug('Removed exists %s', json_file)
with open(json_file, 'wb') as fh:
    fh.write(s.read())
log.info('Data saved to %s', json_file)
with open(json_file, 'r') as f:
    s = json.load(f)

version = s[1]['release']['version']
if ACCESS_KEY is None:
    session = boto3.session.Session(profile_name=args.profile, region_name='us-west-2')
    client = session.client('ec2', region_name='us-west-2')
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
with open(json_file, 'r') as fh:
    image_dict = json.load(fh)
# log.info(image_dict)
log.info("AMI Name | AMI ID | Region Name | Public | Bootable")
result_list = []
#for i in sorted(image_dict, key=itemgetter('region')):
def check_item(i):
    bootable = False
    if ACCESS_KEY is None:
        session = boto3.session.Session(profile_name=args.profile, region_name=i['region'])
        client = session.client('ec2', region_name=i['region'])
    else:
        client = boto3.client(
            'ec2',
            aws_access_key_id=ACCESS_KEY,
            aws_secret_access_key=SECRET_KEY,
            region_name=i['region'],
        )
    subnet_list = client.describe_subnets()['Subnets']
    if 'x86_64' in i['name']:
        instance_type = 'm5.large'
    else:
        instance_type = 'a1.large'
    if ACCESS_KEY is None:
        session = boto3.session.Session(profile_name=args.profile, region_name=i['region'])
        ec2 = session.resource('ec2', region_name=i['region'])
    else:
        ec2 = boto3.resource(
            'ec2',
            aws_access_key_id=ACCESS_KEY,
            aws_secret_access_key=SECRET_KEY,
            region_name=i['region'],
        )
    if i['region'] in regionids:
        regionids.remove(i['region'])
    bootable = check_boot(ec2_resource=ec2,instance_type=instance_type,ami=i['ami'],subnet=subnet_list[0]['SubnetId'],region=i['region'])
    if 'FalseNoENA' in str(bootable):
        log.info("Failed as ENA, 2nd check with d2.xlarge instance type without ENA.")
        instance_type = 'd2.xlarge'
        bootable = check_boot(ec2_resource=ec2,instance_type=instance_type,ami=i['ami'],subnet=subnet_list[0]['SubnetId'],region=i['region'])

    image = ec2.Image(i['ami'])
    if image.public:
        public_status = 'Public'
    else:
        public_status = 'Private'
    result_list.append([i['name'], i['ami'], i['region'], public_status, bootable])

with concurrent.futures.ThreadPoolExecutor(max_workers=150) as executor:
    check_all_regions_tasks = {executor.submit(check_item, item): item for item in sorted(image_dict, key=lambda r: (r['region']))}
    for r in concurrent.futures.as_completed(check_all_regions_tasks):
        x = check_all_regions_tasks[r]
        try:
            data = r.result()
        except Exception as exc:
            log.error("{} generated an exception: {}".format(r,exc))
        else:
            pass
result_list = sorted(result_list, key=lambda x:x[2])
for i in result_list:
    log.info("%s %s %s %s %s", i[0], i[1], i[2], i[3], i[4])
log.info("Found total AMIs: {}".format(len(result_list)))
if len(regionids) > 0:
    log.info('Below regions no ami uploaded: %s', regionids)