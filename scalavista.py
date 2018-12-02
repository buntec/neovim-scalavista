from subprocess import Popen, PIPE
import glob
import json
import os
import requests
import subprocess
import time


def info(msg):
    print('scalavista> {}'.format(msg))


def launch():

    info('launching server...')

    with open('scalavista.json') as f:
        conf = json.load(f)

    scala_binary_version = conf['scalaBinaryVersion']

    scalavista_jar = glob.glob(os.path.expanduser('~/.scalavista/scalavista-*_{}.jar'.format(scala_binary_version)))[0]

    if not os.path.isfile(scalavista_jar):
        raise RuntimeError('jar not found: {}'.format(scalavista_jar))

    classpath = conf['classpath'] + ':' + scalavista_jar
    server_process = Popen(['java', '-cp', classpath, 'org.scalavista.AkkaServer'], stdout=PIPE, stderr=PIPE)
    server_port = server_process.stdout.readline().decode('utf-8')
    server_url = 'http://localhost:{}'.format(server_port).strip()

    for i in range(10):
        try:
            info('testing connection...')
            req = requests.get(server_url + '/alive')
        except Exception as e:
            time.sleep(1)
        else:
            if req.status_code == requests.codes.ok:
                break
    else:
        server_process.terminate()
        info('failed to start server - quitting...')
        return

    for source_file in conf['sources']:
        with open(source_file) as f:
            data = {'filename': source_file, 'fileContents': f.read()}
        try:
            req = requests.post(server_url + '/reload-file', json=data)
            if req.status_code != requests.codes.ok:
                info('failed to load file {}'.format(source_file))
        except Exception:
            info('failed to reload buffer {}'.format(source_file))

    info('server is up and running at {} - press any key to stop...'.format(server_url))

    while True:
        print(server_process.stdout.readline())

    input('')

    server_process.terminate()


if __name__ == '__main__':
    launch()
