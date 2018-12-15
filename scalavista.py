from subprocess import Popen
import glob
import json
import os
import requests
import subprocess
import time
import crayons


PROMPT = 'scalavista>'


def info(msg):
    print('{}#{} {}'.format('scalavista', crayons.magenta('info'), msg))


def success(msg):
    print('{}#{} {}'.format('scalavista', crayons.green('success'), msg))


def warn(msg):
    print('{}#{} {}'.format('scalavista', crayons.yellow('warn'), msg))


def error(msg):
    print('{}#{} {}'.format('scalavista', crayons.red('error'), msg))


def launch():

    try:
        with open('scalavista.json') as f:
            conf = json.load(f)
    except FileNotFoundError:
        error('missing "scalavista.json" - please use the sbt-scalavista plugin to generate it.')
        return

    info('launching server...')

    scala_binary_version = conf['scalaBinaryVersion']

    base_dir = os.path.dirname(os.path.realpath(__file__))
    jar_path = os.path.join(base_dir, 'jars', r'scalavista-*_{}.jar'.format(scala_binary_version))
    scalavista_jar = glob.glob(jar_path)[0]

    if not os.path.isfile(scalavista_jar):
        raise RuntimeError('jar not found: {}'.format(scalavista_jar))

    classpath = conf['classpath'] + ':' + scalavista_jar
    server_process = Popen(['java', '-cp', classpath, 'org.scalavista.AkkaServer'])
    # server_port = server_process.stdout.readline().decode('utf-8')
    # server_url = 'http://localhost:{}'.format(server_port).strip()
    server_url = 'http://localhost:9317'

    for i in range(10):
        try:
            info('testing connection...')
            req = requests.get(server_url + '/alive')
        except Exception:
            time.sleep(1)
        else:
            if req.status_code == requests.codes.ok:
                break
    else:
        server_process.terminate()
        error('failed to start server - quitting...')
        return

    for source_file in conf['sources']:
        with open(source_file) as f:
            data = {'filename': source_file, 'fileContents': f.read()}
        try:
            req = requests.post(server_url + '/reload-file', json=data)
            if req.status_code != requests.codes.ok:
                raise Exception
        except Exception:
            warn('failed to load source file {}'.format(source_file))

    success('server is up and running at {} - press any key to stop...'.format(server_url))

    input('')

    server_process.terminate()


if __name__ == '__main__':
    launch()
