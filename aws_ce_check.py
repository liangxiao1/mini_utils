#!/usr/bin/env python
'''
github : https://github.com/liangxiao1/mini_utils

Retrive cost and usage on aws.
'''
from datetime import datetime, timezone, date
import argparse
import string
import concurrent.futures
import sys
try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    print("Please install boto3")
    sys.exit(1)

from tipset.libs import aws_libs
import email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
import logging
LOG_FORMAT = '%(asctime)s:%(levelname)s:%(message)s'
MAIL_TEXT_TEMPLATE = string.Template('''
Hello,

Here is monthly cost report from $start_date to $end_date of Linux-QE-AWS for your reference.
$body
Note: this message is sent by auto for knowing the cost usage by month.

Rgs,
Frank
''')
MAIL_HTML_TEMPLATE = string.Template('''
<html>
  <head>
    <style type="text/css" media="screen">
      table, th, td {
      border: 1px solid black;
        border-collapse: collapse;
       }
       td.cell{
          background-color: white;
      }
    </style>
  </head>
  <body>
    <p>Hello,</p>
    <p>Here is monthly cost report from $start_date to $end_date of Linux-QE-AWS for your reference.</p>
    <table id="result" class="table">
      <thead>
        <tr><th>TimePeriod</th><th>Amount</th></tr>
      </thead>
      <tbody>
        $body
      </tbody>
    </table>
    <p>Note: this message is sent by auto for knowing the cost usage by month.</p>
    <p></p>
    <p>Rgs,</p>
    <p>Frank</p>
  </body>
</html>
''')

def send_mail(content=None, html_content=None, end_date=None):
    #msg = email.message.EmailMessage()
    msg = MIMEMultipart('alternative')
    msg['Subject'] = 'Monthly cost report of Linux-QE-AWS ({})'.format(end_date)
    msg['From'] = 'xiliang@redhat.com'
    msg['To'] = 'xiliang@redhat.com'
    #msg.set_content(content)
    if content:
        msg.attach(MIMEText(content, 'plain'))
    if html_content:
        msg.attach(MIMEText(html_content, 'html'))
        #msg.add_alternative(html_content)
    
    server = smtplib.SMTP('smtp.redhat.com')
    #server.set_debuglevel(1)
    #server.sendmail('xiliang@redhat.com', 'xiliang@redhat.com', msg)
    server.send_message(msg)
    server.quit()

def main():
    parser = argparse.ArgumentParser('Retrive cost and usage on aws')
    parser.add_argument('--start_date', dest='start_date', action='store',\
        help='The beginning of the time period.', required=False)
    parser.add_argument('--end_date', dest='end_date', action='store',default=None,\
        help='The end of the time period.', required=False)
    parser.add_argument('--granularity', dest='granularity', action='store', default='MONTHLY',\
        help='DAILY, MONTHLY or HOURLY', required=False)
    parser.add_argument('-d', dest='is_debug', action='store_true',\
        help='optional, run in debug mode', required=False, default=False)
    parser.add_argument('--profile', dest='profile', default='default', action='store',
        help='option, profile name in aws credential config file, default is default', required=False)
    parser.add_argument('--metrics', dest='metrics', default='BlendedCost', action='store',
        help='AmortizedCost,BlendedCost,NetAmortizedCost,NetUnblendedCost,NormalizedUsageAmount,UnblendedCost and UsageQuantity', required=False)
    args = parser.parse_args()

    log = logging.getLogger(__name__)
    if args.is_debug:
        logging.basicConfig(level=logging.DEBUG, format=LOG_FORMAT)
    else:
        logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    if args.start_date:
        start_date = args.start_date
    else:
        tmp_date = date.today().replace(year=date.today().year - 1)
        start_date = tmp_date.strftime("%Y-%m-%d")
    if args.end_date:
        end_date = args.end_date
    else:
        end_date = date.today().strftime("%Y-%m-%d")
    print(start_date,end_date)
    client = boto3.client('ce')
    _, client = aws_libs.aws_init_key(profile=args.profile, log=log, client_type='ce')
    cost_all = client.get_cost_and_usage(
        TimePeriod={
        'Start': start_date,
        'End': end_date
    },
    Granularity=args.granularity,
    Metrics=args.metrics.split(',')
    )
    log.info(cost_all)
    text_body = ''
    html_body = ''
    for month in reversed(cost_all['ResultsByTime']):
        text_body += "TimePeriod:{}~{} Amount:{:0.2f} {}\n".format(month['TimePeriod']['Start'],
                month['TimePeriod']['End'],float(month['Total']['BlendedCost']['Amount']),month['Total']['BlendedCost']['Unit'])
        html_body += "<tr><td>{}~{}</td> <td>{:0.2f} {}</td></tr>".format(month['TimePeriod']['Start'],
                month['TimePeriod']['End'],float(month['Total']['BlendedCost']['Amount']),month['Total']['BlendedCost']['Unit'])

    send_mail(content=MAIL_TEXT_TEMPLATE.substitute(start=month['TimePeriod']['Start'],end=month['TimePeriod']['End'],body=text_body,start_date=start_date,end_date=end_date,),
    html_content=MAIL_HTML_TEMPLATE.substitute(start=month['TimePeriod']['Start'],end=month['TimePeriod']['End'],body=html_body,start_date=start_date,end_date=end_date),end_date=end_date)

if __name__ == '__main__':
    main()
