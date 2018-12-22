from subprocess import Popen
import glob
import json
import os
import requests
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


def launch(debug=False, recursive=False):

    try:
        with open('scalavista.json') as f:
            conf = json.load(f)
            scala_binary_version = conf['scalaBinaryVersion']
            classpath = conf['classpath']
            sources = conf['sources']
    except IOError:
        warn('missing "scalavista.json" - you can generate it using the scalavista sbt-plugin.')
        scala_binary_version = '2.12'
        lib_jars = glob.glob(os.path.join(os.path.abspath('./lib'), '*.jar'))
        classpath = ':'.join(lib_jars)
        if recursive:
            sources = []
            for root, _, files in os.walk(os.path.abspath('.')):
                for file in files:
                    if file.endswith('.scala'):
                        sources.append(os.path.join(root, file))
        else:
            sources = [os.path.abspath(source_path) for source_path in glob.glob('*.scala')]

    base_dir = os.path.dirname(os.path.realpath(__file__))
    jar_wildcard = os.path.join(base_dir, 'jars', r'scalavista-*_{}.jar'.format(scala_binary_version))

    if not glob.glob(jar_wildcard):
        raise RuntimeError('no suitable scalavista jar found - run install.sh to download')

    scalavista_jar = glob.glob(jar_wildcard)[0]

    if not os.path.isfile(scalavista_jar):
        raise RuntimeError('jar not found: {}'.format(scalavista_jar))

    if classpath:
        classpath += ':' + scalavista_jar
    else:
        classpath = scalavista_jar

    info('launching server...')

    if debug:
        logging_flag = '-d'
    else:
        logging_flag = '-q'

    server_process = Popen(['java', '-cp', classpath, 'org.scalavista.AkkaServer', logging_flag])
    server_url = 'http://localhost:9317'

    max_tries = 10
    for i in range(max_tries):
        try:
            info('testing connection...({}/{})'.format(i + 1, max_tries))
            req = requests.get(server_url + '/alive')
        except Exception:
            time.sleep(2)
        else:
            if req.status_code == requests.codes.ok:
                break
    else:
        server_process.terminate()
        error('failed to start server - quitting...')
        return

    for source_file in sources:
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
