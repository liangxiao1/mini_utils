#!/usr/bin/env python
'''
github : https://github.com/liangxiao1/mini_utils

This tool is for cleaning up amis and relative snapshots together.
awscli deregister-image command only deregister image and do not delete
snapshot, the snapshots created when built AMI is using disk resource.
So clean them together to release resource.

'''
import boto3
import logging
import argparse
import sys
import os
import re
import time

def del_snapshot(snap_id):
    '''
    delete snapshot
    '''

    ec2 = boto3.resource('ec2')
    try:
        snapshot = ec2.Snapshot(snap_id)
        snapshot.delete(DryRun=False)
        log.info("delete snaphot: %s", snap_id)
        return True
    except Exception as err:
        log.info("%s is not deleted as %s", snap_id, err)
        return False

def del_ami(ami_id):
    '''
    delete ami
    '''

    ec2 = boto3.resource('ec2')
    try:
        image = ec2.Image(ami_id)
        image.deregister()
        log.info("deregister ami: %s", ami_id)
        return True
    except Exception as err:
        log.info("%s is not deleted as %s", ami_id, err)
        return False

parser = argparse.ArgumentParser('This tool is for cleaning up ami and relative snapshot together.')
parser.add_argument('--ami_list', dest='ami_list',action='store',help='amis, seperated by comma',required=True)
parser.add_argument('--delete', dest='delete',action='store_true',help='optional, specify for delete instances, otherwise list only',required=False)
parser.add_argument('-d', dest='is_debug',action='store_true',help='optional, run in debug mode', required=False,default=False)
parser.add_argument('--region', dest='region',action='store',help='region name, default us-west-2',required=False,default="us-west-2")
args = parser.parse_args()


if __name__ == '__main__':
    log = logging.getLogger(__name__)
    if args.is_debug:
        logging.basicConfig(level=logging.DEBUG,format="%(levelname)s:%(message)s")
    else:
        logging.basicConfig(level=logging.INFO,format="%(levelname)s:%(message)s")
    try:
        client = boto3.client('ec2',region_name=args.region)
    except Exception as err:
        log.info(err)
        sys.exit(1)
    ec2 = boto3.resource('ec2')
    for ami in args.ami_list.split(','):
        try:
            ami=ami.strip(' ')
            image = ec2.Image(ami)
            log.info("%s found" % ami)
            log.debug(image.block_device_mappings)
            snapid = image.block_device_mappings[0]['Ebs']['SnapshotId']
            log.info("Get snapshot id: %s", snapid)
            if snapid == None:
                log.info("Cannot get snapshot id, exit!")
                sys.exit(1)
            if args.delete:
                del_ami(ami)
                time.sleep(2)
                del_snapshot(snapid)
        except Exception as err:
            log.info("Hit error: %s", str(err))
            sys.exit(1)
