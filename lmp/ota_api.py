import asyncio
import sys

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
    def data_received(self, data, datatype):
        print(data, end='')

    def connection_lost(self, exc):
        if exc:
            self.log('SSH session error: ' + str(exc))
            raise


def update_device(log, device, update_name):
    cmd = 'sudo -S aktualizr-lite update ' + update_name

    async def ssh():
        async with _host_connect() as conn:
            chan, session = await conn.create_session(MySSHClientSession, cmd)
            session.log = log
            chan.write('osf\n')
            chan.write_eof()
            await chan.wait_closed()

    log('SSHing into host to perform update')
    try:
        asyncio.get_event_loop().run_until_complete(ssh())
    except (OSError, asyncssh.Error) as exc:
        sys.exit('SSH connection failed: ' + str(exc))
    except KeyboardInterrupt:
        pass
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
