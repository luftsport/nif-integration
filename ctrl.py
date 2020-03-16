#!/home/einar/nif-integration/bin/python
import requests
from settings import API_URL, API_HEADERS
import sys
from datetime import datetime

def test():
    print('Testing testing')


def startup():
    resp = requests.post('{}/syncdaemon/workers/reboot'.format(API_URL),
                         headers=API_HEADERS)
    print('Startup', datetime.now().isoformat())
    print('Http', resp.status_code)
    print('Msg')
    print(resp.text)


def shutdown():
    resp = requests.post('{}/syncdaemon/workers/shutdown'.format(API_URL),
                         headers=API_HEADERS)
    print('Shutdown', datetime.now().isoformat())
    print('Http', resp.status_code)
    print('Msg')
    print(resp.text)

def halt():
    resp = requests.post('{}/syncdaemon/shutdown'.format(API_URL),
                         headers=API_HEADERS)
    print('HALT', datetime.now().isoformat())
    print('Http', resp.status_code)
    print('Msg')
    print(resp.text)

if __name__ == "__main__":
    arg = sys.argv[1:2]
    if len(arg) > 0:
        arg = arg[0]
    else:
        arg = None

    if arg == 'stop':
        shutdown()
    elif arg == 'start':
        startup()
    elif arg == 'halt':
        halt()
    elif arg == 'test':
        test()
    else:
        print('[ERR] No arguments given')
