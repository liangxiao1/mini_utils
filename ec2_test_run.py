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


def sig_handler(signum, frame):
    logging.info('Got signal %s, exit!', signum)
    sys.exit(0)


def setup_user():
    log.info("Setup user, max 100 users!")
    user_list = map(lambda user: 'cloud'+str(user), range(0, 100))
    new_user = None
    user_home = None
    for user in user_list:
        user_home = '/home/'+user
        if os.path.exists(user_home):
            log.debug('User %s exists! use others' % user)
        else:
            log.info("Create user: %s" % user)
            pexpect.run('useradd '+user)
            if os.path.exists(user_home):
                log.info('User %s created!' % user)
            new_user = user
            break
    if new_user is None:
        log.info("Max 100 users, all are in use!")
        sys.exit(errno.EUSERS)
    try:
        log.info('Copy /home/ec2/.aws to %s' % user_home)
        pexpect.run("cp -r /home/ec2/.aws %s/" % user_home)
        log.info('Copy avocado-cloud to %s' % user_home)
        pexpect.run("cp -r /home/ec2/avocado-cloud %s/" % user_home)

    except Exception as err:
        log.error("Copy exception hit!\n %s" % err)
        cleanup_user(new_user)
        sys.exit(errno.ENOENT)
    return new_user


def cleanup_user(user_name):
    log.info("Remove %s" % user_name)
    pexpect.run("userdel "+user_name)
    shutil.rmtree('/home/'+user_name)
    sys.exit(0)


def setup_avocado(user_name):

    if args.ami_id is None or args.region is None or args.subnet_id is None or args.security_group_ids is None or args.instance_yaml is None:
        log.error("ami_id,region,subnet_id,security_group_ids is not allowed empty")
        cleanup_user(user_name)
    instance_yaml = args.instance_yaml
    if not os.path.exists(instance_yaml):
        log.error("No %s found!" % instance_yaml)
        return False
    instance_yaml_dest = '/home/%s/avocado-cloud/config/ec2_instance_types.yaml' % user_name
    os.unlink(instance_yaml_dest)
    log.info('Copy %s to %s' % (instance_yaml, instance_yaml_dest))
    shutil.copy(instance_yaml, instance_yaml_dest)
    tmp_yaml = "/tmp/%s.yaml" % user_name
    ec2_env_yaml = '/home/%s/avocado-cloud/config/ec2_env_conf.yaml' % user_name
    if os.path.exists(tmp_yaml):
        os.unlink(tmp_yaml)

    with open(ec2_env_yaml, 'r') as fh:
        for line in fh.readlines():
            if line.startswith('ami_id :'):
                line = 'ami_id : %s\n' % args.ami_id
            if line.startswith('region : '):
                line = 'region : %s\n' % args.region
            if line.startswith('region : '):
                line = 'subnet_id_ipv6 : %s\n' % args.subnet_id
            if line.startswith('subnet_id_ipv4 : '):
                line = 'subnet_id_ipv4 : %s\n' % args.subnet_id
            if line.startswith('security_group_ids : '):
                line = 'security_group_ids : %s\n' % args.security_group_ids
            if line.startswith('ec2_tagname : '):
                line = 'ec2_tagname : virtqe_node_%s\n' % user_name
            with open(tmp_yaml, 'a') as fd:
                fd.writelines(line)

    if os.path.exists(ec2_env_yaml):
        os.unlink(ec2_env_yaml)
    log.info('Copy %s to %s' % (tmp_yaml, ec2_env_yaml))
    shutil.copy(tmp_yaml, ec2_env_yaml)


def run_avocado(user_name):
    log.info("Start to run avocado-cloud......")
    avocado_dir = "/home/%s/avocado-cloud/" % user_name
    os.chdir(avocado_dir)
    session = pexpect.spawn("su "+user_name)
    session.expect('$')
    session.logfile = sys.stdout

    if 'acceptance' in args.casetag:
        cmd = 'avocado run -m config/ec2_test.yaml --filter-by-tags %s tests/aws/ --execution-order=tests-per-variant' % args.casetag
    else:
        cmd = 'avocado run -m config/ec2_test.yaml --filter-by-tags %s --filter-by-tags test_cleanupall tests/aws/ --execution-order=tests-per-variant' % args.casetag
    log.info("Run %s" % cmd)
    session.sendline(cmd)
    if args.timeout is None:
        timeout = 28800
    else:
        timeout = args.timeout
    log.info("Wait timeout was set to %s" % timeout)
    session.expect('JOB HTML', timeout=timeout)
    session.close()
    log_link = "/home/%s/avocado/job-results/latest" % user_name
    log_dir = "/home/%s/avocado/job-results/%s" % (
        user_name, os.readlink(log_link))
    log.info("Test completed, log dir %s" % log_dir)

    tmpdir = tempfile.mkdtemp(prefix='ec2_', dir='/tmp')
    log.info("Move it to %s" % tmpdir)
    pexpect.run("cp -r %s %s/" % (log_dir, tmpdir))


parser = argparse.ArgumentParser(
    description="This tool is using for running avocado-cloud ec2 test in paralle.\
    eg. python ec2_test_run.py --instance_yaml /tmp/t.yaml --ami-id ami-xxxx --key_name xxxx --security_group_ids sg-xxxx --subnet_id subnet-xxxx --region us-west-2")

parser.add_argument('--instance_yaml', dest='instance_yaml', action='store', default=None, required=False,
                    help='instance types yaml file')
parser.add_argument('-d', dest='is_debug', action='store_true',
                    help='run in debug mode', required=False)

parser.add_argument('--clean', dest='is_clean', action='store_true',
                    help='caution: clean up all exists users /home/cloudN before test', required=False)

parser.add_argument('--ami-id', dest='ami_id', default=None, action='store',
                    help='required if specify -c', required=False)
parser.add_argument('--key_name', dest='key_name', default=None, action='store',
                    help='required if specify -c', required=False)
parser.add_argument('--security_group_ids', dest='security_group_ids', default=None, action='store',
                    help='required if specify -c', required=False)
parser.add_argument('--subnet_id', dest='subnet_id', default=None, action='store',
                    help='required if specify -c', required=False)
parser.add_argument('--region', dest='region', default=None, action='store',
                    help='required if specify -c ', required=False)
parser.add_argument('--timeout', dest='timeout', default=None, action='store',
                    help='bare metal can set to 8hrs each, others can be 7200 each, default it 28800s', required=False)
parser.add_argument('--casetag', dest='casetag', default='acceptance', action='store',
                    help='cases filter tag, default is acceptance ', required=False)

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

    if args.is_clean:
        user_list = map(lambda user: 'cloud'+str(user), range(0, 100))
        for user in user_list:
            cleanup_user(user)

    user = setup_user()
    setup_avocado(user)
    run_avocado(user)
    cleanup_user(user)


if __name__ == '__main__':
    main()
