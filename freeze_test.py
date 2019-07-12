import datetime
import importlib
import logging
import os
import os.path
import shutil
import tempfile
import unittest
import urllib.parse

import freeze

# Uncommenting this can be handy for examining why test fail
#logging.basicConfig(level=logging.DEBUG)

# Mapping of freeze module level setting attributes to their default
# values
default_settings = {
    'repository': None,
    'force': None,
    'carry_on': False,
    'freeze_date': None,
    'settings_file': 'settings.ini',
    'dry_run': False
}

minimal_commandline_args = {
    'args': [
        "https://dummy.repo.tld/some-repo.git",
        "2000-01-01"
    ],
    'test_values': {
        'repository': "https://dummy.repo.tld/some-repo.git",
        'freeze_date': datetime.date(2000, 1, 1)
    }
}

class TestCommandLine(unittest.TestCase):
    def _check_setting_values(self, **kwargs):
        """
        Checks the freeze module level setting attributes are correct.

        Specify attribute_name=value as a keyword argument to test any
        attributes that should not have their default value.
        """
        for setting, value in default_settings.items():
            test_setting = getattr(freeze, setting)
            test_value = value
            if setting in kwargs:
                test_value = kwargs[setting]

            # Make failure messages easier to trace
            msg="Setting %s is not %s" % (setting, test_value)

            # Make sure booleans remain booleans
            if value is True or value is False:
                self.assertIs(test_setting, test_value, msg=msg)
            # Things that are initially None may become defined to
            # another type.
            elif value is None and test_value is None:
                self.assertIs(test_setting, None, msg=msg)
            else:
                self.assertEqual(test_setting, test_value, msg=msg)


    def _reset_settings(self):
        # Re-import the library which should cause the variables to
        # revert to their initial values.
        importlib.reload(freeze)

    def _test_args(
        self, args_list=None, add_min_args=True, **kwargs
    ):
        """
        args:
            args_list: list to add the minimal args to and test.  Will
                be set to exactly the minimum list if set to its default
                value of None.
            add_min_args: set to False to not extend args_list with
                minimum mandatory positional arguments (defaults to
                true)

            Specify attribute_name=value as a keyword argument to test
            any attributes that should not have their default value.
        """
        if args_list is None:
            args = minimal_commandline_args['args']
        else:
            args = args_list
            if add_min_args:
                args.extend(minimal_commandline_args['args'])
        freeze.process_commandline(args)
        test_values = minimal_commandline_args['test_values']
        test_values.update(kwargs)
        self._check_setting_values(**test_values)


    def setUp(self):
        # Called before each test
        logging.debug("Checking settings are in default state before test.")
        self._check_setting_values()

    def tearDown(self):
        # Called after each test
        logging.debug("Resetting settings to default state after test.")
        self._reset_settings()

    def test_process_commandline_missing_args(self):
        # No arguments
        with self.assertRaises(SystemExit) as cm:
            self._test_args([], add_min_args=False)
        # Argparser exists status 2 on invalid arguments
        self.assertEqual(
            cm.exception.code, 2,
            msg="No argument command line did not exit status 2"
        )

        # Missing Date
        with self.assertRaises(SystemExit) as cm:
            self._test_args(
                ["https://dummy.repo.tld/some-repo.git"],
                add_min_args=False
            )
        # Argparser exists status 2 on invalid arguments
        self.assertEqual(
            cm.exception.code, 2,
            msg="URL-only command line did not exit status 2"
        )

        # Missing URL
        with self.assertRaises(SystemExit) as cm:
            self._test_args(["2000-01-01"], add_min_args=False)
        # Argparser exists status 2 on invalid arguments
        self.assertEqual(
            cm.exception.code, 2,
            msg="Date-only command line did not exit status 2"
        )

    def test_basic_commandline(self):
        self._test_args([])
        self.assertFalse(
            freeze.logger.isEnabledFor(logging.DEBUG),
            msg="Logger is enabled at Debug level without -d/--debug"
        )

    def test_process_commandline_debug_short(self):
        self._test_args(['-d'], dry_run=True)
        logging.warning("Effective level for logger: %s", freeze.logger.getEffectiveLevel())
        logging.warning("Logger is enabled for debug: %s", freeze.logger.isEnabledFor(logging.DEBUG))
        self.assertTrue(
            freeze.logger.isEnabledFor(logging.DEBUG),
            msg="Logger is not enabled at Debug level with -d option."
        )

    def test_process_commandline_debug_long(self):
        self._test_args(['--debug'], dry_run=True)
        self.assertTrue(
            freeze.logger.isEnabledFor(logging.DEBUG),
            msg="Logger is not enabled at Debug level with --debug option."
        )

    def test_process_commandline_debug_no_dry_run(self):
        self._test_args(['-d', '--no-dry-run'], dry_run=False)
        self.assertTrue(
            freeze.logger.isEnabledFor(logging.DEBUG),
            msg="Logger is not enabled at Debug level with -d and --no-dry-run"
                " options."
        )

    def test_process_commandline_dry_no_dry_conflict(self):
        with self.assertRaises(SystemExit) as cm:
            self._test_args(['--dry-run', '--no-dry-run'])
        self.assertEqual(
            cm.exception.code, 1,
            msg="--dry-run and --no-dry-run together should exit with error"
                " state"
        )
   


class UrlTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """
        Create a dummy "cloned" repo directory - for test cases that
        require files.
        """
        if getattr(cls, '_tmprepodir', None) is None:
            cls._tmprepodir = tempfile.mkdtemp()
            logging.debug("Created temporary 'repository' directory: %s", cls._tmprepodir)

    @classmethod
    def tearDownClass(cls):
        try:
            shutil.rmtree(cls._tmprepodir)
            logging.debug("Cleaned up temporary 'repository' directory: %s", cls._tmprepodir)
            cls._tmprepodir = None
        except AttributeError:
            # If no _tmprepodir, carry on as through we hadn't tried to
            # delete it (it doesn't exist).
            pass

    def test_github_io_url_converstion(self):
        """
        Test _github_io_to_github_com

        Ensures that it fails as expected with non-github.io addresses
        and correctly converts github.io ones.
        """

        self.assertEqual(
            freeze._github_io_to_github_com(
                urllib.parse.urlparse(
                    "https://bear-carpentries.github.io/2019-01-07-bham"
                )
            ).geturl(),
            "https://github.com/bear-carpentries/2019-01-07-bham"
        )
        self.assertEqual(
            freeze._github_io_to_github_com(
                urllib.parse.urlparse(
                    "https://bear-carpentries.github.io/2019-01-07-bham/"
                )
            ).geturl(),
            "https://github.com/bear-carpentries/2019-01-07-bham/"
        )

        # Should raise an assertion error if the passed url object is
        # not of a github.io disposition.
        self.assertRaises(
            AssertionError,
            freeze._github_io_to_github_com,
                urllib.parse.urlparse(
                    "https://github.com/bear-carpentries/2019-01-07-bham"
                )
        )

    def test_decompose_urls(self):
        """
        Test _get_organistaion_repo_from_url

        Ensures it correctly decomposes the followuing syles of url:
          * github.com/<org>/<repo>
          * github.com/<org>/<repo>/
          * <org>.github.io/<repo>
          * <org>.github.io/<repo>/
        """
        self.assertEqual(
            freeze._get_organisation_repo_from_url(
                "https://github.com/bear-carpentries/2019-01-07-bham"
            ),
            ('bear-carpentries', '2019-01-07-bham')
        )
        self.assertEqual(
            freeze._get_organisation_repo_from_url(
                "https://github.com/bear-carpentries/2019-01-07-bham/"
            ),
            ('bear-carpentries', '2019-01-07-bham')
        )
        self.assertEqual(
            freeze._get_organisation_repo_from_url(
                "https://bear-carpentries.github.io/2019-01-07-bham"
            ),
            ('bear-carpentries', '2019-01-07-bham')
        )
        self.assertEqual(freeze._get_organisation_repo_from_url("https://bear-carpentries.github.io/2019-01-07-bham/"), ('bear-carpentries', '2019-01-07-bham'))

    def test_regression_spaces_at_end_of_url(self):
        # Tear-up - create a dummy schedule file with invalid urls in it
        schedule_path = freeze._get_schedule_file_relative_path()
        os.makedirs(os.path.join(self._tmprepodir, os.path.dirname(schedule_path)))
        with open(os.path.join(self._tmprepodir, schedule_path), 'w') as f:
            # Write a dummy schedule file with links that end in space in them
            f.write("""
            <html>
                <body>
                    <p>
                        <ul>
                            <li><a href="https://bham-carpentries.github.io/shell-novice ">Shell-Novice</a></li>
                            <li><a href="https://bham-carpentries.github.io/python-novice-inflammation ">Python</a></li>
                        </ul>
                    </p>
                </body>
            </html>
                """)

        self.assertEqual(
            freeze.get_repos_to_freeze(self._tmprepodir),
            [
                ('https://bham-carpentries.github.io/shell-novice ', 'https://github.com/bham-carpentries/shell-novice'),
                ('https://bham-carpentries.github.io/python-novice-inflammation ', 'https://github.com/bham-carpentries/python-novice-inflammation')
            ]
        )

        # Tear-down - delete dummy schedule (mainly to ensure file doesn't interfere with other tests - directories will be cleaned up by fixture (class-level) tear-down)
        os.remove(os.path.join(self._tmprepodir, schedule_path))

    def test_regression_github_io_urls_fail(self):
        freeze.load_settings()
        freeze.dry_run = True # Don't want it changing anything
        with self.assertWarns(RuntimeWarning) as warning:
            freeze.do_freeze("https://bham-carpentries.github.io/2019-02-11-bham/")

        self.assertEqual(len(warning.warnings), 1)
        self.assertEqual(str(warning.warnings[0].message), "***TEST SET TO TRUE - ABORTING***")