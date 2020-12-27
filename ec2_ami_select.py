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
import logging
import argparse
import os
import sys
import re

try:
    from yaml import CLoader as Loader
    #from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader
    #from yaml import Loader, Dumper
from yaml import load

LOG_FORMAT = "%(levelname)s:FUNC-%(funcName)s:%(message)s"
# pylint: disable=W1401
BRANCH_REGEX = "RHEL-\d{1,2}.\d{1,2}"
# pylint: disable=W1401
KERNEL_REGEX = "\d{1,5}.\d{1,5}.\d{1,5}-\d{1,5}"


def get_by_branch(branch_name):
    '''
    get ami_id by parse branchname
    '''
    try:
        if ARGS.arch == 'aarch64':
            ami_id = KEYS_DATA[branch_name]['ec2_ami_aarch64']
        else:
            ami_id = KEYS_DATA[branch_name]['ec2_ami_x86_64']
        LOG.debug('branch_name: %s ami_id: %s', branch_name, ami_id)
        return branch_name, ami_id
    except KeyError:
        LOG.debug('branch_name: {} not found'.format(branch_name))
        guess_list = []
        for i in KEYS_DATA.keys():
            if branch_name.upper() in i.upper():
                guess_list.append(i)
        if len(guess_list) > 0:
            LOG.debug('Try:{}?'.format(guess_list))

        sys.exit(1)

def guess_branch(s=None):
    '''
    check string and guess branch name
    '''
    if s.startswith('RHEL-7'):
        branch_name = 'RHEL-7-latest'
    elif s.startswith('RHEL-8'):
        branch_name = 'RHEL-8-latest'
    elif s.startswith('RHEL-9'):
        branch_name = 'RHEL-9-latest'
    elif s.startswith('RHEL-10'):
        branch_name = 'RHEL-10-latest'
    elif s.startswith('CentOS-Stream-8'):
        branch_name = 'CentOS-Stream-8'
    elif s.startswith('CentOS-Stream-9'):
        branch_name = 'CentOS-Stream-9'
    else:
        branch_name = 'RHEL-latest'
    LOG.debug('Your branch_name:%s', branch_name)
    return branch_name

def get_by_compose():
    '''
    get ami_id by parse compose id
    '''
    try:
        branch_name = re.findall(BRANCH_REGEX, ARGS.compose)[0]
    except IndexError:
        branch_name = guess_branch(ARGS.compose)
    try:
        _, ami_id = get_by_branch(branch_name)
    except Exception as err:
        branch_name = guess_branch(branch_name)
        _, ami_id = get_by_branch(branch_name)
    return branch_name, ami_id

def get_by_kernel():
    '''
    get ami_id by parse kernel string
    '''
    LOG.debug("Check by kernel version......")
    branch_name = None
    kernel = re.findall(KERNEL_REGEX, ARGS.kernel)[0]
    LOG.debug('Your kernel version:%s', kernel)
    for branch in KEYS_DATA.keys():
        if KEYS_DATA[branch]['kernel'] == kernel:
            branch_name = branch
            LOG.debug('match:%s success',  KEYS_DATA[branch]['kernel'])
            LOG.debug("detcted branch_name: %s", branch_name)
            break
        else:
            LOG.debug('match:%s false',  KEYS_DATA[branch]['kernel'])
    if branch_name is None:
        if kernel.startswith('3.'):
            branch_name = 'RHEL-7-latest'
        elif kernel.startswith('4.'):
            branch_name = 'RHEL-8-latest'
        else:
            branch_name = 'RHEL-latest'
    _, ami_id = get_by_branch(branch_name)
    return branch_name, ami_id

if __name__ == '__main__':
    ARG_PARSER = argparse.ArgumentParser(
        description="Check RHEL version by giving kernel version or compose id. \
            eg.  python ec2_ami_select.py -k $kernel -f $datafile")
    ARG_PARSER.add_argument('-d', dest='is_debug', action='store_true',
                            help='run in debug mode', required=False)
    ARG_PARSER.add_argument('-k', dest='kernel', action='store', default=None,
                            help='kernel version, eg. 4.18.0-147 or kernel-4.18.0-80.14.1.el8_0',
                            required=False)
    ARG_PARSER.add_argument('-c', dest='compose', action='store', default=None,
                            help='compose id, eg. RHEL-8.1.0-20191204.0', required=False)
    ARG_PARSER.add_argument('-b', dest='branch_name', action='store', default=None,
                            help='branch_name, eg. RHEL-8.1,CentOS-Stream-8', required=False)
    ARG_PARSER.add_argument('-f', dest='datafile', action='store', default=None,
                            help='branch map data file', required=True)
    ARG_PARSER.add_argument('-s', dest='select_filed', action='store', default=None,
                            help='ami_id|branch_name to show only in output, ouput both by default',
                            required=False)
    ARG_PARSER.add_argument('-p', dest='arch', action='store', default=None,
                            help='aarch64|x86_64', required=False)

    ARGS = ARG_PARSER.parse_args()
    LOG = logging.getLogger(__name__)

    if ARGS.is_debug:
        logging.basicConfig(level=logging.DEBUG, format=LOG_FORMAT)
    else:
        logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)

    MAP_FILE = ARGS.datafile
    if not os.path.exists(MAP_FILE):
        LOG.error("mapping file not found %s", MAP_FILE)
        sys.exit(1)
    with open(MAP_FILE, 'r') as fh:
        KEYS_DATA = load(fh, Loader=Loader)
    LOG.debug(KEYS_DATA)
    if ARGS.compose:
        BRANCH_NAME, AMI_ID = get_by_compose()
    if ARGS.kernel:
        BRANCH_NAME, AMI_ID = get_by_kernel()
    if ARGS.branch_name:
        BRANCH_NAME, AMI_ID = get_by_branch(ARGS.branch_name)

    if ARGS.select_filed == "branch_name":
        #print(branch_name)
        sys.stdout.write(BRANCH_NAME)
    elif ARGS.select_filed == "ami_id":
        #print(ami_id)
        sys.stdout.write(AMI_ID)
    else:
        LOG.info('branch_name: %s ami_id: %s', BRANCH_NAME, AMI_ID)
