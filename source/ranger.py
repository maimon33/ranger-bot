import re
import os
import sys
import json
import queue
import socket
import difflib
import getpass
import threading
import time as Time

import smtplib
import urllib.request

from prettytable import PrettyTable
from datetime import time, date, timedelta, datetime

import boto3
import click

from botocore.exceptions import ClientError

import utils

CURRENT_FILE = sys.argv[0]
USERNAME = getpass.getuser()
USER_HOME = os.getenv("HOME")
HOSTNAME = socket.gethostname()

try:
    urllib.request.urlopen('http://www.google.com', timeout=1)
    PUBLIC_IP = json.load(urllib.request.urlopen('http://jsonip.com'))['ip']
except (urllib.error.URLError, socket.timeout):
    PUBLIC_IP = ""

AWS_RANGER_HOME = '{0}/.ranger'.format(USER_HOME)
BOTO_CREDENTIALS = '{0}/.aws/credentials'.format(USER_HOME)


def run_func_in_threads(thread_func, list_of_args=None):
    queue_res = queue.Queue()
    list_of_args.append(queue_res)
    t = threading.Thread(target=thread_func, args=tuple(list_of_args))
    t.start()
    t.join()
    result = queue_res.get()
    return result

def find_profiles(file=None):
    if not file:
        file = ""
    profiles_list = []
    try:
        boto_config = open(file).read()
        for match in re.findall("\[.*\]", boto_config):
            profiles_list.append(match.strip("[]"))
        return profiles_list
    except IOError:
        return ["default"]

def validate_ranger(ranger_home):
    if not os.path.exists(ranger_home):
        print(' Missing ranger HOME dir...\n Run:\n'\
              ' ranger --init or create it yourself at ~/.ranger')
        sys.exit()
        
def create_short_instances_dict(all_instances_dictionary, 
                                execute_action, 
                                service=False):
    instance_dict ={}

    for region in all_instances_dictionary.items():
        instances_ids_list = []
        stopped_instances_ids = []
        running_instances_ids = []
        managed_instances_ids = []
        
        for instance in region[1]:
            if instance['ranger state'] == "excluded":
                continue
            
            if instance['State'] == "running" and \
                instance['ranger state'] != "managed":
                running_instances_ids.append(instance["_ID"])

            if instance['State'] in ["running", "stopped"] and \
                instance['ranger state'] == "managed":
                managed_instances_ids.append(instance["_ID"])

            if instance['State'] == "stopped":
                stopped_instances_ids.append(instance["_ID"])

        if service:
            instance_dict[region[0]] = managed_instances_ids
        else:
            if execute_action == "start":
                instances_ids_list = managed_instances_ids + \
                                     stopped_instances_ids
                instance_dict[region[0]] = instances_ids_list
            if execute_action == "stop":
                instances_ids_list = managed_instances_ids + \
                                     running_instances_ids
                instance_dict[region[0]] = instances_ids_list
            if execute_action == "terminate":
                instances_ids_list  = managed_instances_ids + \
                                      running_instances_ids + \
                                      stopped_instances_ids
            instance_dict[region[0]] = instances_ids_list

    return instance_dict

def create_state_dictionary(dictionary):
    state_file_dictionary = {}

    for region in dictionary.items():
        region_instances = []

        for instance in region[1]:
            if instance['ranger state'] == "excluded":
                region_instances.append(instance)
            elif instance['State'] == "running":
                instance['ranger state'] = "managed"
                region_instances.append(instance)
            elif instance['State'] == "stopped" and \
                instance['ranger state'] != "managed":
                instance['ranger state'] = "ignored"
                region_instances.append(instance)
        state_file_dictionary[region[0]] = region_instances
    return state_file_dictionary

def confirm_state_file(file_path):
    try:
        state_file = read_json_file(file_path)
        schedule = state_file['_schedule']
        return True
    except ValueError:
        print(' State file corrupted. Create new by using --init\n ')
        sys.exit()
    except IOError:
        print("missing state file")
        sys.exit()

def read_json_file(json_file):
    try:
        return json.load(open(json_file))
    except IOError:
        return "File Missing"

def update_json_file(file_path, new_dictionary):
    try:
        orig_state_file = json.load(open(file_path))
    except (IOError, ValueError):
        orig_state_file = {}
    orig_state_file.update(new_dictionary)
    with open(file_path, 'w') as file:
        json.dump(orig_state_file, file, indent=4, sort_keys=True)

def update_instances_state_file(state_file, all_instances_dictionary):
    new_state_dict = {}
    instances_list = []
    current_instances_ids = []
    state_file_instances_ids = []

    state_dict = read_json_file(state_file)
    instances = create_state_dictionary(all_instances_dictionary)

    # Remove Schedule section for state evaluation
    state_dict.pop('_schedule', None)

    for region, state_instances_list in state_dict.items():
        for state_instance in state_instances_list:
            try:
                state_file_instances_ids.append(state_instance["_ID"])
            except TypeError:
                pass

    for region, current_instances_list in instances.items():
        for instance in current_instances_list:
            if instance["_ID"] in state_file_instances_ids:
                for state_instance in state_instances_list:
                    if state_instance["_ID"] == instance["_ID"]:
                        instances_list.append(state_instance)
            else:
                if instance['ranger state'] == "excluded":
                    instances_list.append(instance)
                elif instance["State"] == "running":
                    instance['ranger state'] == "managed"
                    instances_list.append(instance)
                elif instance["State"] == "stopped" and \
                    instance['ranger state'] != "managed":
                    instance['ranger state'] == "ignored"
                    instances_list.append(instance)
        new_state_dict[region] = instances_list
        update_dictionary(state_file, region, new_state_dict[region])

def update_instance_state(state_file, target_instances, key, value):
    state_dict = read_json_file(state_file)

    # Remove Schedule section for state evaluation
    schedule_info = state_dict['_schedule']
    state_dict.pop('_schedule', None)

    for region, state_instances_list in state_dict.items():
        for state_instance in state_instances_list:
            for instances in target_instances:
                if state_instance["_ID"] == instances:
                    try:
                        state_instance[key] = value
                    except KeyError:
                        pass
    
    state_dict['_schedule'] = schedule_info
    update_json_file(state_file, state_dict)

def remove_instance_from_state(state_file, region, target_instance):
    state_dict = read_json_file(state_file)

    # Remove Schedule section for state evaluation
    schedule_info = state_dict['_schedule']
    state_dict.pop('_schedule', None)

    for region, state_instances_list in state_dict.items():
        for state_instance in state_instances_list:
            if target_instance == state_instance["_ID"]:
                state_instances_list.remove(state_instance)

    state_dict['_schedule'] = schedule_info
    update_json_file(state_file, state_dict)

def update_dictionary(file_path, section, keys_and_values):
    try:
        state_file = json.load(open(file_path))
    except ValueError:
        print("Corrupted json file")
        sys.exit()
    state_file[section] = keys_and_values
    with open(file_path, 'w') as file:
        json.dump(state_file, file, indent=4, sort_keys=True)

def assume_aws_role(accountid):
    try:
        response = boto3.client("sts").assume_role(DurationSeconds=3600, 
                                                ExternalId="watcher-temp",
                                                RoleArn=ROLE_ARN.format(accountid),
                                                RoleSessionName="Watcher")
        os.environ["AWS_ACCESS_KEY_ID"] = response["Credentials"]["AccessKeyId"]
        os.environ["AWS_SECRET_ACCESS_KEY"] = response["Credentials"]["SecretAccessKey"]
        os.environ["AWS_SESSION_TOKEN"] = response["Credentials"]["SessionToken"]
    except ClientError as e:
        print('Unable to Assume role\n'
        'Review to origin Creds [IAM role, AWS keys]')
        sys.exit()

def get_current_account_id():
    return boto3.client('sts').get_caller_identity().get('Account')

class AWSRanger(object):
    def __init__(self, profile_name):
        try:
            self.aws_client(resource=False, 
                            profile_name=None).describe_regions()
        except ClientError as e:
            print('Failed to Authenticate your AWS account\n'
            'Review your boto credentials file at ~/.aws/credentials')
            sys.exit()

    def aws_client(self, 
                   resource=True,
                   profile_name=None,
                   region_name="eu-west-1",
                   aws_service="ec2"):
        
        if not profile_name:
            session = boto3.Session()
        else:
            session = boto3.Session(profile_name=profile_name)

        if resource:
            return session.resource(aws_service, region_name=region_name)
        else:
            return session.client(aws_service, region_name=region_name)
        
    def get_all_regions(self):
        region_list = []
        response = self.aws_client(resource=False).describe_regions()['Regions']
        for region in response:
            region_api_id = region['Endpoint'].split('.')[1]
            region_list.append(region_api_id)
        return region_list

    def convert_region_name(self, region_endpoint):
        return self.aws_client(resource=False, aws_service="ssm").get_parameter(
            Name='/aws/service/global-infrastructure/regions/{}/longName'.format(
                region_endpoint))['Parameter']['Value']

    def get_instance_os(self, region, instanceid):
        instance = self.aws_client(
            resource=False,
            region_name=region).describe_instances(Filters=[{'Name': 'instance-id', 'Values': [instanceid]}])
        instance_ami = instance["Reservations"][0]["Instances"][0]["ImageId"]
        ami_os = self.aws_client(
            resource=False,
            region_name=region).describe_images(Filters=[{'Name': 'image-id', 'Values': [instance_ami]}])
        try:
            return ami_os["Images"][0]["PlatformDetails"].split("/")[0]
        except KeyError:
            return ami_os["Images"][0]["Name"].split("/")[0]
    
    def get_price(self, region, instance_type, os):
        FLT = '[{{"Field": "tenancy", "Value": "shared", "Type": "TERM_MATCH"}},'\
            '{{"Field": "operatingSystem", "Value": "{o}", "Type": "TERM_MATCH"}},'\
            '{{"Field": "preInstalledSw", "Value": "NA", "Type": "TERM_MATCH"}},'\
            '{{"Field": "instanceType", "Value": "{t}", "Type": "TERM_MATCH"}},'\
            '{{"Field": "locationType", "Value": "AWS Region", "Type": "TERM_MATCH"}},'\
            '{{"Field": "capacitystatus", "Value": "Used", "Type": "TERM_MATCH"}}]'

        f = FLT.format(t=instance_type, o=os)
        data = self.aws_client(
            resource=False, 
            region_name='us-east-1', 
            aws_service='pricing').get_products(
                ServiceCode='AmazonEC2', Filters=json.loads(f))
        od = json.loads(data['PriceList'][0])['terms']['OnDemand']
        id1 = list(od)[0]
        id2 = list(od[id1]['priceDimensions'])[0]
        return od[id1]['priceDimensions'][id2]['pricePerUnit']['USD']

    def fetch_instances(self, instance_state, region=False):
        return self.aws_client(region_name=region).instances.filter(
            Filters=[{'Name': 'instance-state-name', 
                      'Values': instance_state}])

    def get_bill(self, year, month, last_day_in_month):
        if len(str(month)) < 2:
            month = f'0{month}'
        response = self.aws_client(
            resource=False, 
            region_name='us-east-1', 
            aws_service='ce').get_cost_and_usage(
                TimePeriod={'Start': f'{year}-{month}-01','End': f'{year}-{month}-{last_day_in_month}'},
                Granularity='MONTHLY', Metrics=['AmortizedCost'])
        cost = response['ResultsByTime'][0]['Total']['AmortizedCost']['Amount']
        cost = utils.truncate(float(cost), 2)
        date = f'{month}/{year}'
        bill = f'{cost} $'
        return date, bill

    def get_bill_by_month(self, current_month=True, queue=None):
        year, month, last_day_in_month = utils.get_current_date(current=current_month)
        date, bill = self.get_bill(year=year, month=month, last_day_in_month=last_day_in_month)
        queue.put((date, bill))
    
    def get_instances(self,
                      instances_state=["running", "stopped"],
                      region=False):
        all_instances = []
        region_list = []

        if region:
            region_list.append(region)
        else:
            for region in self.get_all_regions():
                try:
                    region_list.append(region)
                except ClientError:
                    print("Skipping region: {}".format(region))

        all_instances = {}

        for region in region_list:
            instances_list = []
            region_inventory = {}
            
            instances = self.fetch_instances(instances_state, region)
            for instance in instances:
                instance_dict = {}
                instance_dict['_ID'] = instance.id
                instance_dict['State'] = instance.state['Name']
                instance_dict['Type'] = instance.instance_type
                instance_cost = self.get_price(region, instance.instance_type, self.get_instance_os(region, instance.id))
                instance_dict['Cost per hour'] = instance_cost
                instance_dict['Public DNS'] = instance.public_dns_name
                instance_dict['Creation Date'] = str(instance.launch_time)
                instance_dict['ranger state'] = "new"
                instance_dict['Tags'] = instance.tags
                
                try:
                    instances_list.append(instance_dict)
                    continue
                except TypeError:
                    instance_dict['Tags'] = [{u'Value': 'none', u'Key': 'Tag'}]

                instances_list.append(instance_dict)
            all_instances[region] = instances_list
        return all_instances

    def update_tags(self, instance_list, tags_list, region):
        for instance in instance_list:
            self.aws_client(region_name=region).create_tags(
                Resources=[instance], Tags=tags_list)

    def start_instnace(self, instance_list, region=False):
        for instance in instance_list:
            print('Starting instance: {}'.format(instance))
            self.aws_client(region_name=region).instances.filter(
                InstanceIds=[instance]).start() 

    def stop_instnace(self, instance_list, region=False):
        for instance in instance_list:
            print('Stopping instance: {}'.format(instance))
            self.aws_client(region_name=region).instances.filter(
                InstanceIds=[instance]).stop()

    def terminate_instnace(self, instance_list, region=False):
        for instance in instance_list:
            print('Terminating instance: {}'.format(instance))
            self.aws_client(region_name=region).instances.filter(
                InstanceIds=[instance]).terminate()
    
    def executioner(self,
                    state_file,
                    instances,
                    region=False,
                    action="pass",
                    cron=False):
        
        tags_list = [{"Key":"ranger Host", 
                      "Value":"{0} @ {1}".format(HOSTNAME, PUBLIC_IP)},
                     {"Key":"ranger Last Action",
                      "Value":"{0} @ {1}".format(
                          action, Time.strftime("%Y-%m-%d %H:%M:%S"))},
                     {"Key":"ranger User",
                      "Value":USERNAME}]
        
        try:
            if action.lower() == 'stop':
                if cron:
                    stop_dictionary = instances
                else:
                    stop_dictionary = create_short_instances_dict(
                        instances, action.lower())
                for k, v in stop_dictionary.items():
                    self.stop_instnace(v, region=k)
                    self.update_tags(v, tags_list, region=k)
                    if cron:
                        update_instance_state(state_file, v, "State", "stopped")
            elif action.lower() == 'start':
                if cron:
                    start_dictionary = instances
                else:
                    start_dictionary = create_short_instances_dict(
                        instances, action.lower())
                for k, v in start_dictionary.items():
                    self.start_instnace(v, region=k)
                    self.update_tags(v, tags_list, region=k)
                    if cron:
                        update_instance_state(state_file, v, "State", "running")
            elif action.lower() == 'terminate':
                if cron:
                    terminate_dictionary = instances
                else:
                    terminate_dictionary = create_short_instances_dict(
                        instances, action.lower())
                for k, v in terminate_dictionary.items():
                    self.terminate_instnace(v, region=k)
                    if cron:
                        remove_instance_from_state(state_file, k, v)
                        pass
            elif action == 'pass':
                pass
        except AttributeError:
            pass
        except ClientError:
            pass


def ranger(init, region, table, execute):
    """Round up your AWS instances

    Scout for Instances in all AWS Regions
    """

    if not utils._internet_on():
        print("No Internet connection...")
        sys.exit()

    DEFAULT_AWS_PROFILE = find_profiles(BOTO_CREDENTIALS)[0]
    STATE_FILE = '{0}/{1}.state'.format(AWS_RANGER_HOME,
                                        DEFAULT_AWS_PROFILE)

    if init:
        if os.path.exists(AWS_RANGER_HOME):
            pass
        else:
            # print("Creating ranger Home")
            os.makedirs(AWS_RANGER_HOME)
    
    validate_ranger(AWS_RANGER_HOME)

    if region == "all":
        all_regions = True
    else:
        all_regions = False

    ranger = AWSRanger(profile_name=DEFAULT_AWS_PROFILE)

    if all_regions:
        region = None
    
    instances = {}
    instances = ranger.get_instances(region=region)
    
    account = get_current_account_id()

    if execute:
        ranger.executioner(instances, action=execute)
    
    if table:
        # print("Summery for Account ID: {}".format(account))
        x = PrettyTable()
        x.field_names = ["AWS Region", "# of instances"]
        if all_regions:
            for region in ranger.get_all_regions():
                if len(instances[region]) > 0:
                    x.add_row([ranger.convert_region_name(region), len(instances[region])])
        else:
            if len(instances[region]) > 0:
                x.add_row([ranger.convert_region_name(region), len(instances[region])])
            else:
                print("Region has no instance")
        # return x
        with open('report_output.txt', 'w') as w:
            w.write(str(x))
        return
    else:
        print(utils._format_json(instances))

def bill():
    DEFAULT_AWS_PROFILE = find_profiles(BOTO_CREDENTIALS)[0]
    ranger = AWSRanger(profile_name=DEFAULT_AWS_PROFILE)

    lastdate, lastbill = run_func_in_threads(thread_func=ranger.get_bill_by_month, list_of_args=[False])
    currentdate, currentbill = run_func_in_threads(thread_func=ranger.get_bill_by_month,  list_of_args=[True])
    REPORT_OUTPUT="""
Cost for {}: {}
Cost for {}: {}
""".format(lastdate, lastbill, currentdate, currentbill)
    with open('report_output.txt', 'w') as w:
        w.write(REPORT_OUTPUT)
    return


if __name__ == "__main__":
    ranger()