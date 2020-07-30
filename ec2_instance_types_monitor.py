#!/usr/bin/env python
'''
ec2 instance type: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/instance-types.html
github : https://github.com/liangxiao1/mini_utils

This tool is for tracking new instance types automatically.

'''
from __future__ import print_function
import logging
import argparse
import os
import sys
import re
import boto3
import datetime
import json

LOG_FORMAT = "%(levelname)s:%(message)s"
DEFAULT_REGION = 'us-west-2'
DATA_FILE = 'data/instance_types.json'
NOWDATE = str(datetime.datetime.now().date())
instance_types_dict = {"InstanceTypes":[]}
def main():
    client = boto3.client('ec2', region_name=DEFAULT_REGION)
    tmp_dict_all = client.describe_instance_types()
    loop = 0
    while True:
        LOG.info('Get all instance types loop %s', loop)
        loop = loop + 1
        instance_types_dict["InstanceTypes"].extend(tmp_dict_all['InstanceTypes'])
        try:
            nexttoken = tmp_dict_all['NextToken']
        except KeyError as err:
            LOG.info("Get all instance types done, length %s", len(instance_types_dict["InstanceTypes"]))
            break
        if nexttoken == None:
            LOG.info("Get all instance types done, length %s", len(instance_types_dict["InstanceTypes"]))
            break
        tmp_dict_all = client.describe_instance_types(NextToken=nexttoken)
    instance_types_dict_tmp = {"InstanceTypes":[]}
    if not os.path.exists(DATA_FILE):
        LOG.info("{} not found, init it all instance types with today's date".format(DATA_FILE))
        for instance in instance_types_dict["InstanceTypes"]:
            instance['Initdate'] = NOWDATE
            instance_types_dict_tmp["InstanceTypes"].append(instance)
            LOG.info("Init {} date {}".format(instance["InstanceType"], NOWDATE))
        with open(DATA_FILE, 'w') as fh:
            json.dump(instance_types_dict_tmp,fh,indent=4)
    with open(DATA_FILE, 'r') as fh:
        instance_types_stored = json.load(fh)
    tmp_new_instance = []
    for instance in instance_types_dict["InstanceTypes"]:
        is_exist = False
        for instance_stored in instance_types_stored["InstanceTypes"]:
            if instance["InstanceType"] == instance_stored["InstanceType"]:
                LOG.info("{} already exists before".format(instance["InstanceType"]))
                is_exist = True
                break
        if not is_exist:
            instance['Initdate'] = NOWDATE
            tmp_new_instance.append(instance)
            LOG.info("Init new {} date {}".format(instance["InstanceType"],NOWDATE))
    #LOG.info("New instance types: {}".format(tmp_new_instance))
    instance_types_stored["InstanceTypes"].extend(tmp_new_instance)
    with open(DATA_FILE, 'w') as fh:
        json.dump(instance_types_stored,fh,indent=4)
    #LOG.info(json.dumps(instance_types_stored, indent=4))
    new_instance_types_x86 = []
    new_instance_types_aarch64 = []
    for instance_stored in instance_types_stored["InstanceTypes"]:
        if instance_stored['Initdate'] == NOWDATE:
            if 'arm' in instance_stored['ProcessorInfo']['SupportedArchitectures'][0]:
                new_instance_types_aarch64.append(instance_stored["InstanceType"])
            else:
                new_instance_types_x86.append(instance_stored["InstanceType"])
    if len(new_instance_types_aarch64) == 0 and len(new_instance_types_x86) == 0:
        LOG.info("No new instance type found!")
        sys.exit(0)
    if os.path.exists(DEFAULT_OUTPUT):
        os.unlink(DEFAULT_OUTPUT)
    if len(new_instance_types_aarch64) > 0:
        LOG.info("new_instance_types_aarch64: {}".format(','.join(new_instance_types_aarch64)))
        with open(DEFAULT_OUTPUT, 'a') as fh:
            fh.write("INSTANCE_TYPES_ARM: {}\n".format(','.join(new_instance_types_aarch64)))
    else:
        with open(DEFAULT_OUTPUT, 'a') as fh:
            fh.write("INSTANCE_TYPES_ARM: None\n")
    if len(new_instance_types_x86) > 0:
        LOG.info("new_instance_types_x86: {}\n".format(','.join(new_instance_types_x86)))
        with open(DEFAULT_OUTPUT, 'a') as fh:
            fh.write("INSTANCE_TYPES_X86: {}\n".format(','.join(new_instance_types_x86)))
    else:
        with open(DEFAULT_OUTPUT, 'a') as fh:
            fh.write("INSTANCE_TYPES_X86: None\n")
    with open(DEFAULT_OUTPUT, 'a') as fh:
            fh.write("INSTANCE_DATE: {}\n".format(NOWDATE))
    LOG.info("Output saved to {}".format(DEFAULT_OUTPUT))
    #sys.stdout.write(','.join(new_instance_types))

if __name__ == '__main__':
    ARG_PARSER = argparse.ArgumentParser(
        description="Check new instance types \
            eg.  python ec2_instance_types_monitor.py --region us-west-2")
    ARG_PARSER.add_argument('-d', dest='is_debug', action='store_true',
                            help='run in debug mode', required=False)
    ARG_PARSER.add_argument('--region', dest='region', action='store', default='us-west-2',
                            help='region name, default is us-west-2',
                            required=False)
    ARG_PARSER.add_argument('-o', dest='output', action='store', default='/tmp/newinstance.log',
                            help='output file, default is /tmp/newinstance.log',
                            required=False)
    ARGS = ARG_PARSER.parse_args()
    LOG = logging.getLogger(__name__)
    if ARGS.is_debug:
        logging.basicConfig(level=logging.DEBUG, format=LOG_FORMAT)
    else:
        logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    DEFAULT_REGION = ARGS.region
    DEFAULT_OUTPUT = ARGS.output
    main()