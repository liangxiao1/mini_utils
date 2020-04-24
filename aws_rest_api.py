#!/usr/bin/env python
'''
github : https://github.com/liangxiao1/mini_utils

This tool is setup a quick flask server with restapi provided.
It is a lightweight solution if you do not want to share awscli tokens with other for tempary access.
Others can reboot/start/stop/terminate/ssh login to aws instances without knowing tokens.
It does not allow to create new instance for resource controlling purpose.
Please ask account owner start a instance and send instance id to you.

'''
from flask import Flask, send_file, render_template_string
from flask_restful import Resource, Api, reqparse
import boto3
from botocore.exceptions import ClientError
import time

parser = reqparse.RequestParser()
parser.add_argument('instanceid', type=str, help='instance id')
parser.add_argument('region', type=str, help='region, default us-west-2')

app = Flask(__name__)
api = Api(app)

TASKS = {
    'status': 'status of an instance',
    'stop': 'stop an instance',
    'start': 'start an instance',
    'reboot': 'stop and start an instance',
    'terminate': 'destroy an instance',
    'console': 'get console log from an instance',
    'download': 'download ssh key file for login to this instance'  
}

class TasksList(Resource):
    def get(self):
        return TASKS

class Status(Resource):
    def get(self):
        # Default to 200 OK
        args = parser.parse_args(strict=True)
        instanceid = args['instanceid']
        if instanceid == None:
            return {'Error': "which instanceid do you get?"}
        region = args['region']
        if region == None:
            region = 'us-west-2'
        try:
            ec2 = boto3.resource('ec2', region_name=region)
            instance = ec2.Instance(instanceid)
            instance.reload()
            instance.state
        except ClientError as err:
            return {instanceid: '%s' % err}
        return {'instanceid': instanceid,
               'state': instance.state,
               'IP':instance.public_ip_address}

class Start(Resource):
    def get(self):
        # Default to 200 OK
        args = parser.parse_args(strict=True)
        instanceid = args['instanceid']
        if instanceid == None:
            return {'Error': "which instanceid do you get?"}
        region = args['region']
        if region == None:
            region = 'us-west-2'
        try:
            ec2 = boto3.resource('ec2', region_name=region)
            instance = ec2.Instance(instanceid)
            instance.reload()
            instance.start()
            instance.wait_until_running()
            instance.reload()
            instance.state
        except ClientError as err:
            return {instanceid: '%s' % err}
        return {'instanceid': instanceid,
               'state': instance.state,
               'IP':instance.public_ip_address}

class Stop(Resource):
    def get(self):
        # Default to 200 OK
        args = parser.parse_args(strict=True)
        instanceid = args['instanceid']
        if instanceid == None:
            return {'Error': "which instanceid do you get?"}
        region = args['region']
        if region == None:
            region = 'us-west-2'
        try:
            ec2 = boto3.resource('ec2', region_name=region)
            instance = ec2.Instance(instanceid)
            instance.reload()
            instance.stop()
            instance.wait_until_stopped()
            instance.reload()
            instance.state
        except ClientError as err:
            return {instanceid: '%s' % err}
        return {'instanceid': instanceid,
               'state': instance.state,
               'IP':instance.public_ip_address}

class Reboot(Resource):
    def get(self):
        # Default to 200 OK
        args = parser.parse_args(strict=True)
        instanceid = args['instanceid']
        if instanceid == None:
            return {'Error': "which instanceid do you get?"}
        region = args['region']
        if region == None:
            region = 'us-west-2'
        try:
            ec2 = boto3.resource('ec2', region_name=region)
            instance = ec2.Instance(instanceid)
            instance.reload()
            instance.stop()
            instance.wait_until_stopped()
            instance.start()
            instance.wait_until_running()
            instance.reload()
            instance.state
        except ClientError as err:
            return {instanceid: '%s' % err}
        return {'instanceid': instanceid,
               'state': instance.state,
               'IP':instance.public_ip_address}

class Terminate(Resource):
    def get(self):
        # Default to 200 OK
        args = parser.parse_args(strict=True)
        instanceid = args['instanceid']
        if instanceid == None:
            return {'Error': "which instanceid do you get?"}
        region = args['region']
        if region == None:
            region = 'us-west-2'
        try:
            ec2 = boto3.resource('ec2', region_name=region)
            instance = ec2.Instance(instanceid)
            instance.reload()
            instance.terminate()
            instance.wait_until_terminated()
            instance.reload()
            instance.state
        except ClientError as err:
            return {instanceid: '%s' % err}
        return {'instanceid': instanceid,
               'state': instance.state}

class Console(Resource):
    def get(self):
        # Default to 200 OK
        args = parser.parse_args(strict=True)
        instanceid = args['instanceid']
        if instanceid == None:
            return {'Error': "which instanceid do you get?"}
        region = args['region']
        if region == None:
            region = 'us-west-2'
        try:
            ec2 = boto3.resource('ec2', region_name=region)
            instance = ec2.Instance(instanceid)
            instance.reload()
            for i in range(10):
                console = instance.console_output()
                try:
                    console['Output']
                    break
                except Exception as err:
                    console['Output']="Please try later as delay in console output"
                    time.sleep(2)
                    continue
            instance.reload()
            instance.state
        except ClientError as err:
            return {instanceid: '%s' % err}

        return {'instanceid': instanceid,
                'state':instance.state,'console':console['Output']}

class SSHKEY(Resource):
    def get(self):
        path = "data/guest_s1.pem"
        return send_file(path, as_attachment=True)

api.add_resource(TasksList, '/ops','/')
api.add_resource(Status, '/ops/status')
api.add_resource(Stop, '/ops/stop')
api.add_resource(Start, '/ops/start')
api.add_resource(Reboot, '/ops/reboot')
api.add_resource(Terminate, '/ops/terminate')
api.add_resource(Console, '/ops/console')
api.add_resource(SSHKEY, '/ops/download')

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5901, debug=True)