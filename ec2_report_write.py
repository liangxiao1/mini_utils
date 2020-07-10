# /usr/bin/env python
'''
Write avocado-cloud test log to sqlite
github : https://github.com/liangxiao1/mini_utils

'''
from __future__ import print_function
import json
import sys
import re
import os
import argparse
import logging
from sqlalchemy import create_engine
from sqlalchemy import Column, Integer, String, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker


LOG = logging.getLogger(__name__)

logging.basicConfig(level=logging.DEBUG,
                    format='%(levelname)s:%(message)s')

if sys.version.startswith('2'):
    LOG.info("Please do not run it using python2")
    sys.exit(1)

ARG_PARSER = argparse.ArgumentParser(description="Write results to local db")
ARG_PARSER.add_argument('--dir', dest='log_dir', action='store',
                        help="specify log directory", default=None, required=True)
ARG_PARSER.add_argument('--db_file', dest='db_file', action='store',
                        help="specify database location", default=None, required=True)
ARG_PARSER.add_argument("--ami-id", dest='ami_id', action='store',
                        help="specify ami id", default=None, required=False)
ARG_PARSER.add_argument("--compose-id", dest='compose_id', action='store',
                        help="specify compose id if have", default=None, required=False)
ARG_PARSER.add_argument("--instance_available_date", dest='instance_available_date', action='store',
                        help="specify it if it is new", default=None, required=False)
ARG_PARSER.add_argument("--pkg_ver", dest='pkg_ver', action='store',
                        help="specify pkg version, like kernel or others", default=None,
                        required=False)
ARG_PARSER.add_argument("--bug-id", dest='bug_id', action='store',
                        help="specify bug id if have", default=None, required=False)
ARG_PARSER.add_argument("--report_url", dest='report_url', action='store',
                        help="specify log url", default=None, required=True)
ARG_PARSER.add_argument("--branch_name", dest='branch_name', action='store',
                        help="specify branch name, like RHEL6|7|8", default=None, required=True)
ARG_PARSER.add_argument("--comments", dest='comments', action='store',
                        help="more information if have", default=None, required=False)
ARG_PARSER.add_argument("--testrun", dest='testrun', action='store',
                        help="specify a testrun name", default=None, required=True)
ARGS = ARG_PARSER.parse_args()


DB_ENGINE = create_engine('sqlite:///%s' % ARGS.db_file, echo=True)
DB_SESSION = sessionmaker(bind=DB_ENGINE)
DB_BASE = declarative_base()
JOB_XML = ARGS.log_dir+"/results.xml"
JOB_LOG = ARGS.log_dir+"/job.log"

# pylint: disable=R0902,R0903
class Report(DB_BASE):
    '''
    The table's schema definication.
    '''
    __tablename__ = 'e_c2__report'
    log_id = Column(Integer, primary_key=True)
    ami_id = Column(String)
    instance_type = Column(String)
    instance_available_date = Column(String)
    compose_id = Column(String)
    pkg_ver = Column(String)
    bug_id = Column(String)
    report_url = Column(String)
    branch_name = Column(String)
    cases_pass = Column(Integer)
    cases_fail = Column(Integer)
    cases_cancel = Column(Integer)
    cases_other = Column(Integer)
    cases_total = Column(Integer)
    pass_rate = Column(Integer)
    test_date = Column(String)
    comments = Column(String)
    platform = Column(String)
    testrun = Column(String)
    sqlite_autoincrement = True


class EC2Case(DB_BASE):
    '''
    table for storing ec2 project log by casename
    '''
    __tablename__ = 'e_c2_report_case'
    log_id = Column(Integer, primary_key=True)
    ami_id = Column(String(50))
    instance_type = Column(String(50))
    compose_id = Column(String(50))
    pkg_ver = Column(String(50))
    branch_name = Column(String(50))
    testrun = Column(String(50))
    case_name = Column(String(50))
    case_result = Column(String(50))
    run_time = Column(Float)
    case_debuglog = Column(String)
    test_date = Column(String)
    component = Column(String(50))
    comments = Column(String)
    platform = Column(String(50))
    sqlite_autoincrement = True

def get_ami_id():
    '''
    If no ami_id provided from parameters, then try to get it from the test log.
    '''
    if ARGS.ami_id is None:
        ami_id = None
        LOG.info('no ami_id specified, try to get it from results.xml')
        with open(JOB_XML) as file_handler:
            for line in file_handler.readlines():
                ami_ids = re.findall("ami-.*", line)
                if ami_ids and 'ami_id' in line:
                    ami_id = ami_ids[0].strip("'")
                    LOG.info('find %s', ami_id)
                    break
        if ami_id is None:
            LOG.info('no ami_id specified, try to get it from job.log')
            with open(JOB_LOG) as file_handler:
                for line in file_handler.readlines():
                    ami_ids = re.findall("ami-.*", line)
                    if ami_ids and 'ami_id' in line:
                        ami_id = ami_ids[0].strip("'")
                        LOG.info('find %s', ami_id)
                        break
        if ami_id is None:
            LOG.info('cannot get ami_id, exit!')
            sys.exit(1)
        ARGS.ami_id = ami_id

def get_pkg_ver():
    '''
    If no pkg_ver provided from parameters, then try to get kernel version from the test log.
    The pkg_ver maybe a cloud-init or others if required.
    '''
    if ARGS.pkg_ver is None:
        pkg_ver = None
        LOG.info('no pkg_ver specified, try to get it from log, use kernel version instead \
            from %s', JOB_XML)
        with open(JOB_XML) as file_handler:
            for line in file_handler.readlines():
                # pylint: disable=W1401
                pkg_vers = re.findall(":\d.\d{1,2}.\d{1,4}-.*64", line)
                if pkg_vers:
                    pkg_ver = pkg_vers[0].strip("'")
                    pkg_ver = pkg_vers[0].strip(":")
                    LOG.info('find %s', pkg_ver)
                    break
        if pkg_ver is None:
            pkg_ver = None
            LOG.info('no pkg_ver specified, try to get it from log, use kernel version instead \
                from %s', JOB_LOG)
            with open(JOB_LOG) as file_handler:
                for line in file_handler.readlines():
                    # pylint: disable=W1401
                    pkg_vers = re.findall(":\d.\d{1,2}.\d{1,4}-.*64", line)
                    if pkg_vers:
                        pkg_ver = pkg_vers[0].strip("'")
                        pkg_ver = pkg_vers[0].strip(":")
                        LOG.info('find %s', pkg_ver)
                        break
        if pkg_ver is None:
            LOG.info('cannot get pkg_ver, exit!')
            sys.exit(1)
        ARGS.pkg_ver = 'kernel-'+pkg_ver

def report_writer():
    '''
    read and parse avocado-cloud logs, write Report to db.
    '''
    instances_sub_report = {}

    log_json = ARGS.log_dir+"/results.json"
    with open(log_json, 'r') as file_handler:
        report_dict = json.load(file_handler)
        # print(report_dict)
        print(report_dict['debuglog'])
        test_date = re.findall(
            '[0-9]{4}-[0-9]{2}-[0-9]{2}', report_dict['debuglog'])
        for test_item in report_dict['tests']:
            instance_type = re.findall('Cloud-.*-', test_item['id'])[0].split('-')[1]
            if instance_type not in instances_sub_report.keys():
                instances_sub_report[instance_type] = {
                    'cases_other': 0, 'cases_pass': 0, 'cases_fail': 0, 'cases_cancel': 0,
                    'cases_total': 0, 'test_date': test_date, 'pass_rate': 0}
            instances_sub_report[instance_type]['cases_total'] += 1
            if 'PASS' in test_item['status']:
                instances_sub_report[instance_type]['cases_pass'] += 1
            elif 'FAIL' in test_item['status']:
                instances_sub_report[instance_type]['cases_fail'] += 1
            elif "CANCEL" in test_item['status'] or "SKIP" in test_item['status']:
                instances_sub_report[instance_type]['cases_cancel'] += 1
            else:
                instances_sub_report[instance_type]['cases_other'] += 1
            pass_rate = instances_sub_report[instance_type]['cases_pass']*100 / \
                (instances_sub_report[instance_type]['cases_total'] -
                 instances_sub_report[instance_type]['cases_cancel'])
            instances_sub_report[instance_type]['pass_rate'] = pass_rate

    for instance_type in instances_sub_report:
        print(instance_type, instances_sub_report[instance_type])
        report = Report()
        report.ami_id = ARGS.ami_id
        report.instance_type = instance_type
        report.compose_id = ARGS.compose_id
        report.instance_available_date = ARGS.instance_available_date
        report.pkg_ver = ARGS.pkg_ver
        report.bug_id = ARGS.bug_id
        report.report_url = ARGS.report_url
        report.branch_name = ARGS.branch_name
        report.testrun = ARGS.testrun
        report.comments = ARGS.comments
        report.platform = 'aws'
        report.cases_pass = instances_sub_report[instance_type]['cases_pass']
        report.cases_fail = instances_sub_report[instance_type]['cases_fail']
        report.cases_cancel = instances_sub_report[instance_type]['cases_cancel']
        report.cases_other = instances_sub_report[instance_type]['cases_other']
        report.cases_total = instances_sub_report[instance_type]['cases_total']
        report.pass_rate = instances_sub_report[instance_type]['pass_rate']
        report.test_date = instances_sub_report[instance_type]['test_date'][0]
        session = DB_SESSION()
        session.add(report)
        session.commit()

def case_report_writer():
    '''
    read and parse avocado-cloud logs, write cases status to db.
    '''
    instances_sub_report = {}

    log_json = ARGS.log_dir+"/results.json"
    with open(log_json, 'r') as file_handler:
        report_dict = json.load(file_handler)
        # print(report_dict)
        print(report_dict['debuglog'])
        test_date = re.findall(
            '[0-9]{4}-[0-9]{2}-[0-9]{2}', report_dict['debuglog'])
        for test_item in report_dict['tests']:
            instance_type = re.findall('Cloud-.*-', test_item['id'])[0].split('-')[1]
            case_name = re.findall('\.test.*;', test_item['id'])[0].rstrip(";").lstrip('.')
            component =re.findall('(:.*?\.)', test_item['id'])[0].rstrip('.').lstrip(':')
            LOG.info("instance_type: {} case_name: {} component: {}".format(instance_type, case_name, component))
            case_result = test_item['status']
            run_time = test_item['time']
            debuglog = os.path.join(ARGS.log_dir, '/'.join(test_item['logfile'].split('/')[-3:]))
            LOG.info("instance_type: {} case_name: {} component: {} debuglog: {}".format(instance_type, case_name, component,debuglog))
            with open(debuglog,'r') as fh:
                case_debuglog = fh.read()

            report = EC2Case()
            report.ami_id = ARGS.ami_id
            report.instance_type = instance_type
            report.compose_id = ARGS.compose_id
            report.pkg_ver = ARGS.pkg_ver
            report.bug_id = ARGS.bug_id
            report.report_url = ARGS.report_url
            report.branch_name = ARGS.branch_name
            report.testrun = ARGS.testrun
            report.case_name = case_name
            report.case_result = case_result
            report.case_debuglog = case_debuglog
            report.run_time = run_time
            report.component = component
            report.comments = ARGS.comments
            report.platform = 'aws'
            report.test_date = test_date[0]
            session = DB_SESSION()
            session.add(report)
            session.commit()

if __name__ == "__main__":
    get_ami_id()
    get_pkg_ver()
    report_writer()
    case_report_writer()
