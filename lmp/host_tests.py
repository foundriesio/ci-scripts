#!/usr/bin/python3
import subprocess

import requests


def test_start(name):
    print('Starting Test Suite: %s' % name)


def test_case(name, result):
    print('Test Result: %s = %s\n' % (name, result))


def _check_network(interface, test_label, dst='8.8.8.8'):
    try:
        subprocess.check_call(['/usr/bin/ping', '-c3', '-I', interface, dst])
        test_case(test_label, 'PASSED')
    except Exception:
        test_case(test_label, 'FAILED')


def _check_systemd_job(job_name):
    try:
        subprocess.check_call(['systemctl', 'is-active', '--quiet', job_name])
        test_case('systemd-job-' + job_name, 'PASSED')
    except Exception:
        test_case('systemd-job-' + job_name, 'FAILED')


def _check_core_systemd_jobs():
    _check_systemd_job("systemd-timesyncd.service")
    _check_systemd_job("NetworkManager-wait-online.service")


def _check_shellhttpd():
    try:
        r = requests.get('http://localhost:8080')
        if r.status_code == 200:
            test_case('shellhttpd', 'PASSED')
        else:
            test_case('shellhttpd', 'FAILED')
    except Exception:
        test_case('shellhttpd', 'FAILED')


def _test_doanac_rpi3():
    _check_core_systemd_jobs()
    _check_network('wlan0', 'wifi', '192.168.0.1')
    _check_network('eth0', 'ethernet')
    _check_shellhttpd()


def _test_doanac_intel():
    _check_core_systemd_jobs()
    _check_network('enp2s0', 'ethernet')


DOANAC = '59db9c9a1c85010019e023cc'
DEVICES = {
    # ota+/jobserv name:  (POLIS_ID, test_function)
    'doanac-minnowboard': (DOANAC, _test_doanac_intel),
    'doanac-rpi3-64-2': (DOANAC, _test_doanac_rpi3),
}

if __name__ == '__main__':
    import sys
    if not len(sys.argv) == 2:
        sys.exit('Usage: %s <host>' % sys.argv[0])

    _, test_func = DEVICES.get(sys.argv[1], (None, None))
    if not test_func:
        sys.exit('Could not find tests for %s' % sys.argv[1])
    test_func()
