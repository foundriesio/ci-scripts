import asyncio
import atexit
import os
import sys
import time

from signal import SIGINT

import asyncssh
import requests

from helpers import secret


class UpdateError(Exception):
    show_stack = False


def lmp_headers():
    return {'OSF-TOKEN': secret('osftok')}


def _wait_on_update(log, device_url):
    # 144 * 5 = 720 seconds = 12 minutes
    for i in range(144):
        try:
            r = requests.get(device_url, headers=lmp_headers())
            if r.status_code == 200:
                status = r.json()['status']
                if status == 'UpToDate':
                    return
                log('waiting status = ' + status)
            else:
                log('error checking update status: %d\n%s' % (
                    r.status_code, r.text))
        except Exception as e:
            log('Error checking on: %s\n  %r' % (device_url, e))
        time.sleep(5)

    raise UpdateError('Timeout waiting for device update')


def _tail_journal(log):
    p = os.fork()
    if p:
        atexit.register(os.kill, p, SIGINT)
        return

    log('Tailing journal on host')

    async def ssh():
        future = asyncssh.connect(
            '172.17.0.1', known_hosts=None, username='osf', password='osf')
        async with future as conn:
            await conn.run('journalctl -f', stdout='/archive/journal.log')

    try:
        asyncio.get_event_loop().run_until_complete(ssh())
    except (OSError, asyncssh.Error) as exc:
        sys.exit('SSH connection failed: ' + str(exc))
    except KeyboardInterrupt:
        pass
    sys.exit(0)


def update_device(log, device, ostree_hash):
    _tail_journal(log)

    url = 'https://api.foundries.io' + device['url']
    r = requests.put(
        url, json={'image': {'hash': ostree_hash}}, headers=lmp_headers())
    if r.status_code != 200:
        raise UpdateError('Unable to request update(%s): %d\n%s' % (
            url, r.status_code, r.text))
    log('requested update: %r' % r.text)
    log('waiting for update queue to complete')
    _wait_on_update(log, url)
    log('device updated')


def device_get(name, owner):
    # devices live in different "update-streams". the "list" api returns them
    # all, so use that to find the device and drive the CI logic
    url = 'https://api.foundries.io/lmp/devices/'
    r = requests.get(url, headers=lmp_headers(), params={'user': owner})
    if r.status_code == 200:
        try:
            for d in r.json():
                if d['name'] == name:
                    d['url'] += '&owner=' + owner
                    return d
        except IndexError:
            pass  # will throw an exception below
    raise UpdateError('Unable to find device(%s): %d\n%s' % (
        url, r.status_code, r.text))
