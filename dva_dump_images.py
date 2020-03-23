#!/usr/bin/env python

'''
github : https://github.com/liangxiao1/mini_utils
This tool is for dumping image information from image task json result and generate yamls for dva run

'''

import json
import string
import os
import sys
if sys.version.startswith('2.7'):
    print('Only support run in python3')
    sys.exit(1)
import urllib.request as request
import logging
import argparse

parser = argparse.ArgumentParser(
    'Dump image information and generate yamls for dva run!')
parser.add_argument('--task_url', dest='task_url', action='store',
                    help='image build task url', required=True)
#parser.add_argument('--platform', dest='platform', action='store',
#                    help='RHEL,BETA,ATOMIC', required=True)
#parser.add_argument('--product', dest='product', action='store',
#                    help='CLOUD,JPEAP,JBEWS,GRID,SAP,ATOMIC', required=True)
parser.add_argument('--dir', dest='dir', action='store', default='/tmp',
                    help='save files to dir', required=False)
parser.add_argument('-d', dest='is_debug', action='store_true', default=False,
                    help='Run in debug mode', required=False)
args = parser.parse_args()
log = logging.getLogger(__name__)
if args.is_debug:
    logging.basicConfig(level=logging.DEBUG,
                        format='%(levelname)s:%(message)s')
else:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(message)s')
task_url = args.task_url.replace('push','task')
json_url = task_url + "/log/images.json?format=raw"
log.info('Get data from %s' % json_url)
s = request.urlopen(json_url)
log.info('Got data from %s' % s.geturl())
task_id = task_url.rstrip('/').split('/')[-1]
# print(s.read().decode('utf-8'))
json_file = '%s/images.json' % args.dir
if os.path.exists(json_file):
    os.unlink(json_file)
    log.debug('Removed exists %s' % json_file)
with open(json_file, 'b+w') as fh:
    fh.write(s.read())
log.info('Data saved to %s' % json_file)
with open(json_file,'r') as f:
    s = json.load(f)
if 'ATOMIC' in s[1]['name'].upper():
    log.info("It is atomic image")
    product = 'ATOMIC'
    platform = 'ATOMIC'
elif 'BETA' in s[1]['name'].upper():
    log.info("It is rhel beta image")
    product = 'CLOUD'
    platform = 'BETA'
else:
    log.info("It is rhel image")
    product = 'CLOUD'
    platform = 'RHEL'

version = s[1]['release']['version']
if 'ATOMIC' in version.upper():
    version = version.replace('Atomic_','')
if not str(version).startswith('6') and not str(version).startswith('7.2') and not str(version).startswith('7.3'):
    cfg_tmp = string.Template('''- ami: $ami_id
  arch:
    - arch: x86_64
      bmap:
      - {delete_on_termination: true, name: /dev/sda1, size: '15'}
      - {ephemeral_name: ephemeral0, name: /dev/sdf}
      cpu: '4'
      cloudhwname: m5.xlarge
      memory: '16000000'
      virtualization: hvm
  itype: $itype
  platform: $platform
  product: $product
  region: $region
  version: '$version'
''')
else:
    # run with d2.xlarge as rhel6 has no ena support
    cfg_tmp = string.Template('''- ami: $ami_id
  arch:
    - arch: x86_64
      bmap:
      - {delete_on_termination: true, name: /dev/sda1, size: '15'}
      - {ephemeral_name: ephemeral0, name: /dev/sdf}
      cpu: '4'
      cloudhwname: d2.xlarge
      memory: '30500000'
      virtualization: hvm
  itype: $itype
  platform: $platform
  product: $product
  region: $region
  version: '$version'
''')
# this region does not have d2 instance for rhel6 test
cfg_tmp_sa_east_1 = string.Template('''- ami: $ami_id
  arch:
    - arch: x86_64
      cpu: '2'
      cloudhwname: t2.large
      memory: '8000000'
      virtualization: hvm
  itype: $itype
  platform: $platform
  product: $product
  region: $region
  version: '$version'
''')

cfg_tmp_arm = string.Template('''- ami: $ami_id
  arch:
    - arch: arm64
      cpu: '4'
      cloudhwname: a1.xlarge
      memory: '8000000'
      virtualization: hvm
  itype: $itype
  platform: $platform
  product: $product
  region: $region
  version: '$version'
''')

with open(json_file, 'r') as fh:
    image_dict = json.load(fh)
# log.info(image_dict)
for i in image_dict:
    log.info("%s %s %s" % (i['name'], i['ami'], i['region']))
# aws key is not allow too many read in paralle, so split it by 11 per file
target_hourly_yaml = '%s/test_all_hourly.yaml' % args.dir
target_access_yaml = '%s/test_all_access.yaml' % args.dir

for i in range(10):
    target_yaml = '%s/task_%s_test_%s.yaml' % (args.dir,task_id,i)
    if os.path.exists(target_yaml):
        os.unlink(target_yaml)
        log.debug('Removed exists %s' % target_yaml)

count = 1
file_idx = 1
for i in image_dict:
    target_yaml = '%s/task_%s_test_%s.yaml' % (args.dir,task_id,file_idx)
    if 'Hourly' in i['name']:
        itype = 'hourly'
    else:
        itype = 'access'
    if 'sa-east-1' in i['region'] and 'RHEL-6' in i['name']:
        s = cfg_tmp_sa_east_1.substitute(ami_id=i['ami'], region=i['region'], itype=itype,
                                         platform=platform, product=product, version=version)
    elif 'arm64' in i['name']:
        s = cfg_tmp_arm.substitute(ami_id=i['ami'], region=i['region'], itype=itype,
                                   platform=platform, product=product, version=version)
    else:
        s = cfg_tmp.substitute(ami_id=i['ami'], region=i['region'], itype=itype,
                               platform=platform, product=product, version=version)
    with open(target_yaml, 'a') as fh:
            fh.write(s)
            log.info("Save %s to %s" % (i['ami'], target_yaml))
    count = count + 1
    if count % 11 == 0:
        file_idx = file_idx + 1
