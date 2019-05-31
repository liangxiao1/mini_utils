#!/usr/bin/env python
'''
github : https://github.com/liangxiao1/mini_utils
This tool is for dumping image information from image task json result and generate yamls for dva run

'''

import json
import string
import os
import urllib.request as request
import logging
import argparse

parser = argparse.ArgumentParser(
    'Dump image information and generate yamls for dva run!')
parser.add_argument('--image_url', dest='image_url', action='store',
                    help='image build task json download url', required=True)
parser.add_argument('--platform', dest='platform', action='store',
                    help='RHEL,BETA,ATOMIC', required=True)
parser.add_argument('--product', dest='product', action='store',
                    help='CLOUD,JPEAP,JBEWS,GRID,SAP,ATOMIC', required=True)
parser.add_argument('--version', dest='version', action='store',
                    help='6.10,7.6,7.7,8.0,8.1...', required=True)
parser.add_argument('--dir', dest='dir', action='store', default='/tmp',
                    help='save files to dir', required=False)
parser.add_argument('-d', dest='is_debug', action='store_true', default=False,
                    help='Run in debug mode', required=False)
args = parser.parse_args()
log = logging.getLogger(__name__)
if args.is_debug:
    logging.basicConfig(level=logging.DEBUG,
                        format='%(levelname)s:%(message)s')
url = args.image_url
s = request.urlopen(url)
log.info('Get data from %s' % s.geturl())
# print(s.read().decode('utf-8'))
json_file = '%s/images.json' % args.dir
if os.path.exists(json_file):
    os.unlink(json_file)
    log.debug('Removed exists %s' % json_file)
with open(json_file, 'b+w') as fh:
    fh.write(s.read())
log.info('Data saved to %s' % json_file)
if not str(args.version).startswith('6'):
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
# aws key is not allow to many read in paralle, so split hourly and access
target_hourly_yaml = '%s/test_all_hourly.yaml' % args.dir
target_access_yaml = '%s/test_all_access.yaml' % args.dir
if os.path.exists(target_hourly_yaml):
    os.unlink(target_hourly_yaml)
    log.debug('Removed exists %s' % target_hourly_yaml)
if os.path.exists(target_access_yaml):
    os.unlink(target_access_yaml)
    log.debug('Removed exists %s' % target_access_yaml)
for i in image_dict:
    if 'Hourly' in i['name']:
        itype = 'hourly'
    else:
        itype = 'access'
    if 'sa-east-1' in i['region'] and 'RHEL-6' in i['name']:
        s = cfg_tmp_sa_east_1.substitute(ami_id=i['ami'], region=i['region'], itype=itype,
                                         platform=args.platform, product=args.product, version=args.version)
    elif 'arm64' in i['name']:
        s = cfg_tmp_arm.substitute(ami_id=i['ami'], region=i['region'], itype=itype,
                                   platform=args.platform, product=args.product, version=args.version)
    else:
        s = cfg_tmp.substitute(ami_id=i['ami'], region=i['region'], itype=itype,
                               platform=args.platform, product=args.product, version=args.version)
    if 'Hourly' in i['name']:
        with open(target_hourly_yaml, 'a') as fh:
            fh.write(s)
    else:
        with open(target_access_yaml, 'a') as fh:
            fh.write(s)
if os.path.exists(target_access_yaml):
    log.info("Data saved to %s" % target_access_yaml)
if os.path.exists(target_hourly_yaml):
    log.info("Data saved to %s" % target_hourly_yaml)
