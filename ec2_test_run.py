#!/usr/bin/env python
'''
github : https://github.com/liangxiao1/mini_utils

This tool is using for running avocado-cloud ec2 test in paralle with multi users 
for more efficent.

instance_yaml file should be like below, more instances supported.
instance_types: !mux
    i3.large:
        instance_type: i3.large
        cpu: 2
        memory: 15.25 
        disks: 2
        net_perf : 10
        ipv6: True

'''

import logging
import os
import sys
import argparse
import pexpect
import signal
import shutil
import errno
import tempfile

avocado_cloud_dir = '/home/ec2/avocado-cloud'


def sig_handler(signum, frame):
    logging.info('Got signal %s, exit!', signum)
    sys.exit(0)


def setup_dir():
    log.info("Setup dir %s" % args.result_dir)
    #user_list = map(lambda user: 'cloud'+str(user), range(0, 100))
    if not os.path.exists(args.result_dir):
        log.info("%s not found" % args.result_dir)
        sys.exit(errno.ENOENT)
    if not os.path.exists(avocado_cloud_dir):
        log.info("%s please put avocado-cloud to /home/ec2 directory")
        sys.exit(errno.ENOENT)
    try:
        log.info('Copy ec2 config files to %s' % args.result_dir)
        ec2_env_yaml = '%s/ec2_env_conf.yaml' % args.result_dir
        ec2_testcase_yaml = '%s/ec2_testcases.yaml' % args.result_dir
        ec2_test_yaml = '%s/ec2_test.yaml' % args.result_dir
        ec2_instance_yaml = '%s/ec2_instance_types.yaml' % args.result_dir
        shutil.copy(avocado_cloud_dir +
                    '/config/ec2_env_conf.yaml', ec2_env_yaml)
        shutil.copy(avocado_cloud_dir +
                    '/config/ec2_testcases.yaml', ec2_testcase_yaml)
        shutil.copy(avocado_cloud_dir +
                    '/config/ec2_test.yaml', ec2_test_yaml)
        shutil.copy(avocado_cloud_dir +
                    '/config/ec2_instance_types.yaml', ec2_instance_yaml)

    except Exception as err:
        log.error("Copy exception hit!\n %s" % err)
        sys.exit(errno.ENOENT)


def setup_avocado():

    if args.ami_id is None or args.region is None or args.subnet_id is None or args.security_group_ids is None or args.instance_yaml is None:
        log.error(
            "ami_id,region,subnet_id,security_group_ids, instance_yaml is not allowed empty")
        sys.exit(1)
    instance_yaml = args.instance_yaml
    if not os.path.exists(instance_yaml):
        log.error("No %s found!" % instance_yaml)
        sys.exit(1)
    instance_yaml_dest = '%s/ec2_instance_types.yaml' % args.result_dir
    if os.path.exists(instance_yaml_dest):
        os.unlink(instance_yaml_dest)
    log.info('Copy %s to %s' % (instance_yaml, instance_yaml_dest))
    shutil.copy(instance_yaml, instance_yaml_dest)
    tmp_yaml = "/%s/t.yaml" % args.result_dir
    ec2_env_yaml = '%s/ec2_env_conf.yaml' % args.result_dir
    if os.path.exists(tmp_yaml):
        os.unlink(tmp_yaml)

    with open(ec2_env_yaml, 'r') as fh:
        for line in fh.readlines():
            if line.startswith('ami_id :'):
                line = 'ami_id : %s\n' % args.ami_id
            if line.startswith('region : '):
                line = 'region : %s\n' % args.region
            if line.startswith('availability_zone : '):
                line = 'availability_zone : %s\n' % args.zone
            if line.startswith('subnet_id_ipv6 : '):
                line = 'subnet_id_ipv6 : %s\n' % args.subnet_id
            if line.startswith('subnet_id_ipv4 : '):
                line = 'subnet_id_ipv4 : %s\n' % args.subnet_id
            if line.startswith('security_group_ids : '):
                line = 'security_group_ids : %s\n' % args.security_group_ids
            if line.startswith('ssh_key_name : '):
                line = 'ssh_key_name : %s\n' % args.key_name
            if line.startswith('ec2_tagname : '):
                line = 'ec2_tagname : virtqe_auto_cloud\n'
            if line.startswith('ltp_url : ') and args.ltp_url is not None:
                line = 'ltp_url: %s\n' % args.ltp_url
            if line.startswith('code_cover : '):
                line = 'code_cover : %s\n' % args.is_gcov
            with open(tmp_yaml, 'a') as fd:
                fd.writelines(line)

    if os.path.exists(ec2_env_yaml):
        os.unlink(ec2_env_yaml)
    log.info('Copy %s to %s' % (tmp_yaml, ec2_env_yaml))
    shutil.copy(tmp_yaml, ec2_env_yaml)


def run_avocado():
    log.info("Start to run avocado-cloud......")
    avocado_dir = '/home/ec2/avocado-cloud'
    os.chdir(avocado_dir)
    if args.timeout is None:
        timeout = 28800
    else:
        timeout = args.timeout
    log.info("Wait timeout was set to %s" % timeout)

    if 'acceptance' in args.casetag:
        cmd = 'avocado run -m %s/ec2_test.yaml --filter-by-tags %s %s/tests/aws/ \
            --execution-order=tests-per-variant --job-results-dir %s' % (args.result_dir,
                                                                         args.casetag, avocado_cloud_dir, args.result_dir)
    else:
        casetags = ''.join(
            map(lambda s: ' --filter-by-tags '+s, args.casetag.split(',')))
        cmd = 'avocado run -m %s/ec2_test.yaml %s --filter-by-tags test_cleanupall %s/tests/aws/ \
            --execution-order=tests-per-variant --job-results-dir %s' % (args.result_dir,
                                                                         casetags, avocado_cloud_dir, args.result_dir)
    log.info("Run cmd: %s" % cmd)
    ret, output = pexpect.run(cmd, timeout=int(timeout), withexitstatus=True)
    if ret != 0:
        log.error('Error got, ret%s' % ret)
    log.info(output)


parser = argparse.ArgumentParser(
    description="This tool is using for running avocado-cloud ec2 test in paralle.\
    eg. python ec2_test_run.py --instance_yaml /tmp/t.yaml --ami-id ami-xxxx --key_name xxxx \
        --security_group_ids sg-xxxx --subnet_id subnet-xxxx --region us-west-2")

parser.add_argument('--instance_yaml', dest='instance_yaml', action='store', default=None, required=False,
                    help='instance types yaml file')
parser.add_argument('-d', dest='is_debug', action='store_true',
                    help='run in debug mode', required=False)

parser.add_argument('--clean', dest='is_clean', action='store_true',
                    help='caution: clean up all exists users /home/cloudN before test', required=False)

parser.add_argument('--ami-id', dest='ami_id', default=None, action='store',
                    help='image id', required=False)
parser.add_argument('--key_name', dest='key_name', default=None, action='store',
                    help='key to create instance', required=False)
parser.add_argument('--security_group_ids', dest='security_group_ids', default=None, action='store',
                    help='securitt group id', required=False)
parser.add_argument('--subnet_id', dest='subnet_id', default=None, action='store',
                    help='subnet id', required=False)
parser.add_argument('--region', dest='region', default=None, action='store',
                    help='region to run ', required=False)
parser.add_argument('--zone', dest='zone', default=None, action='store',
                    help='zone to run ', required=False)
parser.add_argument('--timeout', dest='timeout', default=None, action='store',
                    help='bare metal can set to 8hrs each, others can be 7200 each, default it 28800s', required=False)
parser.add_argument('--casetag', dest='casetag', default='acceptance', action='store',
                    help='cases filter tag, default is acceptance, more tags can be seperated by ","', required=False)
parser.add_argument('--result_dir', dest='result_dir', default=None, action='store',
                    help='where to save the result', required=True)
parser.add_argument('--ltp_url', dest='ltp_url', default=None, action='store',
                    help='ltp rpm url', required=False)
parser.add_argument('-g', dest='is_gcov', action='store_true',
                    help='optional,enable collect code coverage report, image should have gcov version kernel installed', required=False)

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

    setup_dir()
    setup_avocado()
    run_avocado()


if __name__ == '__main__':
    main()
