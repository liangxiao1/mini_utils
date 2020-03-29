#!/usr/bin/env python3
import logging
import socket
import subprocess
import sys
import time
from xml.etree.ElementTree import parse, Element

log = logging.getLogger(__name__)
is_debug = True
if is_debug:
    logging.basicConfig(level=logging.DEBUG,format="%(levelname)s:%(message)s")
else:
    logging.basicConfig(level=logging.INFO,format="%(levelname)s:%(message)s")

def update_location():
    '''
    update Jenkins URL to currrent location according to ip address
    '''
    jenkins_file = "/etc/sysconfig/jenkins"
    jenkins_home = None
    with open(jenkins_file) as fh:
        for line in fh.readlines():
            if line.startswith('JENKINS_HOME'):
                jenkins_home = line.split('=')[-1].strip('\n').strip('"')
                log.info("Find jenkins home: %s", jenkins_home)

    if jenkins_home is None:
        log.info("jenkins home not found!")
        sys.exit(1)
    location_file = jenkins_home + '/jenkins.model.JenkinsLocationConfiguration.xml'
    doc = parse(location_file)

    for i in range(60):
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        if "127.0.0.1" not in local_ip:
            break
        log.info("try again to get public ip")
        subprocess.check_output("systemctl restart NetworkManager", stderr=subprocess.STDOUT, shell=True)
        time.sleep(1)
    log.info("Local IP: %s", local_ip)

    root = doc.getroot()
    e = root.find('jenkinsUrl')
    #e = Element('jenkinsUrl')
    log.info(e.text)
    if local_ip not in e.text:     
        e.text = 'http://%s:8080/' % local_ip
        doc.write(location_file,xml_declaration=True)
        log.info("Updated jenkins url to %s", e.text )
        cmd = 'systemctl restart jenkins'
        subprocess.check_output(cmd, stderr=subprocess.STDOUT, shell=True)
    else:
        log.info("No need to update jenkins url." )
    subprocess.check_output("generate_key_data.sh", stderr=subprocess.STDOUT, shell=True)
if '__main__' == __name__:
    update_location()