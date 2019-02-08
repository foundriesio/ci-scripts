import asyncio
import sys
import time

import asyncssh
import requests

from helpers import secret


class UpdateError(Exception):
    show_stack = False


def lmp_headers():
    return {'OSF-TOKEN': secret('osftok')}


def _host_connect():
    # TEMP HACK. The lastest asyncssh wants to use ed25519, but that's not in
    # 3.8 version of alpine's openssl. Once we are one 3.9, we can remove
    kex_algs = ('diffie-hellman-group-exchange-sha256',)
    return asyncssh.connect('172.17.0.1', known_hosts=None,
                            username='osf', password='osf', kex_algs=kex_algs)


class MySSHClientSession(asyncssh.SSHClientSession):
    COMPLETE_MSG = (
        'Created empty /run/aktualizr/ostree-pending-update',
        'got AllInstallsComplete event',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.channel = self.log = self.deadline = None

    def data_received(self, data, datatype):
        print(data, end='')

        for m in self.COMPLETE_MSG:
            if m in data:
                self.log('detected updated completion, exiting')
                self.channel.terminate()
                self.channel.close()
                break
        if self.deadline and time.time() > self.deadline:
            self.log('Timeout waiting for update to complete')
            self.channel.terminate()
            self.channel.close()
            raise UpdateError('Timeout waiting for device update')

    def connection_lost(self, exc):
        if exc:
            self.log('SSH session error: ' + str(exc))
            raise


def _wait_on_update(log):
    async def ssh():
        async with _host_connect() as conn:
            chan, session = await conn.create_session(
                MySSHClientSession, 'sudo -S journalctl -f')
            session.channel = chan
            session.log = log
            session.deadline = time.time() + (60 * 15)   # wait 15 minutes
            chan.write('osf\n')
            chan.write_eof()
            await chan.wait_closed()
    try:
        asyncio.get_event_loop().run_until_complete(ssh())
    except (OSError, asyncssh.Error) as exc:
        sys.exit('SSH connection failed: ' + str(exc))
    except KeyboardInterrupt:
        pass


def update_device(log, device, ostree_hash):
    url = 'https://api.foundries.io' + device['url']
    r = requests.put(
        url, json={'image': {'hash': ostree_hash}}, headers=lmp_headers())
    if r.status_code != 200:
        raise UpdateError('Unable to request update(%s): %d\n%s' % (
            url, r.status_code, r.text))
    log('requested update: %r' % r.text)
    log('waiting for update queue to complete')
    _wait_on_update(log)
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
