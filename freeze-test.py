import logging
import os
import os.path
import shutil
import tempfile
import unittest
import urllib.parse

import freeze

# Uncommenting this can be handy for examining why test fail
logging.basicConfig(level=logging.DEBUG)

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
		freeze.settings = freeze.read_settings(freeze.settings_file)
		with self.assertWarns(RuntimeWarning) as warning:
			freeze.do_freeze("https://bham-carpentries.github.io/2019-02-11-bham/", _test=True)
			self.assertEqual(len(warning.warnings), 1)
			self.assertEqual(str(warning.warnings[0].message), "***TEST SET TO TRUE - ABORTING***")