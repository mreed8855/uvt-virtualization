#!/usr/bin/env python3
"""
    Test kvm using uvtool
    uvtvirt.py
    usage: uvtvirt.py [-h] [-i IMAGE] [--debug] [-l LOG_FILE]

    Run uvt-kvm with defaults
    uvtvirt.py --debug

    Specify a location for uvt-simplestreams-libvirt to retrive an image
    uvtvirt.py -i http://cloud-images.ubuntu.com/daily/server/daily/

    Specify a cloud image for uvt-kvm create to create a vm
    uvtvirt.py -i file:///home/ubuntu/focal-server-cloudimg-amd64.img
"""

from argparse import ArgumentParser
import os
import logging
import lsb_release
import requests
import shlex
from subprocess import (
    Popen,
    PIPE,
    DEVNULL,
    CalledProcessError,
    check_output,
    call
)
import sys
import tempfile
import tarfile
import time
import apt
import urllib.request
from urllib.parse import urlparse
from uuid import uuid4

DEFAULT_TIMEOUT = 500


class RunCommand(object):
    """
    Runs a command and can return all needed info:
    * stdout
    * stderr
    * return code
    * original command

    Convenince class to avoid the same repetitive code to run shell
    commands.
    """

    def __init__(self, cmd=None):
        self.stdout = None
        self.stderr = None
        self.returncode = None
        self.cmd = cmd
        self.run(self.cmd)

    def run(self, cmd):
        proc = Popen(shlex.split(cmd), stdout=PIPE, stderr=PIPE,
                     stdin=DEVNULL, universal_newlines=True)
        self.stdout, self.stderr = proc.communicate()
        self.returncode = proc.returncode


class UVTKVMTest(object):

    def __init__(self, image=None):
        self.image = image
        self.release = lsb_release.get_distro_information()["CODENAME"]
        self.arch = check_output(['dpkg', '--print-architecture'],
                                 universal_newlines=True).strip()
        self.name = tempfile.mktemp()[5:]

    def run_command(self, cmd):
        task = RunCommand(cmd)
        if task.returncode != 0:
            logging.error('Command {} returnd a code of {}'.format(
                task.cmd, task.returncode))
            logging.error(' STDOUT: {}'.format(task.stdout))
            logging.error(' STDERR: {}'.format(task.stderr))
            return False
        else:
            logging.debug('Command {}:'.format(task.cmd))
            if task.stdout != '':
                logging.debug(' STDOUT: {}'.format(task.stdout))
            elif task.stderr != '':
                logging.debug(' STDERR: {}'.format(task.stderr))
            else:
                logging.debug(' Command returned no output')
            return True

    def check_package(self, pkg_name):
        cache = apt.Cache()

        pkg = cache[pkg_name]
        if pkg.is_installed:
            print("{} already installed".format(pkg_name))
        else:
            pkg.mark_install()

        try:
            cache.commit()
        except Exception:
            print("Install of {} failed".format(sys.stderr))

    def get_image_or_source(self):
        """
        An image can be specifed in a filesytem path and used directly in
        uvt-create with the backing-image option or a url can be
        specifed and used in uvt-simpletreams to generate an image.
        """
        url = urlparse(self.image)

        if url.scheme == 'file':
            logging.debug("Cloud image exists locally at %s" % url.path)
            self.image = url.path
        else:
            cmd = ("uvt-simplestreams-libvirt sync release={} "
                   "arch={}".format(self.release, self.arch))

            if url.scheme == 'http':
                # Path specified to use -source option
                logging.debug("Using --source option for uvt-simpletreams")
                cmd = cmd + " --source {} ".format(self.image)

            logging.debug("uvt-simplestreams-libvirt sync")
            if not self.run_command(cmd):
                return False
        return True

    def cleanup(self):
        """
        A combination of virsh destroy/undefine is used instead of
        uvt-kvm destroy.  When using uvt-kvm destroy the following bug
        is seen:
        https://bugs.launchpad.net/ubuntu/+source/uvtool/+bug/1452095
        """
        # Destroy vm
        logging.debug("Destroy VM")
        if not self.run_command('virsh destroy {}'.format(self.name)):
            return False

        # Virsh undefine
        logging.debug("Undefine VM")
        if not self.run_command('virsh undefine {}'.format(self.name)):
            return False

        # Purge/Remove simplestreams image
        if not self.run_command("uvt-simplestreams-libvirt purge"):
            return False
        return True

    def start(self):
        # Generate ssh key if needed
        home_dir = os.environ['HOME']
        ssh_key_file = "{}/.ssh/id_rsa".format(home_dir)

        if not os.path.exists(ssh_key_file):
            self.run_command("mkdir -p {}/.ssh".format(home_dir))

            cmd = ('ssh-keygen -f {} -t rsa -N \'\''.format(ssh_key_file))
            if not self.run_command(cmd):
                return False

        # Create vm
        logging.debug("Creating VM")
        cmd = ('uvt-kvm create release={} {}'.format(self.release, self.name))

        if self.image.find(".img") > 0:
            cmd = cmd + " --backing-image-file {} ".format(self.image)

        if not self.run_command(cmd):
            return False

        logging.debug("Wait for VM to complete creation")
        if not self.run_command('uvt-kvm wait {}'.format(self.name)):
            return False

        logging.debug("List newly created vm")
        cmd = ("uvt-kvm list")
        if not self.run_command(cmd):
            return False

        logging.debug("Verify VM was created with ssh")
        if not self.run_command('uvt-kvm ssh {}'.format(self.name)):
            return False

        logging.debug("Verify VM was created with ssh and run a command")
        if not self.run_command('uvt-kvm ssh {} \"lsb_release -a \"'
                                .format(self.name)):
            return False

        return True


def test_uvtkvm(args):
    logging.debug("Executing UVT KVM Test")
    image = ""
    source = ""

    # First in priority are environment variables.
    if 'UVT_IMAGE_OR_SOURCE' in os.environ:
        image = os.environ['UVT_IMAGE_OR_SOURCE']

    if args.image:
        image = args.image

    uvt_test = UVTKVMTest(image)
    uvt_test.check_package("uvtool")
    uvt_test.check_package("uvtool-libvirt")
    uvt_test.get_image_or_source()
    result = uvt_test.start()
    uvt_test.cleanup()

    if result:
        print("PASS: VM was succssfully started and checked")
        sys.exit(0)
    else:
        print("FAIL: VM was not started and/or checked")
        sys.exit(1)


def main(args):
    parser = ArgumentParser(description="Virtualization Test")
    parser.add_argument('-i', '--image', type=str, default=None)
    parser.add_argument('--debug', dest='log_level',
                        action="store_const", const=logging.DEBUG,
                        default=logging.INFO)
    parser.add_argument(
        '-l', '--log-file', default='virt_debug',
        help="Location for debugging output log. Defaults to %(default)s.")
    parser.set_defaults(func=test_uvtkvm)
    args = parser.parse_args()

    try:
        logging.basicConfig(level=args.log_level)
    except AttributeError:
        pass  # avoids exception when trying to run without specifying 'kvm'

    # silence normal output from requests module
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    # Verify args
    try:
        args.func(args)
        print("in try block")

    except AttributeError:
        parser.print_help()
        return 1

    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main(sys.argv))
