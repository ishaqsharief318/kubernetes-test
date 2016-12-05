from git import Repo

import subprocess
import yaml
import re
import config
import sys
import logging
import os


handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(levelname)s - %(filename)s:%(funcName)s:%(lineno)d - %(message)s', '%Y-%m-%d-%H:%M:%S'  # NOQA
))
logging.getLogger().setLevel(logging.INFO)
logging.getLogger().addHandler(handler)
log = logging.getLogger(__name__)

def release_kuber(context, app, version):
    # check whether the app belongs to the context
    if app not in config.app_dict.get(context, []):
        log.error('Provided app does not belong to the context')
        return

    to_kuber = os.path.join(os.getcwd(), 'hellonode')
    git = Repo(os.path.abspath('{}/..'.format(to_kuber))).git
    git = Repo('{}'.format(os.getcwd())).git
    git.checkout('master')
    git.pull()

    try:
        try:
        # check whether a container with app name and provided version number exists
            print version
            version = version if version.startswith('v') else 'v'+version
            print version
            container_tags = subprocess.check_output(['gsutil', 'ls', '{}/{}/tag_{}'.format(
                                config.gs_path_to_app, app, version)])
            log.info('App and version check successful')
        except:
            log.error('The container with provided app and version number does not exist')
            return

        # modify app.yml file with new version
        yaml_file = '{}.yml'.format(app)

        print os.getcwd()
        with open(yaml_file) as f:
            yaml_dict = yaml.load(f)

        _update_yaml_file(yaml_dict, version)

        with open(yaml_file, 'w') as f:
            yaml.dump(yaml_dict, f, default_flow_style=False)

        # get replication controller name, sample output of this command:
        # CONTROLLER              CONTAINER (S)     IMAGES            SELECTOR     REPLICAS
        # backend-controller      applier           applier_2.3.11    applier      3
        rc_name = subprocess.check_output(['kubectl','get', 'deployment',
                                           '{}'.format(app)]).split('\n')[1].split()[0]

        log.info('Applying New Configuration')
        # run rolling update
        exit_code = subprocess.call(['kubectl', 'apply', '-f', yaml_file])

        # if rolling update succeeds, commit changes in Git repo and push back to master
        if exit_code == 0:
            log.info('Updated {} to {} successfully'.format(app, version))
            git.add(yaml_file)
            commit_message = ' bump {} to {}'.format(app, version)
            git.commit(m=commit_message)
            log.info(commit_message)
            git.push()
        else:
            log.error('Errors in updating deployment, exit code:{}'.format(exit_code))
            git.checkout('.')

    except Exception as e:
        git.checkout('.')
        log.exception('Exception:{}'.format(e))


def _update_yaml_file(yaml_dict, version):
    # replace any version format substring with new version number
    if not isinstance(yaml_dict, dict):
        return
    for key, value in yaml_dict.iteritems():
        if isinstance(value, list):
            for item in value:
                _update_yaml_file(item, version)
        elif isinstance(value, dict):
            _update_yaml_file(value, version)
        elif isinstance(value, str):
            if version.startswith('v'):
                substr_match = re.search('v\d+\.\d+\.\d+', value)
            else:
                substr_match = re.search('\d+\.\d+\.\d+', value)
            if substr_match:
                start, end = substr_match.span()
                yaml_dict[key] = value[:start] + version + value[end:]

if __name__ == '__main__':
    # argv order should be: application name, version number
    release_kuber('backend',sys.argv[1], sys.argv[2])
