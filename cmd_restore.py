#!/usr/bin/python
"""
Restore backup

Options:
    --skip-files                Don't restore filesystem
    --skip-database             Don't restore databases
    --skip-packages             Don't restore new packages

    --no-rollback               Disable rollback

"""

import os
from os.path import *

import sys
import getopt

import shutil
import userdb
import tempfile

from paths import Paths
from changes import Changes

import backup

def fatal(e):
    print >> sys.stderr, "error: " + str(e)
    sys.exit(1)

def usage(e=None):
    if e:
        print >> sys.stderr, "error: " + str(e)

    print >> sys.stderr, "Syntax: %s [ -options ] <address> <keyfile> [ limits ... ]" % sys.argv[0]
    print >> sys.stderr, __doc__.strip()
    sys.exit(1)


def test():
    tmpdir = "/var/tmp/restore/backup"
    log = sys.stdout
    restore(tmpdir, log)

def restore(backup_path, log=None):
    tmpdir = tempfile.mkdtemp(prefix="tklbam-extras-")
    os.rename(backup_path + backup.Backup.EXTRAS_PATH, tmpdir)

    try:
        extras = backup.ExtrasPaths(tmpdir)
        restore_files(backup_path, extras, log)
    finally:
        shutil.rmtree(tmpdir)

class DontWriteIfNone:
    def __init__(self, fh=None):
        self.fh = fh

    def write(self, s):
        if self.fh:
            self.fh.write(str(s))

def restore_files(backup_path, extras, log=None):
    log = DontWriteIfNone(log)

    def userdb_merge(old_etc, new_etc):
        old_passwd = join(old_etc, "passwd")
        new_passwd = join(new_etc, "passwd")
        
        old_group = join(old_etc, "group")
        new_group = join(new_etc, "group")

        def r(path):
            return file(path).read()

        return userdb.merge(r(old_passwd), r(old_group), 
                            r(new_passwd), r(new_group))

    passwd, group, uidmap, gidmap = userdb_merge(extras.etc.path, "/etc")

    def iter_apply_overlay(overlay, root):
        def walk(dir):
            fnames = []
            subdirs = []

            for dentry in os.listdir(dir):
                path = join(dir, dentry)

                if not islink(path) and isdir(path):
                    subdirs.append(path)
                else:
                    fnames.append(dentry)

            yield dir, fnames

            for subdir in subdirs:
                for val in walk(subdir):
                    yield val

        class OverlayError:
            def __init__(self, path, exc):
                self.path = path
                self.exc = exc

            def __str__(self):
                return "OVERLAY ERROR @ %s: %s" % (self.path, self.exc)

        overlay = overlay.rstrip('/')
        for overlay_dpath, fnames in walk(overlay):
            root_dpath = root + overlay_dpath[len(overlay) + 1:]
            if exists(root_dpath) and not isdir(root_dpath):
                os.remove(root_dpath)

            for fname in fnames:
                overlay_fpath = join(overlay_dpath, fname)
                root_fpath = join(root_dpath, fname)

                try:
                    if exists(root_fpath):
                        if not islink(root_fpath) and isdir(root_fpath):
                            shutil.rmtree(root_fpath)
                        else:
                            os.remove(root_fpath)

                    root_fpath_parent = dirname(root_fpath)
                    if not exists(root_fpath_parent):
                        os.makedirs(root_fpath_parent)

                    shutil.move(overlay_fpath, root_fpath)
                    yield root_fpath
                except Exception, e:
                    yield OverlayError(root_fpath, e)

    for val in iter_apply_overlay(backup_path, "/"):
        print >> log, val

    limits = []
    changes = Changes.fromfile(extras.fsdelta, limits)

    for actions in (changes.statfixes(uidmap, gidmap), changes.deleted()):
        for action in actions:
            print >> log, action
            action()

    def w(path, s):
        file(path, "w").write(str(s))

    w("/etc/passwd", passwd)
    w("/etc/group", group)

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'h', 
                                       ['skip-files', 'skip-database', 'skip-packages',
                                        'no-rollback'])
                                        
    except getopt.GetoptError, e:
        usage(e)

    skip_files = False
    skip_database = False
    skip_packages = False
    no_rollback = False
    for opt, val in opts:
        if opt == '--skip-files':
            skip_files = True
        elif opt == '--skip-database':
            skip_database = True
        elif opt == '--skip-packages':
            skip_packages = True
        elif opt == '--no-rollback':
            no_rollback = True
        elif opt == '-h':
            usage()

    if len(args) < 2:
        usage()


    address, keyfile = args[:2]
    limits = args[2:]

    # debug
    for var in ('address', 'keyfile', 'limits', 'skip_files', 'skip_database', 'skip_packages', 'no_rollback'):
        print "%s = %s" % (var, `locals()[var]`)

if __name__=="__main__":
    args = sys.argv[1:]
    funcname = args[0]
    locals()[funcname]()