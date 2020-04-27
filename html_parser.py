#!/usr/bin/env python
'''
github : https://github.com/liangxiao1/mini_utils

This tool is for get element value from html.

'''
import json
from bs4 import BeautifulSoup
import os
import sys
from urllib import urlopen
import logging
import argparse
import string
import re

parser = argparse.ArgumentParser('Script for get info from html')
parser.add_argument('--url',dest='url',action='store',help='specify url',default=None,required=True)
parser.add_argument('--keyword',dest='keyword',action='store',help='specify keyword you are looking for',default=None,required=True)
parser.add_argument('--must_key',dest='must_key',action='store',help='must have keys',default=None,required=False)
parser.add_argument('--notkeyword',dest='notkeyword',action='store',help='specify keyword you are not looking for',default=None,required=False)
parser.add_argument('--tag',dest='tag',action='store',help='optional specify prefix tag, default is JOB_',default='JOB_',required=False)
parser.add_argument('--name',dest='name',action='store',help='optional specify suffix name, default is PKGURL',default='PKGURL',required=False)
parser.add_argument('--dir', dest='file_dir', action='store', default='/tmp',
                            help='optional, output location, default is /tmp', required=False)
args=parser.parse_args()

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO,format="%(levelname)s:%(message)s")
url = args.url
keywords = args.keyword
must_keys = args.must_key
notkeywords = args.notkeyword
tag = args.tag
name = args.name
url_fh = urlopen(url)
html_src = url_fh.read()
with open('arch_taskinfo.txt','w') as fh:
    fh.writelines(html_src)
soup = BeautifulSoup(html_src,'lxml')
log.info("loading done")
JOB_DIR = args.file_dir
JOB_ENV_YAML = JOB_DIR+"/job_env.yaml"
JOB_ENV_TXT = JOB_DIR+"/job_env.txt"
results=[]
#s=soup.findAll('a',href=True)
#log.info(s)
#s=soup.findAll(string=re.compile("Package Name"),href=False)
#log.info(s)
#def walk_soup(soup):
#    if hasattr(soup,'children'):
#        for child in soup.children:
#            log.info(" %s",child.string)
#            #log.info(" %s",child)
#            if hasattr(child,'a'):
#                log.info("xiliang %s",child.a)
#            walk_soup(child)
#    else:
#        log.info("xiliang2 %s",soup)
#walk_soup(soup)
#s=soup.findAll('tr',href=False)
#for i in s:
#    log.info(i.get_text())
#    for child in i.children:
#        log.info(" %s",child.string)
s=soup.findAll('a',href=True)

for i in s:
    #log.info("name: %s, url: %s",i.get_text(),  i['href'])
    if notkeywords == None:
        if keywords != None:
            for keyword in keywords.split(','):
                if re.match('.*'+keyword+'.*', i['href']) != None:
                    log.info("found %s", i['href'])
                    results.append(i['href'])
    else:
        check_notkey = True
        for notkeyword in notkeywords.split(','):
            if re.match('.*'+notkeyword+'.*', i['href']) != None :
                check_notkey = False
        if must_keys != None:
            for must_key in must_keys.split(','):
                if re.match('.*'+must_key+'.*', i['href']) == None :
                    check_notkey = False
        if keywords != None:
            for keyword in keywords.split(','):
                if re.match('.*'+keyword+'.*', i['href']) != None and check_notkey:
                    log.info("found %s", i['href'])
                    results.append(i['href'])

with open(JOB_ENV_YAML, 'a') as fh:
    fh.write("%s%s: %s\n"% (tag, name, ','.join(results)))
    log.info("Write to %s", JOB_ENV_YAML)
with open(JOB_ENV_TXT, 'a') as fh:
    fh.write("%s%s=%s\n"% (tag, name,','.join(results)))
    log.info("Write to %s", JOB_ENV_TXT)
