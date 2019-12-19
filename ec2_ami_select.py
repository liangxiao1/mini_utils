#!/usr/bin/env python
'''
kernel mapping source : https://access.redhat.com/articles/3078
github : https://github.com/liangxiao1/mini_utils

This tool is checking RHEL version by giving kernel version or compose id.
The output is ami-id.

branch_map.yaml example:
RHEL-7.7:
    kernel: 3.10.0-1062
    ec2_ami_x86_64: ami-xxxxxx

'''
from __future__ import print_function
import string
import logging
import argparse
import os
import sys
import json
import random
import signal
import re
from collections import OrderedDict

import pdb

try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper
from yaml import load, dump

def sig_handler(signum, frame):
    logging.debug('Got signal %s, exit!', signum)
    sys.exit(0)

if '__main__' == __name__:
    parser = argparse.ArgumentParser(
    description="Check RHEL version by giving kernel version or compose id. \
    eg.  python check_rhel_version.py -k $kernel -f $datafile")
    parser.add_argument('-d', dest='is_debug', action='store_true',
                    help='run in debug mode', required=False)
    parser.add_argument('-k', dest='kernel', action='store', default=None,
                    help='kernel version, eg. 4.18.0-147 or kernel-4.18.0-80.14.1.el8_0', required=False)
    parser.add_argument('-c', dest='compose', action='store', default=None,
                    help='compose id, eg. RHEL-8.1.0-20191204.0', required=False)
    parser.add_argument('-f', dest='datafile', action='store', default=None,
                    help='branch map data file', required=True)
    parser.add_argument('-s', dest='select_filed', action='store', default=None,
                    help='ami_id|branch_name to show only in output, ouput both by default', required=False)
    parser.add_argument('-p', dest='arch', action='store', default=None,
                    help='aarch64|x86_64', required=False)

    args = parser.parse_args()
    log = logging.getLogger(__name__)
    FORMAT = "%(levelname)s:FUNC-%(funcName)s:%(message)s"
    if args.is_debug:
        logging.basicConfig(level=logging.DEBUG, format=FORMAT)
    else:
        logging.basicConfig(level=logging.INFO, format=FORMAT)
    branch_name = None
    ami_id = None
    final_output = OrderedDict()
    map_file = args.datafile
    if not os.path.exists(map_file):
        log.error("mapping file not found %s" % map_file)
        sys.exit(1)
    with open(map_file,'r') as fh:
        keys_data = load(fh, Loader=Loader)
    log.debug(keys_data)
    if args.kernel is not None:
        log.debug("Check by kernel version......")
        kernel_regx = "[0-9]{1,5}.[0-9]{1,5}.[0-9]{1,5}-[0-9]{1,5}"
        kernel = re.findall(kernel_regx,args.kernel)[0]
        log.debug('Your kernel version:%s' % kernel)
        for branch in keys_data.keys():
            if keys_data[branch]['kernel'] == kernel:
                branch_name = branch
                log.debug("detcted branch_name: %s" % branch_name)
                break
        if branch_name is None and kernel.startswith('3.'):
            branch_name = 'RHEL-7-latest'
        elif branch_name is None:
            branch_name = 'RHEL-8-latest'

        if args.arch == 'aarch64':
            ami_id = keys_data[branch_name]['ec2_ami_aarch64']
        else:
            ami_id = keys_data[branch_name]['ec2_ami_x86_64']

        log.debug('branch_namee: %s ami_id: %s' % (branch_name, ami_id))
    if args.compose is not None:
        branch_regx = "RHEL-[0-9]{1,2}.[0-9]{1,2}"
        branch_name = re.findall(branch_regx,args.compose)[0]
        log.debug('Your branch_name:%s' % branch_name)
        try:
            if args.arch == 'aarch64':
                ami_id = keys_data[branch_name]['ec2_ami_aarch64']
            else:
                ami_id = keys_data[branch_name]['ec2_ami_x86_64']
        except Exception as err:
            if branch_name.startswith('RHEL-7'):
                branch_name = 'RHEL-7-latest'
            else:
                branch_name = 'RHEL-8-latest'
            if args.arch == 'aarch64':
                ami_id = keys_data[branch_name]['ec2_ami_aarch64']
            else:
                ami_id = keys_data[branch_name]['ec2_ami_x86_64']
        log.debug('branch_name: %s ami_id: %s' % (branch_name, ami_id))
    if args.select_filed == "branch_name":
        #print(branch_name)
        sys.stdout.write(branch_name)
    elif args.select_filed == "ami_id":
        #print(ami_id)
        sys.stdout.write(ami_id)
    else:
        log.info('branch_name: %s ami_id: %s' % (branch_name, ami_id))

