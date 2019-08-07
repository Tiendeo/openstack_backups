
import argparse
import subprocess
import re
import os
from datetime import datetime
import time


EXECUTION_TIMESTAMP_UTC = datetime.utcnow().strftime('%Y%m%d%H%M%S')
DESIRED_POWER_STATUS = 'Running'
OPENSTACK_RUNNING_STATUS = 'Running'
OPENSTACK_SHUTDOWN_STATUS = 'Shutdown'
OPENSTACK_DETACHED_STATUS = 'available'
OPENSTACK_ATTACHED_STATUS = 'in-use'
OPENSTACK_BASE_CMD = 'openstack'


def get_create_image_args():
    parser = argparse.ArgumentParser(
        description='An openstack wrapper written in python which creates an snapshot of the targeted server')
    parser.add_argument('-s', '--server', required=True,
                        type=str, help='Name of the target server/instance')
    parser.add_argument('-c', '--cloud', required=False,
                        type=str, help='Openstack cloud name to get configuration from clouds.yaml')
    parser.add_argument('-r', '--region', required=False,
                        type=str, help='Openstack region where the server name is running')
    return parser.parse_args()


# COMMON
def set_openstack_base_command(cloud, region):
    global OPENSTACK_BASE_CMD
    if cloud:
        OPENSTACK_BASE_CMD = OPENSTACK_BASE_CMD + ' --os-cloud {cloud}'.format(cloud=cloud)
    if region:
        OPENSTACK_BASE_CMD = OPENSTACK_BASE_CMD + ' --os-region-name {region}'.format(region=region)


def execute_command(complete_command):
    print("Launching subprocess: '{cmd}'".format(cmd=complete_command))
    return subprocess.run(complete_command.split(' '), capture_output=True, text=True)


def execute_openstack_command(openstack_arguments):
    global OPENSTACK_BASE_CMD
    return execute_command(OPENSTACK_BASE_CMD +' '+openstack_arguments)


def validate_results(comleted_process, error_message):
    if comleted_process.returncode != 0:
        print(error_message)
        print("STERR: {sterr}".format(sterr=comleted_process.stderr))
        return False
    return True


# SERVER
def wait_server_status(server_name, desired_status, timeout=300):
    final_time = time.time() + timeout
    server_in_desired_status = check_server_status(server_name, desired_status)
    while not server_in_desired_status and time.time() < final_time:
        time.sleep(60)
        server_in_desired_status = check_server_status(server_name, desired_status)
    return server_in_desired_status


def get_server_status(server_name):
    openstack_args = 'server show -c OS-EXT-STS:power_state -f value {server}'.format(server=server_name)
    command_result = execute_openstack_command(openstack_args)
    if validate_results(command_result, "ERROR: getting server status"):
        return command_result.stdout


def check_server_status(server_name, desired_status):
    return desired_status in get_server_status(server_name)


def stop_server_and_wait(server_name):
    if not check_server_status(server_name, OPENSTACK_SHUTDOWN_STATUS):
        return stop_server(server_name) and wait_server_status(server_name, OPENSTACK_SHUTDOWN_STATUS)
    return True


def stop_server(server_name):
    # TO-DO: Is this stop a nice shutdown?
    openstack_args = 'server stop {server}'.format(server=server_name)
    return validate_results(execute_openstack_command(openstack_args), "ERROR: stopping the server")


def start_server_and_wait(server_name):
    if not check_server_status(server_name, OPENSTACK_RUNNING_STATUS):
        return start_server(server_name) and wait_server_status(server_name, OPENSTACK_RUNNING_STATUS)
    return True


def start_server(server_name):
    openstack_args = 'server start {server}'.format(server=server_name)
    return validate_results(execute_openstack_command(openstack_args), "ERROR: starting the server")


def create_server_backup(server_name):
    image_name = '{server}_{suffix}'.format(server=server_name, suffix=EXECUTION_TIMESTAMP_UTC)
    openstack_args = 'server backup create --name {backup} --wait {server}'.format(backup=image_name, server=server_name)
    print("START: Creating image for {server}...".format(server=server_name))
    validate_results(execute_openstack_command(openstack_args), "ERROR: backing up server")
    print("END: Creating image for {server}...".format(server=server_name))


# SERVER - VOLUMES
def get_server_attached_volumes(server_name):
    openstack_args = 'server show -c volumes_attached -f value {server}'.format(server=server_name)
    return volumes_attached_response_to_list(execute_openstack_command(openstack_args))


def volumes_attached_response_to_list(completed_process):
    pattern = re.compile("^id='([0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})'$")
    volumes = []
    if validate_results(completed_process, "ERROR: obtaining volumes"):
        for stout_line in completed_process.stdout.split('\n'):
            volume_id_match = pattern.match(stout_line)
            if volume_id_match:
                volumes.append(volume_id_match.group(1))
    return volumes


def get_server_detached_volumes(server_name, volumes):
    return list(set(volumes) - set(get_server_attached_volumes(server_name)))


def detach_volumes(server_name, volume_id_list):
    execution_success = True
    for volume_id in volume_id_list:
        execution_success = execution_success and detach_volume(server_name, volume_id)
    for volume_id in volume_id_list:
        execution_success = execution_success and wait_volume_status(volume_id, OPENSTACK_DETACHED_STATUS)
    return execution_success


def detach_volume(server_name, volume_id):
    openstack_args = 'server remove volume {server} {volume}'.format(volume=volume_id, server=server_name)
    return validate_results(execute_openstack_command(openstack_args), "ERROR: detaching volume from the server")


def wait_volume_status(volume, desired_status, timeout=300):
    final_time = time.time() + timeout
    volume_is_in_desired_status = check_volume_status(volume, desired_status)
    while not volume_is_in_desired_status and time.time() < final_time:
        time.sleep(60)
        volume_is_in_desired_status = check_volume_status(volume, desired_status)
    return volume_is_in_desired_status


def check_volume_status(volume_id, desired_status):
    openstack_args = 'volume show -c status -f value {volume}'.format(volume=volume_id)
    output = execute_openstack_command(openstack_args)
    if validate_results(output, "ERROR Checking volume status"):
        return False
    return output.stdout in desired_status


def attach_volumes(server_name, volume_id_list):
    execution_success = True
    for volume_id in volume_id_list:
        execution_success = execution_success and attach_volume(server_name, volume_id)
    for volume_id in volume_id_list:
        execution_success = execution_success and wait_volume_status(volume_id, OPENSTACK_ATTACHED_STATUS)
    return execution_success


def attach_volume(server_name, volume_id):
    openstack_args = 'server add volume {server} {volume}'.format(volume=volume_id, server=server_name)
    return validate_results(execute_openstack_command(openstack_args), "ERROR: attaching volume to the server")


def create_volumes_backup(server_name, volume_id_list):
    result = True
    for volume_id in volume_id_list:
        result = result and create_volume_backup(server_name, volume_id)
    return result


def create_volume_backup(server_name, volume_id):
    backup_name = 'DSK_{server}_{suffix}'.format(server=server_name, suffix=EXECUTION_TIMESTAMP_UTC)
    openstack_args = 'volume snapshot create --volume {volume} {backup}'.format(backup=backup_name, volume=volume_id)
    print("START: Creating image for volume {volume}...".format(volume=volume_id))
    result = validate_results(execute_openstack_command(openstack_args), "ERROR: creating a volume backup")
    if result:
        print("END: Creating image for {volume}...".format(volume=volume_id))
    return result


def prepare_instance_for_backup(server_name):
    if not stop_server_and_wait(server_name):
        restore_server_initial_status(server_name)
        exit(1)


def prepare_volumes_for_backup(server_name, volumes):
    if not detach_volumes(server_name, volumes):
        restore_volumes_initial_status(server_name, volumes)
        restore_server_initial_status(server_name)
        exit(1)


def restore_volumes_initial_status(server_name, volumes):
    server_detached_volumes = get_server_detached_volumes(server_name, volumes)
    if not attach_volumes(server_name, server_detached_volumes):
        exit(1)


def restore_server_initial_status(server_name):
    if DESIRED_POWER_STATUS in OPENSTACK_RUNNING_STATUS:
        if not start_server_and_wait(server_name):
            exit(1)


def create_server_and_volumes_backup(server_name):
    global DESIRED_POWER_STATUS
    DESIRED_POWER_STATUS = get_server_status(server_name)
    volumes = get_server_attached_volumes(server_name)
    prepare_instance_for_backup(server_name)
    prepare_volumes_for_backup(server_name, volumes)
    backup_result = create_volumes_backup(server_name, volumes) and create_server_backup(server_name)
    restore_volumes_initial_status(server_name, volumes)
    restore_server_initial_status(server_name)
    if not backup_result:
        exit(1)


def main():
    args = get_create_image_args()
    set_openstack_base_command(args.cloud, args.region)
    create_server_and_volumes_backup(args.server)


if __name__ == "__main__":
    main()
