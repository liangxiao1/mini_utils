#!/usr/bin/env python
'''
github : https://github.com/liangxiao1/mini_utils

This tool is for clean up running instances in all supported regions by keyname

'''
import boto3
import logging
import argparse

parser = argparse.ArgumentParser('To list/clean up instances cross regions')
parser.add_argument('--key_name', dest='key_name',action='store',help='specify for owner, seperated by ","',required=False)
#parser.add_argument('--instance_name', dest='instance_name',action='store',help='specify for instance_name, seperated by ","',required=False)
parser.add_argument('--tags', dest='tags',action='store',help='specify for tags, seperated by ","',required=False)
parser.add_argument('--delete', dest='delete',action='store_true',help='optional, specify for delete instances, otherwise list only',required=False)
parser.add_argument('-d', dest='is_debug',action='store_true',help='optional, run in debug mode', required=False,default=False)
parser.add_argument('--skip_region', dest='skip_region',action='store',help='optional skip regions, seperated by ","',required=False,default=None)
parser.add_argument('--only_region', dest='only_region',action='store',help='optional only regions for checking, seperated by ","',required=False,default=None)
args = parser.parse_args()

log = logging.getLogger(__name__)
if args.is_debug:
    logging.basicConfig(level=logging.DEBUG,format="%(levelname)s:%(asctime)s:%(message)s")
else:
    logging.basicConfig(level=logging.INFO,format="%(levelname)s:%(asctime)s:%(message)s")
client = boto3.client('ec2')

region_list = client.describe_regions()

for region in region_list['Regions']:
    region_name = region['RegionName']
    if args.skip_region is not None and region_name in args.skip_region:
        log.info('Skip %s' % region_name)
        continue
    if args.only_region is not None and region_name not in args.only_region:
        log.info('Skip %s' % region_name)
        continue
    log.info("Check %s " % region_name)
    try:
        client = boto3.client('ec2',region_name=region_name)
        s=client.describe_instances()
    except Exception as err:
        log.info(err)
        continue
    #log.info(s)
    for instance in s['Reservations']:
        #log.info(instance)
        try:
            if args.key_name is not None:
                for key_name in args.key_name.split(','):
                    if instance['Instances'][0].has_key('KeyName'):
                        if key_name in instance['Instances'][0]['KeyName']:
                            instance_id = instance['Instances'][0]['InstanceId']
                            if instance['Instances'][0].has_key('Tags'):
                                log.info('Key:%s Tag: %s, LaunchTime: %s id:%s' % (instance['Instances'][0]['KeyName'],
                                    instance['Instances'][0]['Tags'][0]['Value'],instance['Instances'][0]['LaunchTime'],instance_id ))
                            else:
                                log.info('Key:%s Tag: N/A LaunchTime: %s id:%s' % (instance['Instances'][0]['KeyName'],
                                    instance['Instances'][0]['LaunchTime'],instance_id ))
                            if args.delete:
                                ec2 = boto3.resource('ec2',region_name=region_name)
                                vm = ec2.Instance(instance_id)
                                vm.terminate()
                                log.info('%s terminated' % instance_id)
            if args.tags is not None:
                for tag in args.tags.split(','):
                    if instance['Instances'][0].has_key('Tags'):
                        for val  in instance['Instances'][0]['Tags'][0].values():
                            if tag in val:
                                instance_id = instance['Instances'][0]['InstanceId']
                                log.info('Key:%s Tag: %s, LaunchTime: %s id:%s' % (instance['Instances'][0]['KeyName'],
                                    instance['Instances'][0]['Tags'][0]['Value'],instance['Instances'][0]['LaunchTime'],instance_id ))
                                if args.delete:
                                    ec2 = boto3.resource('ec2',region_name=region_name)
                                    vm = ec2.Instance(instance_id)
                                    vm.terminate()
                                    log.info('%s terminated' % instance_id)
        except KeyError as err:
            log.info("No such words found %s" % err)
    