#!/usr/bin/python3

import asyncio
import os
import subprocess
import sys

import asyncssh

from helpers import (
    require_env, require_secrets, test_start,
    test_case_ctx, secret_get, test_case,
)
from helpers import __file__ as helpers_file
from host_tests import __file__ as host_tests_file


def _create_reboot_script(cold):
    # Reboot support in the worker uses "script" and not a "script-repo", so
    # we have to copy what we need in order to make this work:
    if cold:
        script = '/archive/execute-on-cold-reboot'
        arg = 'cold'
    else:
        script = '/archive/execute-on-reboot'
        arg = 'warm'
    with open(script, 'w') as fout:
        fout.write('#!/bin/sh -ex\n')
        fout.write('cat > /tmp/helpers.py <<EIEIO\n')
        with open(helpers_file) as f:
            fout.write(f.read())
        fout.write('EIEIO\n')

        fout.write('cat > /tmp/host_tests.py <<EIEIO\n')
        with open(host_tests_file) as f:
            fout.write(f.read())
        fout.write('EIEIO\n')

        fout.write('cat > /tmp/main.py <<EIEIO\n')
        with open(__file__) as f:
            fout.write(f.read())
        fout.write('EIEIO\n')
        fout.write('\nPYTHONUNBUFFERED=1 python3 /tmp/main.py %s\n' % arg)
        os.fchmod(fout.fileno(), 0o755)


def flash_main():
    from ota_api import device_get, update_device
    from host_tests import DEVICES

    test_start('ota-update')
    with test_case_ctx('ota-api') as log:
        name = os.environ['H_WORKER']
        owner = DEVICES[name][0]
        log('Looking up device: %s' % name)
        device = device_get(name, owner)
        log('Device image is: %s - %s' % (
            device['image']['name'], device['image']['hash']))
        log('Device status: %s' % device['status'])
        log('Last seen: %s' % device['last-seen'])
        log('Update stream: %s' % device['update-stream'])

    with test_case_ctx('find-test-hash') as log:
        url = os.environ['H_TRIGGER_URL'] + 'other/ostree.sha.txt'
        ostree_hash = secret_get(url, 'osftok', 'OSF-TOKEN').text.strip()

    with test_case_ctx('download-update') as log:
        update_device(log, device, ostree_hash)

    test_start('reboot')
    _create_reboot_script(True)


def _host_connect():
    # TEMP HACK. The lastest asyncssh wants to use ed25519, but that's not in
    # 3.8 version of alpine's openssl. Once we are one 3.9, we can remove
    kex_algs = ('diffie-hellman-group-exchange-sha256',)
    return asyncssh.connect('172.17.0.1', known_hosts=None,
                            username='osf', password='osf', kex_algs=kex_algs)


def ostree_hash():
    # find the ostree hash the device has booted into
    async def ssh():
        async with _host_connect() as conn:
            return await conn.run('ostree admin status')

    try:
        result = asyncio.get_event_loop().run_until_complete(ssh())
        for line in result.stdout.splitlines():
            if line[0] == '*':
                return line.split(' ')[-1][:-2]
        else:
            print('Unable to find active image in: ' + result.stdout)
    except (OSError, asyncssh.Error) as exc:
        print('SSH connection failed: ' + str(exc))


def _test_booted_image(label):
    dmesg = '/archive/dmesg-%s.log' % label
    print('Saving dmesg to %s' % dmesg)
    with open(dmesg, 'w') as f:
        subprocess.check_call(['/bin/dmesg'], stdout=f)

    result = 'PASSED'
    url = os.environ['H_TRIGGER_URL'] + 'other/ostree.sha.txt'
    desired_hash = secret_get(url, 'osftok', 'OSF-TOKEN').text.strip()
    found_hash = ostree_hash()
    if found_hash != desired_hash:
        print('Device booted into incorrect image: %s != %s' % (
            found_hash, desired_hash))
        result = 'FAILED'
    test_case('booted-image-' + label, result)


def cold_main():
    test_case('cold-reboot', 'PASSED')
    _test_booted_image('cold')
    _create_reboot_script(False)


def _run_host_tests():
    test_start('connectivity')

    worker = os.environ['H_WORKER']

    async def ssh():
        async with _host_connect() as conn:
            print('copying tests to host')
            await asyncssh.scp(
                host_tests_file, (conn, '/tmp/lmp-host-tests'))
            print('running tests on host via ssh')
            result = await conn.run('python3 /tmp/lmp-host-tests ' + worker)
            test_case('sshd', 'PASSED')
            print(result.stdout)

    try:
        asyncio.get_event_loop().run_until_complete(ssh())
    except (OSError, asyncssh.Error) as exc:
        print('SSH connection failed: ' + str(exc))
        test_case('sshd', 'FAILED')


def warm_main():
    test_case('warm-reboot', 'PASSED')
    _test_booted_image('warm')

    test_start('docker-tests')
    # If we've gotten this far we can safely claim a few things:
    test_case('container-pull', 'PASSED')
    test_case('container-start', 'PASSED')
    test_case('container-bind-mounts', 'PASSED')

    _run_host_tests()


if __name__ == '__main__':
    require_secrets('osftok')
    require_env('OSTREE_BRANCHNAME', 'MACHINE')
    if len(sys.argv) == 1:
        flash_main()
    elif sys.argv[1] == 'cold':
        cold_main()
    elif sys.argv[1] == 'warm':
        warm_main()
    else:
        sys.exit('Unexpected CLI args: %r' % sys.argv)
