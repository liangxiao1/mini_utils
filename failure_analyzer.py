# /usr/bin/env python
'''
Check a failure is regression or not.
github : https://github.com/liangxiao1/mini_utils

'''
from __future__ import print_function
import json
import sys
import re
import argparse
import logging
from sqlalchemy import create_engine
from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text, Date
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import relationship
import sqlalchemy
import difflib
from collections import deque
import heapq
import math
import pdb



DB_BASE = declarative_base()

# pylint: disable=R0902,R0903

class FailureType(DB_BASE):
    '''
    general use: table for specify failure types, eg. product_bug, tool_bug, env_bug
    '''
    __tablename__ = 'failure_type'
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(String(150), unique=True, nullable=True)

    def __repr__(self):
        return self.name

    sqlite_autoincrement = True


class FailureStatus(DB_BASE):
    '''
    general use: table for specify failure status, like closed, open, on_qa, verified, blocker
    '''
    __tablename__ = 'failure_status'
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(String(150), unique=True, nullable=True)

    def __repr__(self):
        return self.name

    sqlite_autoincrement = True

class Bugs(DB_BASE):
    '''
    general use: table for recording all test failures.
    '''
    __tablename__ = 'bugs'
    id = Column(Integer, primary_key=True)
    test_suite = Column(String(50))
    case_name = Column(String(50))
    bug_id = Column(Integer,nullable=True)
    bug_title = Column(String(200),nullable=True)
    failure_id = Column(Integer, ForeignKey("failure_status.id"), nullable=False)
    failure_status = relationship("FailureStatus")
    branch_name = Column(String(50),nullable=True)
    comments = Column(Text)
    last_update =  Column(Date)
    create_date =  Column(Date)
    failure_type_id = Column(Integer, ForeignKey("failure_type.id"), nullable=False)
    failure_type = relationship("FailureType")
    identify_keywords = Column(Text)
    identify_debuglog = Column(Text)
    contactor = Column(String(50),nullable=True)
    sqlite_autoincrement = True

def log_analyze(db_file=None, log_file=None, case_name=None, LOG=None):
    DB_ENGINE = create_engine('sqlite:///%s' % db_file, echo=False) #echo=True to enable debug
    DB_SESSION = sessionmaker(bind=DB_ENGINE)
    session = DB_SESSION()
    debug_rate_list = []

    bottom_rate = 65
    tmp_failure_ids = []
    tmp_ave_rate = 0
    for bug in session.query(Bugs).order_by(Bugs.id):
        key_rate_list = []
        LOG.debug(bug.id, bug.case_name)
        #LOG.info("##########%s",bug.identify_keywords)
        if case_name is not None:
            if bug.case_name in case_name:
                LOG.debug("%s previous failure found, check whether log match" % bug.case_name)
        if log_file is not None:
            find_it = False
            ave_rate = 0
            #LOG.info(bug.identify_keywords.split('\n'))
            for baseline in bug.identify_keywords.split('\n'):
                tmp_list = []
                if baseline == '': continue
                with open(log_file) as file_handler:
                    for line in file_handler.readlines():
                        seq = difflib.SequenceMatcher(None, a=line, b=baseline)
                        same_rate = seq.ratio()*100
                        tmp_list.append(same_rate)
                    if len(tmp_list) > 0:
                        key_rate_list.append(heapq.nlargest(1,tmp_list)[0])
            LOG.debug("Key final rate: %s", key_rate_list)
            if len(key_rate_list) > 0:
                ave_rate = sum(key_rate_list)/len(key_rate_list)
                if ave_rate > tmp_ave_rate:
                    tmp_ave_rate = ave_rate
                    tmp_failure_ids.append(bug.id)
    if tmp_ave_rate > bottom_rate:
        LOG.debug("Find such failure in DB, continue to double check details......")
    else:
        LOG.info("No similar failure found!")
        return
    tmp_ave_rate = 0
    final_failure_id = None
    for bug in session.query(Bugs).order_by(Bugs.id):
        for tmp_failure_id in tmp_failure_ids:
            if tmp_failure_id == bug.id:
                for baseline in bug.identify_debuglog.split('\n'):
                    tmp_list = []
                    with open(log_file) as file_handler:
                        for line in file_handler.readlines():
                            if baseline == '': continue
                            seq = difflib.SequenceMatcher(None, a=line, b=baseline)
                            same_rate = seq.ratio()*100
                            tmp_list.append(same_rate)
                        if len(tmp_list) > 0:
                            debug_rate_list.append(heapq.nlargest(1,tmp_list)[0])
                    LOG.debug("Final rate: %s", debug_rate_list)
                    ave_rate = sum(debug_rate_list)/len(debug_rate_list)
                if ave_rate > tmp_ave_rate:
                    tmp_ave_rate = ave_rate
                    final_failure_id = bug.id
    if tmp_ave_rate > bottom_rate:
        LOG.debug("Find such failure in DB")
    else:
        LOG.info("No similar failure found!")
        return
    for bug in session.query(Bugs).order_by(Bugs.id):
        if final_failure_id == bug.id:
            failure_type = str(bug.failure_type)
            failure_status = str(bug.failure_status)
            if 'product_bug' in failure_type and bug.case_name in case_name:
                msg = ''
                if 'blocker' in failure_status:
                    msg = 'blocker'
                LOG.info("Product %sbug: %s:%s", msg, bug.bug_id, bug.bug_title)
                LOG.debug("Product %sbug: %s:%s same rate:%s", msg, bug.bug_id, bug.bug_title,ave_rate)
            elif 'env_bug' in failure_type:
                LOG.info("Environment bug: %s same rate:%s", bug.identify_keywords,ave_rate)
                LOG.debug("Environment bug: %s", bug.identify_keywords)
            elif 'tool_bug' in failure_type:
                LOG.info("Tool bug: %s", bug.identify_keywords)
                LOG.info("Tool bug: %s same rate:%s", bug.identify_keywords,ave_rate)
            else:
                LOG.info("No similar failure found, I will check manually!")

if __name__ == "__main__":
    ARG_PARSER = argparse.ArgumentParser(description="Log checking from existing db")
    ARG_PARSER.add_argument('--db_file', dest='db_file', action='store',
                            help="specify database location", default=None, required=True)
    ARG_PARSER.add_argument('-d', dest='is_debug', action='store_true',
        help='optional, run in debug mode', required=False, default=False)
    ARG_PARSER.add_argument("--log_file", dest='log_file', action='store',
                            help="specify log file", default=None, required=False)
    ARG_PARSER.add_argument("--case_name", dest='case_name', action='store',
                            help="specify case_name", default=None, required=False)
    ARGS = ARG_PARSER.parse_args()
    LOG = logging.getLogger(__name__)
    if ARGS.is_debug:
        logging.basicConfig(level=logging.DEBUG, format='%(levelname)s:%(message)s')
    else:
        logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(message)s')

    log_analyze(db_file=ARGS.db_file, log_file=ARGS.log_file, case_name=ARGS.case_name, LOG=LOG)