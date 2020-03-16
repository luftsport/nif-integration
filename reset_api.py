from settings import API_HEADERS, API_URL, STREAM_RESUME_TOKEN_FILE, SYNCDAEMON_PID_FILE
from termcolor import colored, cprint
import requests
import sys
import os
from pathlib import Path

"""
@TODO needs to reset resume.token file else stream will barf
"""

# For resetting changing REALM
"""
resources = [['persons/process', True, 0],
             ['functions/process', True, 0],
             ['functions/types', True, 0],
             ['licenses/process', True, 0],
             ['licenses/types', True, 0],
             ['competences/process', True, 0],
             ['competences/types', True, 0],
             ['organizations/process', True, 0],
             ['organizations/types', True, 0],
             ['integration/users', False, 0],
             ['integration/changes', True, 0],
             ]
"""
resources = [['persons/process', True, 0],
             ['functions/process', True, 0],
             ['functions/types', False, 0],
             ['licenses/process', True, 0],
             ['licenses/types', False, 0],
             ['competences/process', True, 0],
             ['competences/types', False, 0],
             ['organizations/process', False, 0],
             ['organizations/types', False, 0],
             ['integration/users', False, 0],
             ['integration/changes', True, 0],
             ]

resume_token_path = Path(STREAM_RESUME_TOKEN_FILE)
syncdaemon_pid_path = Path(SYNCDAEMON_PID_FILE)

if __name__ == "__main__":
    os.system("cls")
    os.system("clear")
    cprint('\n!!! WARNING !!!', 'red', attrs=['bold'])
    print('You are about to delete ALL items in the following resources:\n')
    print('API: {}\n'.format(API_URL))

    for k, r in enumerate(resources):

        resp = requests.get(url='{}/{}?max_results=1'.format(API_URL, r[0]), headers=API_HEADERS)
        if resp.status_code == 200:

            resources[k][2] = resp.json()['_meta']['total']

            if r[1] is True:
                delete = 'X'
            else:
                delete = ' '

            p = ['[{}] {}/{}'.format(delete, API_URL, r[0]),
                 '[{} items]'.format(r[2])]
            cprint('{: <80} {: <20}'.format(*p), attrs=['bold'])
        else:
            resources.remove(r)

            try:
                err = resp.json()
            except:
                err = {'_error': {'message': resp.text}}

            p = ['[?] {}/{}'.format(API_URL, r[0]),
                 '[{}: {}]'.format(resp.status_code, err.get('_error', {}).get('message', 'Error')) ]
            cprint('{: <80} {: <20}'.format(*p))

    print('\n')
    if syncdaemon_pid_path.exists() is True:
        print('[X] Syncdaemon pidfile {} exists\t\t\t[1 file]'.format(SYNCDAEMON_PID_FILE))
    if resume_token_path.exists() is True:
        print('[X] Stream resume token file {} exists\t\t\t[1 file]'.format(STREAM_RESUME_TOKEN_FILE))

    # Delete all?
    if str(input("\n\nAre you sure? (yes/n):\t")).lower().strip() == "yes":

        # Delte resume token!
        try:
            resume_token_path.unlink()
            print('[D] Deleted file\t\t{}'.format(STREAM_RESUME_TOKEN_FILE))
        except:
            pass

        try:
            syncdaemon_pid_path.unlink()
            print('[D] Deleted file:\t\t{}'.format(SYNCDAEMON_PID_FILE))
        except:
            pass

        for r in resources:
            if r[1] is True:

                resp = requests.delete('{}/{}'.format(API_URL, r[0]), headers=API_HEADERS)

                # 204 deleted, 404 nothing in it...
                cprint(
                    '[D] {0}/{1}\t\t\t[{2}: deleted {3} items]'.format(API_URL, r[0], resp.status_code, r[2]),
                    attrs=['bold'])
            elif r[1] is not True:
                cprint(
                    '[ ] {0}/{1}\t\t\t[deleted 0 items]'.format(API_URL, r[0]),
                    attrs=['bold'])
    else:
        print('\n\n')
        print('Ok, no deletes')
        print('\n')


    # Rebuild reseources?
    if str(input("\n\nRebuild all resource resources? (yes/n):\t")).lower().strip() == "yes":
        from rebuild_api_resources import NifRebuildResources
        r = NifRebuildResources()
        r.rebuild()
        print('Ok, finished rebuilding!')
    else:
        print('\n\n')
        print('Ok, no rebuilding then')
        print('\n')

    sys.exit(0)
