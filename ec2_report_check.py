# /usr/bin/env python
'''
Check ec2 test result automatically.
github : https://github.com/liangxiao1/mini_utils
'''
import os
import sys
import logging
import re
import json
import argparse
from failure_analyzer import log_analyze, FailureType, FailureStatus
import pdb

ARG_PARSER = argparse.ArgumentParser(description="aws test report auto check")
ARG_PARSER.add_argument('--dir', dest='log_dir', action='store',
                        help="specify log directory", default=None, required=True)
ARG_PARSER.add_argument('--db_file', dest='db_file', action='store',
                        help="specify database location", default=None, required=True)
ARG_PARSER.add_argument('-d', dest='is_debug', action='store_true',
    help='optional, run in debug mode', required=False, default=False)
ARG_PARSER.add_argument('-a', dest='is_all', action='store_true',
        help='optional, only open bug searched by default', required=False, default=False)
ARGS = ARG_PARSER.parse_args()
LOG = logging.getLogger(__name__)
if ARGS.is_debug:
    logging.basicConfig(level=logging.DEBUG, format='%(levelname)s:%(message)s')
else:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(message)s')

JOB_LOG = ARGS.log_dir+"/job.log"
RESULT_JSON = ARGS.log_dir+"/results.json"

debug_list = []
def walk_dir(dir_name):
    for item in os.listdir(dir_name):
        if item.startswith(r'.'):
            continue
        abs_path = os.path.abspath(os.path.join(dir_name,item))
        if os.path.isdir(abs_path):
            walk_dir(abs_path)
        else:
            file_name = abs_path
            if file_name.endswith('debug.log'):
                debug_list.append(file_name)
    if len(debug_list) == 0:
        LOG.debug('No debug.log file found!')
    return debug_list

def item_writer(debug_log):
    LOG.debug("Write %s" % debug_log)
    case_dir = debug_log.split('/')[-2]
    instance_type = case_dir.split('-')[-2]
    case_name = re.findall('\.test_[_\da-z]{1,40}',case_dir)[0].rstrip('_').lstrip('.')
    LOG.debug("instance type: %s case name: %s", instance_type, case_name)

def get_fails(log_json):
    if not os.path.exists(log_json):
        LOG.info("Cannot find %s", log_json)
    with open(log_json,'r') as file_handle:
        cases_dict = json.load(file_handle)['tests']
    final_result = {}
    for case in cases_dict:
        if case['status'] == 'FAIL' or case['status'] == 'ERROR':
            LOG.info('Failure: %s',case['id'])
            #LOG.info(debug_list)
            for debug_log in debug_list:
                id = re.findall('^[\d]*-', case['id'])[0]
                #LOG.info(int_id)
                if id+'_' in debug_log:
                    tmp_result = log_analyze(db_file=ARGS.db_file, log_file=debug_log, case_name=case['id'],LOG=LOG, is_all=ARGS.is_all)
                    if tmp_result[0] not in final_result.keys():
                        final_result[tmp_result[0]] = [tmp_result[1]]
                        continue
                    for f in final_result.keys():
                        if tmp_result[0] == f:
                            final_result[f].append(tmp_result[1])
                #else:
                #    LOG.info("Not found debug log %s ", case['id'])
    LOG.info(final_result)
    autocheck_log = "{}/autocheck.log".format(ARGS.log_dir)
    if len(final_result) > 0:
        with open(autocheck_log, 'w') as fh:
            for x in final_result:
                fh.writelines(r"- Failed Cases:[{}] {} \n".format(','.join(final_result[x]), x))
            LOG.info("saved to {}".format(autocheck_log))
    else:
        with open(autocheck_log, 'w') as fh:
            fh.writelines("All tests Pass\n")
            LOG.info("saved to {}".format(autocheck_log))

if __name__ == '__main__':
    #walk_dir('.')
    for i in walk_dir(ARGS.log_dir):
        item_writer(i)
    get_fails(RESULT_JSON)