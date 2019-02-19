#!/usr/bin/python3
import subprocess
import time

import requests


def test_start(name):
    print('Starting Test Suite: %s' % name)


def test_case(name, result):
    print('Test Result: %s = %s\n' % (name, result))


def _check_bt_device(bt_mac):
    out = subprocess.check_output(['/usr/bin/hcitool', 'con'])
    if 'LE ' + bt_mac in out.decode():
        test_case('bt-joiner', 'PASSED')
        return True
    else:
        test_case('bt-joiner', 'FAILED')


def _check_leshan_ep(ep):
    for x in range(4):
        r = requests.get('https://mgmt.foundries.io/leshan/api/clients/' + ep)
        if r.status_code == 200:
            test_case('bluetooth', 'PASSED')
            test_case('nginx-lwm2m-proxy', 'PASSED')
            return True
        print('Unable to find device %s. Sleeping and trying again.' % ep)
        print(' HTTP(%d) - %s' % (r.status_code, r.text))
        time.sleep(2)
    test_case('bluetooth', 'FAILED')
    test_case('nginx-lwm2m-proxy', 'FAILED')


def _check_hawkbit_ep(ep):
    url = 'https://admin:admin@mgmt.foundries.io/hawkbit/rest/v1/targets/'
    url += ep
    for x in range(4):
        msg = 'Unable to find device ' + ep
        r = requests.get(url)
        if r.status_code == 200:
            if not r.json()['pollStatus']['overdue']:
                test_case('bluetooth', 'PASSED')
                test_case('nginx-http-proxy', 'PASSED')
                return True
            msg = 'Device pollStatus is "overdue" for ' + ep
        print(msg + '. Sleeping and trying again.')
        print(' HTTP(%d) - %s' % (r.status_code, r.text))
        time.sleep(2)
    test_case('bluetooth', 'FAILED')
    test_case('nginx-http-proxy', 'FAILED')


def _check_mqtt(device):
    url = 'https://mgmt.foundries.io/mqtt/%s.log' % device
    val = None
    for x in range(4):
        r = requests.get(url)
        if r.status_code == 200:
            if val is None:
                val = r.text
            elif val != r.text:
                # the log has changed so we've reported something
                test_case('mosqitto', 'PASSED')
                return True
        print('No change in data detected, sleeping and trying again.')
        time.sleep(2)
    test_case('mosqitto', 'FAILED')


def _check_network(interface, test_label, dst='8.8.8.8'):
    try:
        subprocess.check_call(['/usr/bin/ping', '-c3', '-I', interface, dst])
        test_case(test_label, 'PASSED')
    except Exception:
        test_case(test_label, 'FAILED')


def _test_doanac_hikey():
    _check_network('wlan0', 'wifi')
    if _check_bt_device('D4:E7:DD:63:FE:94'):
        _check_leshan_ep('zmp:sn:dd63fe94')


def _test_doanac_rpi3():
    _check_network('wlan0', 'wifi', '192.168.0.1')
    _check_network('eth0', 'ethernet')
    if _check_bt_device('D4:E7:43:91:CC:43'):
        _check_leshan_ep('4391cc43')


def _test_doanac_rpi0():
    _check_network('wlan0', 'wifi')
    if _check_bt_device('D6:E7:46:2F:A6:2D'):
        _check_leshan_ep('462fa62d')


def _test_doanac_intel():
    _check_network('enp2s0', 'ethernet')


def _test_doanac_410c():
    _check_network('eth0', 'usb-ethernet')
    if _check_bt_device('D4:E7:64:15:92:32'):
        _check_hawkbit_ep('nrf52_blenano2-64159232')
        _check_mqtt('nrf52_blenano2-64159232')


DOANAC = '59db9c9a1c85010019e023cc'
DEVICES = {
    # ota+/jobserv name:  (POLIS_ID, test_function)
    'doanac-minnowboard': (DOANAC, _test_doanac_intel),
    'doanac-dragonboard-410c': (DOANAC, _test_doanac_410c),
    'doanac-hikey-1': (DOANAC, _test_doanac_hikey),
    'doanac-raspberrypi0-wifi': (DOANAC, _test_doanac_rpi0),
    'doanac-rpi3-64-2': (DOANAC, _test_doanac_rpi3),
    'doanac-x86-qemu-1': (DOANAC, _test_doanac_intel),
}

if __name__ == '__main__':
    import sys
    if not len(sys.argv) == 2:
        sys.exit('Usage: %s <host>' % sys.argv[0])

    _, test_func = DEVICES.get(sys.argv[1], (None, None))
    if not test_func:
        sys.exit('Could not find tests for %s' % sys.argv[1])
    test_func()
