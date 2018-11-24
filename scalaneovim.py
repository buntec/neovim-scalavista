import subprocess
import time
import requests
import json


def launch():

    print('scalavista> launching server...')

    with open('scalavista.json') as f:
        conf = json.load(f)

    classpath = conf['classpath'] + ':' + '/Users/christophbunte/repos/gitlab-repos/scala-completion-server/target/scala-2.12/scala-completion-engine-assembly-0.1.jar'

    p = subprocess.Popen(['java', '-cp', classpath, 'org.scalavista.AkkaServer'])

    for i in range(5):
        time.sleep(1)
        try:
            r = requests.get('http://localhost:8080/alive')
        except Exception:
            pass
        else:
            if r.status_code == requests.codes.ok:
                break
    else:
        p.terminate()
        print("scalavista> failed to start server - quitting")
        return

    for source_file in conf['sources']:
        with open(source_file) as f:
            data = {'filename': source_file, 'fileContents': f.read()}
        try:
            r = requests.post('http://localhost:8080/reload-file', json=data)
            if r.status_code != requests.codes.ok:
                print('failed to load file {}'.format(source_file))
        except Exception:
            print('failed to reload buffer {}'.format(source_file))

    input("scalavista> server is up and running - press any key to stop...")

    p.terminate()


if __name__ == '__main__':
    launch()
