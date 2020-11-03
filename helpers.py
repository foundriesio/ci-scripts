import contextlib
from zipfile import ZipFile
import json
import os
import subprocess
import sys
import traceback
from typing import Optional

import requests

SECRETS = os.environ.get('SECRETS_DIR', '/secrets')


def require_env(*env_names):
    missing = []
    for e in env_names:
        try:
            yield os.environ[e]
        except KeyError:
            missing.append(e)
    if missing:
        sys.exit('Missing required environment variables: %s' % ', '.join(
            missing))


def require_secrets(*secret_names):
    missing = []
    for s in secret_names:
        if not os.path.exists(os.path.join(SECRETS, s)):
            missing.append(s)
    if missing:
        sys.exit('Missing required secrets: %s' % ', '.join(missing))


def status(msg, prefix='== '):
    '''Print a commonly formatted status message to the build output'''
    sys.stdout.buffer.write(prefix.encode())
    sys.stdout.buffer.write(b' ')
    sys.stdout.buffer.write(msg.encode())
    sys.stdout.buffer.write(b'\n')
    sys.stdout.buffer.flush()


def test_start(name):
    print('Starting Test Suite: %s' % name)


def test_case(name, result):
    print('Test Result: %s = %s\n' % (name, result))


@contextlib.contextmanager
def test_case_ctx(name):
    def status_func(msg):
        print('  ' + msg)
    try:
        print('- Starting test: ' + name)
        yield status_func
        test_case(name, 'PASSED')
    except Exception as e:
        if getattr(e, 'show_stack', True):
            stack = traceback.format_exc().strip().replace('\n', '\n  | ')
            print('  ' + stack)
        else:
            print('  ERROR: ' + str(e))
        test_case(name, 'FAILED')
        sys.exit(1)


def cmd(*args, cwd=None, capture=False):
    '''Run a command and die if it fails. Output goes to stdoud/stderr'''
    # run a command and terminate on failure
    status(' '.join(args), prefix='=$ ')
    p = subprocess.Popen(args, cwd=cwd,
                         stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
    out = b''
    for line in p.stdout:
        sys.stdout.buffer.write(b'| ')
        sys.stdout.buffer.write(line)
        sys.stdout.buffer.flush()
        if capture:
            out += line
    sys.stdout.buffer.write(b'|--\n')
    p.communicate()
    if p.returncode != 0:
        raise subprocess.CalledProcessError(p.returncode, args)
    return out


def secret(name):
    with open(os.path.join(SECRETS, name)) as f:
        return f.read().strip()


def secret_get(url, secret_name, header_name, **kwargs):
    '''Does an HTTP get using the given secret sent as header_name'''
    headers = {header_name: secret(secret_name)}
    r = requests.get(url, headers=headers, **kwargs)
    if r.status_code != 200:
        sys.exit('Unable to find %s: %d\n%s' % (url, r.status_code, r.text))
    return r


def secret_delete(url, secret_name, header_name, **kwargs):
    '''Does an HTTP DELETE using the given secret sent as header_name'''
    headers = {header_name: secret(secret_name)}
    r = requests.delete(url, headers=headers, **kwargs)
    if r.status_code != 200:
        sys.exit('Unable to delete %s: %d\n%s' % (url, r.status_code, r.text))
    return r


def jobserv_get(url):
    '''Does an HTTP get using the jobserv credentials'''
    if url[0] == '/':
        url = 'https://api.foundries.io/' + url
    return secret_get(url, 'osftok', 'OSF-TOKEN').json()


def jobserv_post(url, data, dryrun, status_code=201):
    headers = {'OSF-TOKEN': secret('osftok')}

    if url[0] == '/':
        url = 'https://api.foundries.io' + url

    if dryrun:
        print('== dryrun post to: ' + url)
        print('    ' + '\n    '.join(json.dumps(data, indent=2).splitlines()))
        return
    r = requests.post(url, json=data, headers=headers)
    if r.status_code != status_code:
        sys.exit('Unable to POST(%s): %d\n%s' % (url, r.status_code, r.text))


def jobserv_iterate_items(url, item_name):
    while url:
        data = jobserv_get(url)['data']
        for item in data[item_name]:
            yield item
        url = data.get('next')


def http_get(url, params=None, **kwargs):
    response = requests.get(url, params=params, **kwargs)
    if not response.ok:
        raise requests.exceptions.HTTPError('Failed to get {}: HTTP_{}\n{}'.
                                            format(url, response.status_code, response.text))
    return response


def generate_credential_tokens(creds_zip_in: str, creds_zip_out: str):
    """Creates an updated creds.zip file that has populated osf
       tokens with the dynamic scoped tokens set in the run's secrets."""

    with ZipFile(creds_zip_out, mode='w') as zout:
        with ZipFile(creds_zip_in) as zin:
            for name in zin.namelist():
                buf = zin.read(name)
                if name == 'treehub.json':
                    data = json.loads(buf.decode())
                    data['oauth2']['client_id'] = secret('triggered-by')
                    data['oauth2']['client_secret'] = secret('osftok')
                    buf = json.dumps(data).encode()
                zout.writestr(name, buf)


class Progress:
    def __init__(self, total: int, parent: Optional["Progress"] = None):
        if total == 0:
            raise ValueError("Invalid total")
        self.total = total
        self.cur = 0
        self.parent = parent

    def tick(self, complete=False):
        if complete and self.cur != self.total:
            self.cur = self.total
        elif self.cur < self.total:
            self.cur += 1

        percent = round(self.cur / self.total * 100)
        if self.parent:
            parent_total = round(self.parent.cur / self.parent.total * 100)
            percent = parent_total + round(percent / self.parent.total)

            if self.cur == self.total:
                self.parent.cur += 1
        self.show_progress(percent)

    def show_progress(self, percent_complete: int):
        status('Run is %d%% complete' % percent_complete, prefix='##')
