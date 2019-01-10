import logging
import unittest
import urllib.parse

import freeze

# Uncommenting this can be handy for examining why test fail
#logging.basicConfig(level=logging.DEBUG)

class UrlTest(unittest.TestCase):
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

