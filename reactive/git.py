import os
import shutil
import subprocess
import textwrap

from charmhelpers.core.hookenv import (
    service_name,
    status_set,
    open_port,
    config,
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

from gitlib import git_repo_path


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
@when_not('git.repo-available')
def clone_repo(git):
    url = git.url()
    status_set('waiting', 'Cloning {}'.format(url))
    # TODO(axw) separate paths for .git and contents
    path = git_repo_path()
    dotgit = os.path.join(path, '.git')
    if os.path.exists(dotgit):
        shutil.rmtree(dotgit)
    git_exec(git, 'clone', url, path)
    # TODO(axw) store the current commit in local state
    status_set('active', '')
    git.set_local('repo-path', path)
    set_state('git.repo-available')


@when('git.commit.changed')
def commit_changed(git):
    sha = git.get_remote('git-commit')
    path = git_repo_path()
    git_exec(git, 'fetch', 'origin', cwd=path)
    git_exec(git, 'checkout', sha, cwd=path)
    git.set_commit(sha)


def git_exec(git, *args, **kwargs):
    env = os.environ
    if git.get_remote('protocol') == 'ssh':
        env = env.copy()
        env['GIT_SSH'] = os.path.abspath(GIT_SSH)
        hostname = git.get_remote('hostname')
        ssh_host_key = git.get_remote('ssh-host-key')
        # TODO(axw) only rewrite if args change
        write_git_ssh(hostname, ssh_host_key)
    subprocess.check_call(['git'] + list(args), env=env, **kwargs)


def write_git_ssh(hostname, ssh_host_key):
    # TODO(axw) validate format of ssh_host_key
    content = '{} {}'.format(hostname, ssh_host_key)
    host.write_file(SSH_USER_KNOWN_HOSTS_FILE,
                    content.encode('utf-8'),
                    'root', 'root', 0o600)

    content = textwrap.dedent("""\
    #!/bin/bash
    exec /usr/bin/ssh -i {} -o UserKnownHostsFile={} $*
    """.format(os.path.abspath(SSH_IDENTITY), os.path.abspath(SSH_USER_KNOWN_HOSTS_FILE)))
    host.write_file(GIT_SSH, content.encode('utf-8'), 'root', 'root', 0o700)
