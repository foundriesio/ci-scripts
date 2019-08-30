import asyncio
import sys

import asyncssh


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


def update_device(log, update_name):
    cmd = 'sudo -S aktualizr-lite update --update-name ' + update_name

    async def ssh():
        async with _host_connect() as conn:
            chan, session = await conn.create_session(MySSHClientSession, cmd)
            session.log = log
            chan.write('osf\n')
            chan.write_eof()
            await chan.wait_closed()
            if chan.get_exit_status() != 0:
                sys.exit('== ERROR: Unable to update device')

    log('SSHing into host to perform update')
    try:
        asyncio.get_event_loop().run_until_complete(ssh())
    except (OSError, asyncssh.Error) as exc:
        sys.exit('SSH connection failed: ' + str(exc))
    except KeyboardInterrupt:
        pass
    log('device updated')
