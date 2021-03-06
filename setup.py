#! /usr/bin/python -tt
"""setup - Generic project setup.py"""
# Copyright (C) 2007-2011  James Rowe <jnrowe@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import doctest
import os
import shutil
import sys
import time

from setuptools import setup
from setuptools.command.sdist import (finders, sdist)
from setuptools import Command
from distutils.util import convert_path

from distutils.archive_util import make_archive
from distutils.command.clean import clean
from distutils.dep_util import newer
from distutils.errors import (DistutilsFileError, DistutilsModuleError)
from distutils.file_util import write_file
from distutils.util import execute

try:
    from email.utils import parseaddr
except ImportError:  # Python2.4
    from email.Utils import parseaddr

from glob import glob

try:
    from subprocess import check_call
except ImportError:  # Python2.4
    from subprocess import call as sp_call

    def check_call(*args, **kwargs):
        retval = sp_call(*args, **kwargs)
        if retval:
            raise OSError("Command execution failed!")

from subprocess import (PIPE, Popen)

try:
    from docutils.core import publish_cmdline
    from docutils import nodes
    from docutils.parsers.rst import directives
    #: True if ``docutils`` module is available
    DOCUTILS = True
except ImportError:
    DOCUTILS = False
try:
    from pygments import highlight
    from pygments.lexers import get_lexer_by_name
    from pygments.formatters import HtmlFormatter
    #: True if ``pygments`` module is available
    PYGMENTS = True
except ImportError:
    PYGMENTS = False

import __pkg_data__
import test

#: Base URL for links
BASE_URL = "http://jnrowe.github.com/"
PROJECT_HOMEPAGE = "%s%s" % (BASE_URL, __pkg_data__.MODULE.__name__)
PROJECT_URL = "https://github.com/JNRowe/%s" % __pkg_data__.MODULE.__name__

if sys.version_info < (2, 5, 0, 'final'):
    raise SystemError("Requires Python v2.5+")


#{ Generated data file functions
def write_changelog(filename):
    """Generate a ChangeLog from SCM repo

    :type filename: ``str``
    :param filename: Filename to write :file:`ChangeLog` to

    """
    if __pkg_data__.SCM == "hg" and os.path.isdir(".hg"):
        print('Building ChangeLog from Mercurial repository')
        options = "log --no-merges --style changelog"
    elif __pkg_data__.SCM == "git" and os.path.isdir(".git"):
        print('Building ChangeLog from Git repository')
        files = call_scm("ls-tree --name-only HEAD")
        options = "log --graph --date=short --stat -- %s" % " ".join(files)
    else:
        print("Unable to build ChangeLog, dir is not a %s clone"
              % __pkg_data__.SCM)
        return False
    try:
        call_scm(options, stdout=open(filename, "w"))
    finally:
        # Remove the ChangeLog if call_scm() failed
        if os.stat(filename).st_size == 0:
            os.unlink(filename)


def write_manifest(files):
    """Generate a :file:`MANIFEST` file

    :type files: ``list``
    :param files: Filenames to include in :file:`MANIFEST`

    """
    open("MANIFEST", "w").write("\n".join(sorted(files)) + "\n")
#}


#{ Implementation utilities
def call_scm(options, *args, **kwargs):
    """SCM command line tools

    :type options: ``list``
    :param options: SCM command options
    :type args: ``list``
    :param args: Positional arguments for ``subprocess.Popen``
    :type kwargs: ``dict``
    :param kwargs: Keyword arguments for ``subprocess.Popen``
    :rtype: ``str``
    :return: SCM command output
    :raise OSError: SCM command not found
    :raise ValueError: Unknown SCM type

    """
    options = options.split()
    if "stdout" in kwargs:
        redirect = True
    else:
        redirect = False
        kwargs["stdout"] = PIPE
    if __pkg_data__.SCM in ("hg", "git"):
        options.insert(0, __pkg_data__.SCM)
    else:
        raise ValueError("Unknown SCM type %r" % (__pkg_data__.SCM, ))
    try:
        process = Popen(options, *args, **kwargs)
    except OSError:
        print("Error calling %r, is %s installed?"
              % (options[0], __pkg_data__.SCM))
        raise
    process.wait()
    if not process.returncode == 0:
        print("%r completed with %i return code"
              % (options[0], process.returncode))
        sys.exit(process.returncode)
    if redirect:
        return True
    else:
        return process.stdout.read()


def gen_desc(doc):
    """Pull simple description from docstring

    :type doc: ``str``
    :param doc: Docstring to manipulate
    :rtype: ``str``
    :return: Description string suitable for :class:`Command` class's
        description

    """
    desc = doc.splitlines()[0].lstrip()
    return desc[0].lower() + desc[1:]


class NoOptsCommand(Command):
    """Abstract class for simple :mod:`distutils` command implementation"""

    def initialize_options(self):
        """Set default values for options"""
        pass

    def finalize_options(self):
        """Finalize, and test validity, of options"""
        pass
#}


class BuildDoc(NoOptsCommand):
    """Build project documentation

    .. attribute:: force

       Force documentation generation

    """
    description = gen_desc(__doc__)
    #: `BuildDoc`'s option mapping
    user_options = [
        ('force', 'f',
         "force documentation generation"),
    ]
    #: `BuildDoc` class' boolean options
    boolean_options = ['force']

    def initialize_options(self):
        """Set default values for options"""
        self.force = False

    def run(self):
        """Build the required documentation"""
        if not DOCUTILS:
            raise DistutilsModuleError("docutils import failed, "
                                       "can't generate documentation")
        if not PYGMENTS:
            # This could be a warning with conditional support for users, but
            # how would coloured output be guaranteed in releases?
            raise DistutilsModuleError("pygments import failed, "
                                       "can't generate documentation")

        def pygments_directive(name, arguments, options, content, lineno,
                               content_offset, block_text, state,
                               state_machine):
            """Code colourising directive for :mod:`docutils`"""
            # Previously we tested to see if the lexer existed and set a
            # default of text if it didn't, but this hides bugs such as a typo
            # in the directive
            lexer = get_lexer_by_name(arguments[0])
            if sys.version_info[:2] >= (3, 0):
                parsed = highlight('\n'.join(content), lexer,
                                   pygments_formatter)
            else:
                parsed = highlight(unicode('\n'.join(content)), lexer,
                                   HtmlFormatter())
            return [nodes.raw('', parsed, format='html')]
        pygments_directive.arguments = (1, 0, 1)
        pygments_directive.content = 1
        directives.register_directive('code-block', pygments_directive)

        for source in sorted(["NEWS.rst", "README.rst"] + glob('doc/*.rst')):
            dest = os.path.splitext(source)[0] + '.html'
            if self.force or newer(source, dest):
                print('Building file %s' % dest)
                if self.dry_run:
                    continue
                publish_cmdline(writer_name='html',
                                argv=['--source-link', '--strict',
                                      '--generator',
                                      '--stylesheet-path=doc/docutils.css',
                                      '--link-stylesheet', source, dest])
        print("Building sphinx tree")
        if not os.path.isdir("doc/html"):
            os.mkdir("doc/html")
        check_call(["sphinx-build", "-b", "html", "-d", "doc/source/.doctrees",
                    "doc/source", "doc/html"])

        files = glob("%s/*.py" % __pkg_data__.MODULE.__name__)
        files.extend(["%s.py" % i.__name__ for i in __pkg_data__.SCRIPTS])
        if self.force or not os.path.isfile("ChangeLog"):
            execute(write_changelog, ("ChangeLog", ))
        else:
            cl_time = os.stat("ChangeLog").st_mtime
            if __pkg_data__.SCM == "hg" and os.path.isdir(".hg"):
                output = call_scm("tip --template '{date}'")
                tip_time = float(output[1:output.find("-")])
            elif __pkg_data__.SCM == "git" and os.path.isdir(".git"):
                output = call_scm("log -n 1 --pretty=format:%at HEAD")
                tip_time = int(output)
            else:
                print("Unable to build ChangeLog, dir is not a %s clone"
                      % __pkg_data__.SCM)
                return False
            if tip_time > cl_time:
                execute(write_changelog, ("ChangeLog", ))

        if hasattr(__pkg_data__, "BuildDoc_run"):
            __pkg_data__.BuildDoc_run(self.dry_run, self.force)


#{ Distribution utilities
def scm_finder(*none):
    """Find files for distribution tarball

    This is only used when ``setuptools`` is imported, simply to create a valid
    list of files to distribute.  Standard setuptools only works with CVS.
    Without this it *appears* to work, but only distributes a very small subset
    of the package.

    .. seealso::

       :class:`MySdist.get_file_list`

    :type none: any
    :param none: Just for compatibility
    """
    # setuptools documentation says this shouldn't be a hard fail, but we won't
    # do that as it makes builds entirely unpredictable
    if __pkg_data__.SCM == "hg":
        output = call_scm("locate")
    elif __pkg_data__.SCM == "git":
        output = call_scm("ls-tree -r --full-name --name-only HEAD")
    distributed_files = output.splitlines()
    distributed_files.append(".%s_version" % __pkg_data__.SCM)
    distributed_files.append("ChangeLog")
    distributed_files.extend(glob("*.html"))
    distributed_files.extend(glob("doc/*.html"))
    for path, directory, filenames in os.walk("html"):
        for filename in filenames:
            distributed_files.append(os.path.join(path, filename))
    return distributed_files
    if __pkg_data__.SCM == "hg":
        finders.append((convert_path('.hg/dirstate'), scm_finder))
    elif __pkg_data__.SCM == "git":
        finders.append((convert_path('.git/index'), scm_finder))


class ScmSdist(sdist):
    """Create a source distribution tarball

    .. seealso::

       :class:`sdist`

    .. attribute: repo

       SCM repository object

    """
    description = gen_desc(__doc__)
    #: `ScmSdist`'s option mapping
    user_options = [
        ('force-build', 'b', "force build with stale version number"),
    ] + sdist.user_options
    boolean_options = ['force-build']

    def initialize_options(self):
        """Set default values for options"""
        sdist.initialize_options(self)
        self.force_build = False
        if __pkg_data__.SCM == "hg":
            output = call_scm("status -mard")
        elif __pkg_data__.SCM == "git":
            output = call_scm("diff --name-status")
        else:
            raise ValueError("Unknown SCM type %r" % (__pkg_data__.SCM, ))
        if not len(output) == 0:
            raise DistutilsFileError("Uncommitted changes!")

    def get_file_list(self):
        """Generate MANIFEST file contents from SCM"""
        manifest_files = scm_finder()
        execute(write_manifest, [manifest_files], "writing MANIFEST")
        sdist.get_file_list(self)

    def make_distribution(self):
        """Update versioning data and build distribution"""
        news_format = "%s - " % __pkg_data__.MODULE.__version__
        news_matches = [line for line in open("NEWS.rst")
                        if line.startswith(news_format)]
        if not any(news_matches):
            print("NEWS.rst entry for %r missing"
                  % (__pkg_data__.MODULE.__version__, ))
            sys.exit(1)
        news_time = time.mktime(time.strptime(news_matches[0].split()[-1],
                                "%Y-%m-%d"))
        if time.time() - news_time > 86400 and not self.force_build:
            print("NEWS.rst entry is older than a day, version may not have "
                  "been updated")
            sys.exit(1)
        execute(self.write_version, ())
        sdist.make_distribution(self)

    def write_version(self):
        """Store the current SCM changeset identifier in a file"""
        if __pkg_data__.SCM == "hg":
            # This could use `hg identify' but that outputs other unused
            # information
            output = call_scm("tip --template '{node|short}'")[1:-1]
        elif __pkg_data__.SCM == "git":
            output = call_scm("log -n 1 --pretty=format:%T HEAD")
        else:
            raise ValueError("Unknown SCM type %r" % (__pkg_data__.SCM, ))
        write_file(".%s_version" % __pkg_data__.SCM, (output, ))


class Snapshot(NoOptsCommand):
    """Build a daily snapshot tarball"""
    description = gen_desc(__doc__)
    #: `Snapshot`'s option mapping
    user_options = []

    def run(self):
        """Prepare and create tarball"""
        snapshot_name = "%s-%s" % (__pkg_data__.MODULE.__name__,
                                   time.strftime("%Y-%m-%d"))
        snapshot_location = "dist/%s" % snapshot_name
        if os.path.isdir(snapshot_location):
            execute(shutil.rmtree, (snapshot_location, ))
        execute(self.generate_tree, (snapshot_location, ))
        execute(write_changelog, ("%s/ChangeLog" % snapshot_location, ))
        execute(make_archive, (snapshot_location, "bztar", "dist",
                               snapshot_name))
        execute(shutil.rmtree, (snapshot_location, ))

    @staticmethod
    def generate_tree(snapshot_name):
        """Generate a clean SCM clone"""
        if __pkg_data__.SCM == "hg":
            call_scm("archive %s" % snapshot_name)
        elif __pkg_data__.SCM == "git":
            basename = os.path.basename(snapshot_name)
            call_scm("git archive --prefix=%s/ HEAD" % basename,
                     stdout=open("%s.tar" % basename, "w"))
            check_call(("tar xfv %s.tar -C %s" % (basename, "dist")).split())
            os.remove("%s.tar" % basename)
        else:
            raise ValueError("Unknown SCM type %r" % (__pkg_data__.SCM, ))
#}


class MyClean(clean):
    """Clean built and temporary files

    .. seealso::

       :class:`clean`

    """
    description = gen_desc(__doc__)

    def run(self):
        """Remove built and temporary files"""
        clean.run(self)
        if self.all:
            for filename in [".git_version", ".hg_version", "ChangeLog",
                             "MANIFEST"] \
                + glob("*.html") + glob("doc/*.html") \
                + glob("%s/*.pyc" % __pkg_data__.MODULE.__name__):
                if os.path.exists(filename):
                    os.unlink(filename)
            execute(shutil.rmtree, ("html", True))
            execute(shutil.rmtree, ("doc/html", True))
            execute(shutil.rmtree, ("doc/source/.doctrees", True))
        if hasattr(__pkg_data__, "MyClean_run"):
            __pkg_data__.MyClean_run(self.dry_run, self.force)


#{ Testing utilities
class MyTest(NoOptsCommand):
    """Abstract class for test command implementations"""
    #: `MyTest`'s option mapping
    user_options = [
        ('exit-on-fail', 'x',
         "exit on first failure"),
    ]
    boolean_options = ['exit-on-fail']

    def initialize_options(self):
        """Set default values for options"""
        self.exit_on_fail = False
        self.doctest_opts = doctest.REPORT_UDIFF | doctest.NORMALIZE_WHITESPACE
        #: Mock objects to include for test framework
        self.extraglobs = {
            "urllib": test.mock.urllib,
        }
        if hasattr(__pkg_data__, "TEST_EXTRAGLOBS"):
            for key, value in __pkg_data__.TEST_EXTRAGLOBS.items():
                if value:
                    self.extraglobs[key] = value
                else:
                    self.extraglobs[key] = getattr(test.mock, key)

    def run(self):
        """Run doctest tests"""
        if self.__class__.__name__ == "TestCode":
            files = glob("%s/*.py" % __pkg_data__.MODULE.__name__)
            files.extend(["%s.py" % i.__name__ for i in __pkg_data__.SCRIPTS])
            test_func = doctest.testmod
            hook = "TestCode_run"
        else:
            files = ['README.rst', ] + glob("doc/*.rst")
            test_func = doctest.testfile
            hook = "TestDoc_run"
        tot_fails = 0
        tot_tests = 0
        for filename in sorted(files):
            if self.__class__.__name__ == "TestCode":
                print('  Testing python file %s' % filename)
                module = os.path.splitext(filename)[0].replace("/", ".")
                if module.endswith("__init__"):
                    module = module[:-9]
                testable = sys.modules[module]
            else:
                print('  Testing documentation file %s' % filename)
                testable = filename
            fails, tests = test_func(testable, optionflags=self.doctest_opts,
                                     extraglobs=self.extraglobs)
            print("    %i tests run, %i failed" % (tests, fails))
            if self.exit_on_fail and not fails == 0:
                sys.exit(1)
            tot_fails += fails
            tot_tests += tests
        print("Total of %i tests run, %i failed" % (tot_tests, tot_fails))
        if hasattr(__pkg_data__, hook):
            getattr(__pkg_data__, hook)(self.dry_run, self.force)


class TestDoc(MyTest):
    """Test documentation's code examples

    .. seealso:

       :class:`MyTest`

    """
    description = gen_desc(__doc__)


class TestCode(MyTest):
    """Test script and module's :mod:`doctest` examples

    .. seealso::

       :class:`MyTest`

    """
    description = gen_desc(__doc__)
#}


def main():
    # Force tests to be run, and documentation to be built, before creating a
    # release.
    if "sdist" in sys.argv:
        for test in ("test_code", "test_doc"):
            if not test in sys.argv:
                sys.argv = [sys.argv[0], ] + [test, "-x"] + sys.argv[1:]
        if not "build_doc" in sys.argv:
            sys.argv.insert(1, "build_doc")

    setup(
        name=__pkg_data__.MODULE.__name__,
        version=__pkg_data__.MODULE.__version__,
        description=__pkg_data__.DESCRIPTION,
        long_description=__pkg_data__.LONG_DESCRIPTION,
        author=parseaddr(__pkg_data__.MODULE.__author__)[0],
        author_email=parseaddr(__pkg_data__.MODULE.__author__)[1],
        url=PROJECT_HOMEPAGE,
        download_url="%s/tarball/%s-%s.tar.gz" \
            % (PROJECT_URL, __pkg_data__.MODULE.__name__,
               __pkg_data__.MODULE.__version__),
        packages=[__pkg_data__.MODULE.__name__],
        include_package_data=True,
        scripts=["%s.py" % i.__name__ for i in __pkg_data__.SCRIPTS],
        test_suite=__pkg_data__.TEST_SUITE,
        test_requires=__pkg_data__.TEST_REQUIRES,
        zip_safe=False,
        license=__pkg_data__.MODULE.__license__,
        keywords=" ".join(__pkg_data__.KEYWORDS),
        classifiers=__pkg_data__.CLASSIFIERS,
        obsoletes=__pkg_data__.OBSOLETES,
        options={'sdist': {'formats': 'bztar'}},
        cmdclass={
            'build_doc': BuildDoc, 'clean': MyClean, 'sdist': ScmSdist,
            'snapshot': Snapshot, 'test_doc': TestDoc, 'test_code': TestCode,
        },
        install_requires=__pkg_data__.INSTALL_REQUIRES,
        entry_points=__pkg_data__.ENTRY_POINTS,
    )

if __name__ == "__main__":
    main()
