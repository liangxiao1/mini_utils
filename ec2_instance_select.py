#!/usr/bin/env python
'''
ec2 data source : https://www.ec2instances.info/?region=us-gov-west-1
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
import json
import random
import csv
import boto3
from botocore.exceptions import ClientError
import signal
import re

import requests
import lxml.html as lh
import pandas as pd
import pdb


def sig_handler(signum, frame):
    logging.info('Got signal %s, exit!', signum)
    sys.exit(0)


def df_retrive():
    if args.region is not None:
        src_url = 'https://www.ec2instances.info/?region=%s' % args.region
    else:
        logging.info("No region specified, use default us-gov-west-1")
        src_url = 'https://www.ec2instances.info/?region=us-gov-west-1'
    logging.info("Get instance data from %s", src_url)
    '''
    Below section refer to https://towardsdatascience.com/web-scraping-html-tables-with-python-c9baba21059
    '''
    src_page = requests.get(src_url)
    doc = lh.fromstring(src_page.content)
    tr_elements = doc.xpath('//tr')
    [len(T) for T in tr_elements[:52]]
    col = []
    i = 0
    for t in tr_elements[0]:
        i += 1
        name = t.text_content()

        name = name.strip('\n ')
        # print("%d,%s" % (i, name))
        col.append((name, []))

    for j in range(1, len(tr_elements)):

        T = tr_elements[j]

        if len(T) != 52:
            break

        i = 0
        for t in T.iterchildren():
            data = t.text_content()
            if i > 0:
                try:
                    data = int(data)
                except:
                    pass
            col[i][1].append(data)
            i += 1
    Dict = {title: column for (title, column) in col}
    df = pd.DataFrame(Dict)
    # df.to_csv('test.csv')
    df.sort_values('API Name')
    return df
    '''
    #it is a fast way to read html table, but not always works as expected.
    Use above solution firstly.
    df = pd.read_html(src_url)
    df[0].sort_values('API Name')
    logging.info(df[0]['API Name'])
    return df[0]
    '''


def deal_instancetype(x):
    if x.count('.') > 0:
        return x
    return x+'.'


def df_parser(df):
    logging.info(df.sort_values('API Name')['API Name'].values[0])
    instance_list = df.sort_values('API Name')['API Name'].tolist()
    if len(instance_list) == 0:
        logging.info("No instance can run in this region!")
        sys.exit(1)
    instance_list.sort()
    # logging.info(instance_list)

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
        for x in instances_type:
            # logging.info(
            #    df.where(df['API Name'].str.startswith(x))['API Name'].dropna().values)
            pick_list.extend(df.where(df['API Name'].str.startswith(x))[
                             'API Name'].dropna().values)
    elif args.is_all:
        pick_list = instance_list

    # logging.info(pick_list)

    write_count = 0
    wroten_count = 0
    if args.split_num is not None:
        max_eachfile = args.split_num
    if args.cfg_name is None:
        cfg_file = "ec2_instance_types.yaml"
    else:
        cfg_file = args.cfg_name

    for instance in pick_list:
        # logging.info(df[df['API Name'] == instance]['API Name'].values[0])
        log.info("%s selected", instance)
        # log.info(df[df['API Name'] == instance]['Instance Storage'].values)
        if args.check_live:
            vm = EC2VM()
            vm.instance_type = instance
            if not vm.create():
                continue
        is_write = True
        disk_count = 1
        if is_write:
            store_str = df[df['API Name'] ==
                           instance]['Instance Storage'].values[0].strip('\n ')
            if 'EBS only' in store_str:
                disk_count = 1
            elif r'*' in store_str:
                disk_count = int(re.findall(
                    '\([0-9]+ \*', store_str)[0].strip('*\('))
                disk_count += 1
            else:
                disk_count += 1
            net_str = df[df['API Name'] ==
                         instance]['Network Performance'].values[0].strip('\n ')
            if 'Moderate' in net_str:
                net_perf = 0
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
            if 'Yes' in df[df['API Name'] == instance]['IPv6 Support'].values[0]:
                ipv6_support = True
            else:
                ipv6_support = False
            vcpu_str = df[df['API Name'] ==
                          instance]['vCPUs'].values[0]
            vcpu_str = re.findall(
                '[0-9 ]+ vCPUs', vcpu_str)[0].strip('vCPUs\n ')
            instance_str += instance_template.substitute(
                instance_type=instance, cpu_count=vcpu_str, mem_size=df[df['API Name'] == instance]['Memory'].values[0].rstrip('GiB'), disk_count=disk_count, net_perf=net_perf, ipv6_support=ipv6_support)
            write_count += 1

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
        fh = open(cfg_file, 'w')
        fh.writelines(instance_str)
        fh.close()
    elif write_count == 0:
        logging.info(
            "No instance can be run in this region, please check ami or region support")


class EC2VM:
    def __init__(self):
        self.ec2 = boto3.resource('ec2')

        self.ami_id = args.ami_id
        self.key_name = args.key_name
        self.security_group_ids = args.security_group_ids
        self.subnet_id = args.subnet_id
        self.instance_type = None
        self.zone = args.zone

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
                Placement={
                    'AvailabilityZone': self.zone,
                },
                DryRun=True,
            )[0]

        except ClientError as err:
            if 'DryRunOperation' in str(err):
                logging.info("Can create in %s", self.zone)
                return True
            logging.error("Can not create in %s : %s", self.zone, err)
            return False
        return False


parser = argparse.ArgumentParser(
    description="Generate instance type yaml file for avocado-cloud test. \
    eg.  python /tmp/ec2_instance_select.py -c --ami-id xxxx --key_name xxxx --security_group_ids xxxx --subnet_id xxxx --zone us-west-2c -t i3.large -f /tmp/tt.yaml")
parser.add_argument('-a', dest='is_all', action='store_true',
                    help='dump all instance types', required=False)
parser.add_argument('-c', dest='check_live', action='store_true',
                    help='check whether instance can run in this region, ami_id,key_name,security_group_ids,subnet_id,instance_type and zone option required', required=False)
parser.add_argument('-d', dest='is_debug', action='store_true',
                    help='run in debug mode', required=False)
parser.add_argument('-f', dest='cfg_name', default=None, action='store',
                    help='generate and save cfg file, like ec2_instance_types.yaml', required=False)
parser.add_argument('--region', dest='region', action='store',
                    help='region to query, default is us-gov-west-1', required=False)
parser.add_argument('-r', dest='random_pick', default=None, action='store_true',
                    help='random select instance types in each type', required=False)
parser.add_argument('-s', dest='split_num', action='store',
                    required=False, help='split cfg file into severa; files which have how many instances in each file')
parser.add_argument('-t', dest='instances', action='store', default=None, required=False,
                    help='select instances from specified type, can choose multi like c5a,m5d')

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

    instance_df = df_retrive()
    df_parser(instance_df)


if __name__ == '__main__':
    main()
