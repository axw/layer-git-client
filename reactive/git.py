import os
import shutil
import subprocess
import textwrap

from charmhelpers.core.hookenv import (
    service_name,
    status_set,
    open_port,
    config,
    storage_list,
    storage_get,
)

from charmhelpers.core import host

from charmhelpers.fetch import (
    apt_install,
)

from charms.reactive import (
    hook,
    when,
    when_not,
    is_state,
    set_state,
    remove_state,
)


# created in the charm directory.
SSH_IDENTITY = 'id_rsa'
SSH_USER_KNOWN_HOSTS_FILE = 'known_hosts'
GIT_SSH = 'git-ssh'


@hook('install')
def install_git():
    apt_install('git')


@when('git.related')
@when_not('git.configured')
def configure_git(git):
    status_set('maintenance', 'Configuring ssh and git')
    username = service_name()
    subprocess.check_call(['ssh-keygen', '-P', '', '-f', SSH_IDENTITY])
    public_key = open(SSH_IDENTITY + '.pub').read()
    git.configure(username, public_key)
    status_set('waiting', 'Waiting for git repository to be created')
    set_state('git.configured')


@when('git.available')
@when_not('git.repo.cloned')
def clone_repo(git):
    url = git.url()
    status_set('waiting', 'Cloning {}'.format(url))

    env = os.environ.copy()
    if git.get_remote('protocol') == 'ssh':
        env['GIT_SSH'] = os.path.abspath(GIT_SSH)
        hostname = git.get_remote('hostname')
        ssh_host_key = git.get_remote('ssh-host-key')
        write_git_ssh(hostname, ssh_host_key)

    path = repo_path()
    if os.path.exists(path):
        shutil.rmtree(path)
    subprocess.check_call(['git', 'clone', url, path], env=env)
    # TODO(axw) store the current commit in local state
    status_set('active', '')
    set_state('git.repo.cloned')


# TODO(axw) when('git.commit.changed')
# TODO(axw) need to check if hostname changed, update remote


def write_git_ssh(hostname, ssh_host_key):
    # TODO(axw) validate format of ssh_host_key
    content = '{} {}'.format(hostname, ssh_host_key)
    host.write_file(SSH_USER_KNOWN_HOSTS_FILE, content, 'root', 'root', 0o600)

    content = textwrap.dedent("""\
    #!/bin/bash
    exec /usr/bin/ssh -i {} -o UserKnownHostsFile={} $*
    """.format(os.path.abspath(SSH_IDENTITY), os.path.abspath(SSH_USER_KNOWN_HOSTS_FILE)))
    host.write_file(GIT_SSH, content, 'root', 'root', 0o700)


def repo_path():
    # TODO(axw) when reactive support for storage is fixed, use
    # storage.
    #return storage_get('location', storage_list('repo')[0])
    path = 'repo'
    return path

