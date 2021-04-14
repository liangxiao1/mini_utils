#!/usr/bin/env python
'''
now: describe-instance-types by latest awscli
old: ec2 data source : https://www.ec2instances.info/?region=us-gov-west-1

github : https://github.com/liangxiao1/mini_utils

This tool is using for dump yaml file from ec2 data source and check whether 
the instance can run in this region.

yaml file example:
instance_types: !mux
    i3.large:
        instance_type: i3.large
        cpu: 2
        memory: 15.25 
        disks: 2
        net_perf : 10
        ipv6: True

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

import pdb


def sig_handler(signum, frame):
    logging.info('Got signal %s, exit!', signum)
    sys.exit(0)

def deal_instancetype(x):
    if x.count('.') > 0:
        return x
    return x+'.'


def instance_get():
    instance_types_list = []
    session = boto3.session.Session(profile_name=args.profile, region_name=args.region)
    client = session.client('ec2', region_name=args.region)
    filters = []
    if args.is_all:
        filters = []
        log.info("Filter all generation instance types")
    else:
        filters = [
            {
                'Name': 'current-generation',
                'Values': [
                    'true',
                ]
            },
        ]
        log.info("Filter only current generation instance types")
    if args.max_mem is not None:
        filters.append({
                'Name': 'memory-info.size-in-mib',
                'Values': [
                    str(int(args.max_mem)*1024),
                ]
            })
    tmp_dict_all = client.describe_instance_types(Filters=filters)
    #tmp_dict_all = client.describe_instance_types()
    i = 0
    while True:
        log.info('Get loop %s', i)
        i = i + 1
        tmp_dict = tmp_dict_all['InstanceTypes']
        instance_types_list.extend(tmp_dict)
        try:
            nexttoken = tmp_dict_all['NextToken']
        except KeyError as err:
            log.info("Get instance types done, length %s", len(instance_types_list))
            break
        if nexttoken == None:
            log.info("Get instance types done, length %s", len(instance_types_list))
            break
        tmp_dict_all = client.describe_instance_types(NextToken=nexttoken, Filters=filters)
    tmp_instance_types_list = []
    if args.is_x86 and args.is_arm:
        log.info("Only one arch can be specified")
        sys.exit(1)
    if args.is_x86:
        log.info("Filter only x86 instance types")
        tmp_instance_types_list = [x for x in instance_types_list if x["ProcessorInfo"]["SupportedArchitectures"][0] != "arm64"]
    if args.is_arm:
        log.info("Filter only arm instance types")
        tmp_instance_types_list = [x for x in instance_types_list if x["ProcessorInfo"]["SupportedArchitectures"][0] == "arm64"]
    if args.is_x86 or args.is_arm:
        instance_types_list = tmp_instance_types_list

    #log.info(instance_types_list)
    instance_list = [ x['InstanceType'] for x in instance_types_list ]
    instance_list.sort()
    log.info("The available instances: {}".format(instance_list))

    instance_str = 'instance_types: !mux\n'
    instance_template = string.Template('''    $instance_type:
        instance_type: $instance_type
        cpu: $cpu_count
        memory: $mem_size
        disks: $disk_count
        net_perf : $net_perf
        ipv6: $ipv6_support
''')

    is_write = False
    pick_list = []

    if args.random_pick:
        log.info("Randomly pick instance....")
        i = 0
        a = 0

        for x in instance_list:
            if i == len(instance_list)-1:
                pick_list.append(instance_list[random.randint(a, i)])
            elif str(x).split(r'.')[0] != instance_list[i+1].split(r'.')[0]:
                pick_list.append(instance_list[random.randint(a, i)])
                a = i+1
            i += 1
    elif args.instances is not None:
        instances_type = map(
            deal_instancetype, args.instances.split(','))
        log.info("instance type specified:%s", instances_type)
        for x in instances_type:
            pick_list.extend(filter(lambda y: y.startswith(x), instance_list))
        log.info('instance type matched: %s', pick_list)
    elif args.is_all:
        log.info("Pick all instance types")
        pick_list = instance_list
    if len(pick_list) == 0:
        log.info("Please specify instance type or random pick or all.")
        sys.exit(1)

    write_count = 0
    wroten_count = 0
    if args.split_num is not None:
        max_eachfile = args.split_num
    if args.cfg_name is None:
        cfg_file = "ec2_instance_types.yaml"
    else:
        cfg_file = args.cfg_name
    cfg_file_name = os.path.basename(cfg_file)
    cfg_file_dir = os.path.dirname(cfg_file)
    cfg_file_sum = 'sum_'+cfg_file_name
    cfg_file_sum = os.path.join(cfg_file_dir, cfg_file_sum)
    if os.path.exists(cfg_file_sum):
        os.unlink(cfg_file_sum)
    for instance in pick_list:
        if args.skip_instance is not None:
            log.debug(args.skip_instance.split(','))
            for i in args.skip_instance.split(','):
                if instance.startswith(i):
                    log.info("skipped %s as skip_instance specified" %i)
                    pick_list.remove(instance)
    for instance in pick_list:
        if args.check_live:
            vm = EC2VM()
            vm.instance_type = instance
            if not vm.create():
                pick_list.remove(instance)
                log.info("skipped %s as not bootable" %instance)
    for i in range(10):
        for instance in pick_list:
            if 'nano' in instance:
                log.info("RHEL not support run as nano instance,skip!")
                pick_list.remove(instance)
        if args.num_instances is not None and len(pick_list) <= int(args.num_instances):
            log.info("pick_list {} is less than wanted {}".format(len(pick_list), args.num_instances))
        if args.num_instances is not None and len(pick_list) >= int(args.num_instances):
            log.info("Select max %s instances" % args.num_instances)
            pick_list = random.sample(pick_list, int(args.num_instances))
        if len(pick_list) == 0:
            log.info("No instance found, retry...")
            continue
        else:
            break
    if len(pick_list) == 0:
        log.info("No instance found, exit")
        sys.exit(1)
    for instance in pick_list:
        if args.skip_instance is not None:
            skip_y = False
            log.debug(args.skip_instance.split(','))
            for i in args.skip_instance.split(','):
                if instance.startswith(i):
                    log.info("skipped %s as skip_instance specified" %i)
                    skip_y = True
                    continue
            if skip_y:
                continue
        log.info("%s selected", instance)
        is_write = True
        disk_count = 1

        if is_write:
            for i in instance_types_list:
                if i['InstanceType'] == instance:
                    break
            instance = i
            if instance['InstanceStorageSupported']:
                disk_count = instance["InstanceStorageInfo"]["Disks"][0]["Count"] + 1
            else:
                disk_count = 1
            net_str = instance["NetworkInfo"]["NetworkPerformance"]
            if 'Moderate' in net_str:
                net_perf = 0
            elif '100 Gigabit' in net_str:
                net_perf = 100
            elif '25 Gigabit' in net_str:
                net_perf = 25
            elif '10 Gigabit' in net_str:
                net_perf = 10
            elif '5 Gigabit' in net_str:
                net_perf = 5
            elif 'Gigabit' in net_str:
                net_perf = net_str.split(' ')[0]
            else:
                net_perf = 0
            ipv6_support = instance["NetworkInfo"]["Ipv6Supported"]

            vcpu_str = instance["VCpuInfo"]["DefaultVCpus"]
            instance_str += instance_template.substitute(
                instance_type=instance["InstanceType"], cpu_count=vcpu_str, mem_size=int(instance["MemoryInfo"]["SizeInMiB"])/1024, disk_count=disk_count, net_perf=net_perf, ipv6_support=ipv6_support)
            write_count += 1
            with open(cfg_file_sum, 'a+') as fh:
                fh.writelines(instance["InstanceType"]+',')

            if args.split_num is None:
                continue

            if write_count % int(max_eachfile) == 0 or pick_list.index(instance)+1 == len(pick_list):
                if write_count > wroten_count:
                    # log.info("write_count:%s,wrote:%smax_eachfile:%s",
                    #         write_count, wroten_count, max_eachfile)
                    cfg_file = args.cfg_name
                    cfg_file = cfg_file+str(write_count)
                    log.info("File saved to %s", cfg_file)
                    fh = open(cfg_file, 'w')
                    fh.writelines(instance_str)
                    fh.close()
                    instance_str = 'instance_types: !mux\n'
                    wroten_count = write_count
    if args.split_num is None and write_count > 0:
        log.info("File saved to %s", cfg_file)
        logging.info("Sum saved to {}".format(cfg_file_sum))
        fh = open(cfg_file, 'w')
        fh.writelines(instance_str)
        fh.close()
    elif write_count == 0:
        logging.info(
            "No instance can be run in this region, please check ami or region support")


class EC2VM:
    def __init__(self):
        self.session = boto3.session.Session(profile_name=args.profile, region_name=args.region)
        self.ec2 = self.session.resource('ec2', region_name=args.region)

        self.ami_id = args.ami_id
        self.key_name = args.key_name
        self.security_group_ids = args.security_group_ids
        self.subnet_id = args.subnet_id
        self.instance_type = None
        #self.zone = args.zone

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
                DryRun=True,
            )[0]

        except ClientError as err:
            if 'DryRunOperation' in str(err):
                logging.info("%s can create in %s", self.instance_type, args.region)
                return True
            logging.error("%s can not create in %s : %s", self.instance_type, args.region, err)
            return False
        return False


parser = argparse.ArgumentParser(
    description="Generate instance type yaml file for avocado-cloud test. \
    eg.  python /tmp/ec2_instance_select.py -c --ami-id xxxx --key_name xxxx --security_group_ids xxxx --subnet_id xxxx --zone us-west-2c -t i3.large -f /tmp/tt.yaml")
parser.add_argument('-a', dest='is_all', action='store_true',
                    help='dump all instance types, default is only current generation', required=False)
parser.add_argument('-x86_64', dest='is_x86', action='store_true',
                    help='only pick up x86 instance types', required=False)
parser.add_argument('-aarch64', dest='is_arm', action='store_true',
                    help='only pick up arm instance types', required=False)
parser.add_argument('-c', dest='check_live', action='store_true',
                    help='check whether instance can run in this region, ami_id,key_name,security_group_ids,subnet_id,instance_type and zone option required', required=False)
parser.add_argument('-d', dest='is_debug', action='store_true',
                    help='run in debug mode', required=False)
parser.add_argument('-f', dest='cfg_name', default=None, action='store',
                    help='generate and save cfg file, like ec2_instance_types.yaml', required=False)
parser.add_argument('--max_mem', dest='max_mem', action='store',
                    required=False, help='max memory in GiB')
parser.add_argument('--region', dest='region', action='store',
                    help='region to query, default is us-gov-west-1', required=False)
parser.add_argument('-r', dest='random_pick', default=None, action='store_true',
                    help='random select instance types in each type', required=False)
parser.add_argument('-s', dest='split_num', action='store',
                    required=False, help='split cfg file into severa; files which have how many instances in each file')
parser.add_argument('-t', dest='instances', action='store', default=None, required=False,
                    help='select instances from specified type, can choose multi like c5a,m5d')
parser.add_argument('--skip_instance', dest='skip_instance', action='store',
                    help='instance type to skip, seperated by ","', required=False)
parser.add_argument('--num_instances', dest='num_instances', action='store',
                    help='the max num of random select instance', required=False)
parser.add_argument('--ami-id', dest='ami_id', default=None, action='store',
                    help='required if specify -c', required=False)
parser.add_argument('--key_name', dest='key_name', default=None, action='store',
                    help='required if specify -c', required=False)
parser.add_argument('--security_group_ids', dest='security_group_ids', default=None, action='store',
                    help='required if specify -c', required=False)
parser.add_argument('--subnet_id', dest='subnet_id', default=None, action='store',
                    help='required if specify -c', required=False)
parser.add_argument('--zone', dest='zone', default=None, action='store',
                    help='required if specify -c ', required=False)
parser.add_argument('--profile', dest='profile', default='default', action='store',
                    help='option, profile name in aws credential config file, default is default', required=False)

args = parser.parse_args()
log = logging.getLogger(__name__)
FORMAT = "%(levelname)s:FUNC-%(funcName)s:%(message)s"

if args.is_debug:
    logging.basicConfig(level=logging.DEBUG, format=FORMAT)
else:
    logging.basicConfig(level=logging.INFO, format=FORMAT)


def main():
    signal.signal(signal.SIGHUP, sig_handler)
    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGQUIT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    instance_get()


if __name__ == '__main__':
    main()
