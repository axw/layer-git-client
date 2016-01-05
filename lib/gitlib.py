from charmhelpers.core.hookenv import (
    storage_list,
    storage_get,
)

def git_repo_path():
    return storage_get('location', storage_list('repo')[0])
