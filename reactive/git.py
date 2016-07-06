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
    if not os.path.exists(SSH_IDENTITY):
        subprocess.check_call(['ssh-keygen', '-P', '', '-f', SSH_IDENTITY])
    public_key = open(SSH_IDENTITY + '.pub').read()
    git.configure(username, public_key)
    set_state('git.configured')


@when('git.configured')
@when_not('git.available')
def waiting_availability():
    status_set('waiting', 'Waiting for git repository to be created')


@when('git.available')
@when_not('git.repo-available')
def clone_repo(git):
    # TODO(axw) only rewrite if server retports
    # changes to the relation settings.
    hostname = git.get_remote('hostname')
    write_git_ssh(hostname, git.ssh_host_keys())

    url = git.url()
    status_set('waiting', 'Cloning {}'.format(url))
    # TODO(axw) separate paths for .git and contents
    path = git_repo_path()
    dotgit = os.path.join(path, '.git')
    if os.path.exists(dotgit):
        shutil.rmtree(dotgit)
    git_exec(git, 'clone', url, path)

    # set the initial commit in local state
    commit = git_exec(git, 'rev-parse', cwd=path)
    if commit:
        git.set_commit(commit)
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
    "git_exec executes a git command and returns its output."

    env = os.environ
    if git.get_remote('protocol') == 'ssh':
        env = env.copy()
        env['GIT_SSH'] = os.path.abspath(GIT_SSH)
    return subprocess.check_output(['git'] + list(args), env=env, **kwargs)


def write_git_ssh(hostname, ssh_host_keys):
    """
    write_git_ssh writes the git-ssh script used by git commands when
    the protocol is 'ssh'.
    """

    # TODO(axw) validate format of ssh_host_keys
    content_lines = []
    for ssh_host_key in ssh_host_keys:
        content_lines.append('{} {}'.format(hostname, ssh_host_key))
    host.write_file(SSH_USER_KNOWN_HOSTS_FILE,
                    '\n'.join(content_lines).encode('utf-8'),
                    'root', 'root', 0o600)

    content = textwrap.dedent("""\
    #!/bin/bash
    exec /usr/bin/ssh -i {} -o UserKnownHostsFile={} $*
    """.format(os.path.abspath(SSH_IDENTITY), os.path.abspath(SSH_USER_KNOWN_HOSTS_FILE)))
    host.write_file(GIT_SSH, content.encode('utf-8'), 'root', 'root', 0o700)
