#!/usr/bin/python
"""
Backup the current system

Arguments:
    <override> := -?( /path/to/add/or/remove | mysql:database[/table] )

    Default overrides read from $CONF_OVERRIDES

Resolution order for options:
1) command line (highest precedence)
2) configuration files ($CONF)

Options:
    --profile=PATH          base profile path
                            default: $DEFAULT_PROFILE

    --keyfile=PATH          secret keyfile
                            default: $CONF_KEY

    --address=TARGET_URL    duplicity target URL
                            default: read from $CONF_ADDRESS

"""

import os
from os.path import *

import sys
import getopt

import re
from string import Template
from paths import Paths

import md5
import shutil

import changes
import dirindex

class Error(Exception):
    pass

class Overrides(list):
    @staticmethod
    def is_db_override(val):
        if re.match(r'^-?mysql:', val):
            return True
        else:
            return False

    @classmethod
    def fromfile(cls, inputfile):
        try:
            fh = file(inputfile)
        except:
            return cls()

        overrides = []
        for line in fh.readlines():
            line = re.sub(r'#.*', '', line).strip()
            if not line:
                continue

            overrides += line.split()

        def is_legal(override):
            if cls.is_db_override(override):
                return True

            if re.match(r'^-?/', override):
                return True

            return False

        for override in overrides:
            if not is_legal(override):
                raise Error(`override` + " is not a legal override")

        return cls(overrides)

    def fs(self):
        for val in self:
            if not self.is_db_override(val):
                yield val
    fs = property(fs)

    def db(self):
        for val in self:
            if self.is_db_override(val):
                yield val
    db = property(db)

    def __add__(self, b):
        cls = type(self)
        return cls(list.__add__(self, b))

class Conf:
    profile = "/usr/share/tklbam/profile"

    path = "/etc/tklbam"
    class Paths(Paths):
        files = [ 'address', 'key', 'overrides' ]
    paths = Paths(path)

    @staticmethod
    def _read_address(path):
        try:
            return file(path).read().strip()
        except:
            return None

    def __init__(self):
        self.keyfile = self.paths.key
        self.address = self._read_address(self.paths.address)
        self.overrides = Overrides.fromfile(self.paths.overrides)

def mcookie():
    return md5.md5(file("/dev/random").read(16)).hexdigest()

def create_key(keyfile):
    fh = file(keyfile, "w")
    os.chmod(keyfile, 0600)
    print >> fh, mcookie()
    fh.close()

def read_key(keyfile):
    return file(keyfile).read().strip()

def fatal(e):
    print >> sys.stderr, "error: " + str(e)
    sys.exit(1)

def usage(e=None):
    if e:
        print >> sys.stderr, "error: " + str(e)

    print >> sys.stderr, "Syntax: %s [ -options ] [ override ... ]" % sys.argv[0]
    tpl = Template(__doc__.strip())
    print >> sys.stderr, tpl.substitute(CONF=Conf.paths.path,
                                        CONF_OVERRIDES=Conf.paths.overrides,
                                        CONF_KEY=Conf.paths.key,
                                        CONF_ADDRESS=Conf.paths.address,
                                        DEFAULT_PROFILE=Conf.profile)
    sys.exit(1)

class BackupPaths(Paths):
    files = [ 'delta', 'newpkgs', 'myfs', 'etc' ]

class ProfilePaths(Paths):
    files = [ 'dirindex', 'dirindex.conf', 'selections' ]

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'h', 
                                       ['profile=', 'keyfile=', 'address='])
    except getopt.GetoptError, e:
        usage(e)

    conf = Conf()

    for opt, val in opts:
        if opt == '--profile':
            conf.profile = val
        elif opt == '--keyfile':
            if not exists(val):
                usage("keyfile %s does not exist" % `val`)
            conf.keyfile = val
        elif opt == '--address':
            conf.address = val
        elif opt == '-h':
            usage()

    conf.overrides += args

    if not conf.address:
        fatal("address not configured")

    if not exists(conf.keyfile):
        print "generating new secret key"
        create_key(conf.keyfile)

    key = read_key(conf.keyfile)

    if not isdir(conf.profile):
        fatal("profile dir %s doesn't exist" % `conf.profile`)

    profile_paths = ProfilePaths(conf.profile)
    backup_paths = BackupPaths("/TKLBAM")
    if isdir(backup_paths.path):
        shutil.rmtree(backup_paths.path)
    os.mkdir(backup_paths.path)

    paths = dirindex.read_paths(file(profile_paths.dirindex_conf))
    paths += conf.overrides.fs

    fh = file(backup_paths.delta, "w")
    for change in changes.whatchanged(profile_paths.dirindex, paths):
        print >> fh, change
    fh.close()
    
if __name__=="__main__":
    main()
