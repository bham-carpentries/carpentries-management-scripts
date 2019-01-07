#!/usr/bin/env python

# Core modules
import argparse
import configparser
import logging
import os.path
import re
import tempfile
import urllib.parse

# 3rd part imports
import dateparser
import git
import github

logger = logging.getLogger(__name__)
tempdirs = []
repository = None
force = None
freeze_date = None
settings_file = 'settings.ini'
settings = None

def process_commandline():
	parser = argparse.ArgumentParser(description='Freeze the version of a'
		' Birmingham Carpentries course for posterity.')
	parser.add_argument('-d', dest='debug', action='store_true',
        help='turn on debug mode (produces more detailed output)')
	parser.add_argument('-s', dest='settings_file', action='store',
		help='Specify the settings file - defaults to "settings.ini" in the'
		' current working directory.  See settings.ini.example for an example.')
	parser.add_argument('--force', dest='force', action='store_true',
        help='force freeze even if repos already looks frozen (based on url)')
	parser.add_argument('repo', action='store',
		help='Repository to freeze (i.e. the repository with the schedule'
		' whose repos you want to freeze)')
	parser.add_argument('date', action='store',
		help='Date to use for new (frozen) repositories.  Any date parseable'
		' by the dateparser (https://dateparser.readthedocs.io) module is'
		' fine.')
	
	args = parser.parse_args()

	if __name__ == '__main__':
		logger_format = "[%(levelname)7s] %(message)s"
	else:
		logger_format = "[%(levelname)7s] %(name)s: %(message)s"
	
	if args.debug:
		logging.basicConfig(level=logging.DEBUG, format=logger_format)
	else:
		logging.basicConfig(level=logging.INFO, format=logger_format)
	
	global repository
	repository = args.repo

	global freeze_date
	freeze_date = dateparser.parse(args.date).date()
	logger.debug("Using date %s for freeze date", freeze_date.isoformat())

	if args.settings_file:
		global settings_file
		settings_file = args.settings_file

	if args.force:
		global force
		force = True
	
	logger.debug("Got repository '%s' from command line", repository)

def read_settings(settings_file):
	"""
	Read settings for the program using ConfigParser.

	args:
		settings_file: filename to read

	returns:
		Result from configparser of reading the settings
	"""
	cp = configparser.ConfigParser()
	cp.read(settings_file)
	if not cp.sections():
		logger.error("Unable to read any settings from '%s'.", settings_file)
		raise RuntimeError("Unable to read settings.")
	return cp


def get_repos_to_freeze(repo_root):
	"""
	Finds the repos referenced by the schedule, to get a list to freeze.

	args:
		repo_root: string which is the path to a clone of the repo to
			freeze.

	returns:
		list of urls that are linked to from the schedule
	"""
	schedule_path = os.path.join(repo_root, '_includes', 'sc', 'schedule.html')
	logger.debug("Reading schedule from: %s", schedule_path)
	with open(schedule_path) as schedule_file:
		schedule = schedule_file.readlines()
	repos_to_freeze = []
	link_re = re.compile(r'<a\s+(?:[^\s]+\s+)?href="(?P<url>[^"]+)"')
	for line in schedule:
		start = 0
		while start >= 0:
			match = link_re.search(line, start)
			if match:
				# Found a match - store the url found
				url = urllib.parse.urlparse(match.group('url'))
				if url.netloc.endswith('.github.io'):
					new_netloc = 'github.com'
					path_prefix = url.netloc[:-10]
					new_url = url._replace(netloc=new_netloc,
						path=path_prefix + url.path)
					logger.info("Converted github pages url '%s' to repo '%s",
						url.geturl(), new_url.geturl())
					url = new_url

				repos_to_freeze.append(url.geturl())
				# Check the rest of the string for another url
				start = match.end()
			else:
				start = -1 # No match, so exit loop
	logger.debug("get_repos_to_freeze found: %s", repos_to_freeze)
	return repos_to_freeze

def create_github_repo(organisation, repo_name, homepage=None):
	"""
	Create a new blank repo called repo_name within the organisation
	using the github api.

	args:
		organisation: organisation to create in
		repo_name: name to create
		homepage: (optional) homepage for the repo

	returns:
		URL of the new repository
	"""
	if 'github' not in settings:
		logger.error("No github settings found! (Have they been put in %s?)",
			settings_file)
		raise RuntimeError("No github settings found.")

	if settings['github'].get('accesstoken'):
		gh = github.Github(settings['github']['accesstoken'])
	else:
		gh = github.Github(settings['github']['username'],
			settings['github']['password'])

	gh_org = gh.get_organization(organisation)

	create_args = {'name': repo_name}
	if homepage is not None:
		create_args['homepage'] = homepage
	new_repo =  gh_org.create_repo(**create_args)
	return new_repo.url


def freeze(repo_url, freeze_date, force=False):
	"""
	Actually freeze the repository given.

	args:
		repo_url: Repository url to freeze
		force: Force a freeze even if the repo URL looks like it points
			to a frozen repo already.

	returns:
		New repository's url if the repository was frozen by this method.
		False if the repository was already frozen (and 'force' was not
			true, so this method did nothing) or frozen url already
			existed.
	"""

	logger.debug("Freezing repository: %s", repo_url)
	url = urllib.parse.urlparse(repo_url)
	split_path = url.path.split('/')

	# If the url ends with a '/' the last part of the url is at index
	# -2 ([-1] is '').
	if repo_url.endswith('/'):
		last_path_part = -2
	else:
		last_path_part = -1

	# Does the url path already start with something that looks like
	# a YYYY-MM-DD-bham_ format (20..-*.-^.-bham_ where . is any digit,
	# * is 0 or 1 and ^ is 0, 1, 2 or 3)?
	if re.match('20[0-9]{2}-[01][0-9]-[0-3][0-9]-bham_',
		split_path[last_path_part]):
		logger.warning("Repository '%s' looks like it is already frozen",
			repo_url)
		if not force:
			logger.error("Will not freeze this one without a force!")
			return False
		else:
			logger.info("Force specified, freezing anyway.")

	new_path = split_path

	# Should be ['', <organisation name>, <path>(, '')]
	if len(new_path) not in (3, 4):
		new_url = url._replace(path='/'.join(new_path))
		logger.error("New path length mismatch - tried %s" % new_url)
		raise RuntimeError("Path length is wrong!")

	organisation = new_path[1]
	repo_name = '%s-bham_' % freeze_date.isoformat() + new_path[last_path_part]
	repo_homepage = "https://%s.github.io/%s" % (organisation, repo_name)

	# Create the new remote repository
	create_github_repo(organisation, repo_name, repo_homepage)
	logger.info("Created repository which will be published at: %s", repo_homepage)


def do_freeze(repo_url, force=False):
	"""
	Freeze the repository.

	Clones the repository, finds repositories referenced by the schedule
	and creates new snapshot repositories of them in GitHub.  Then
	updates the links in the schedule and commits the new version back.

	args:
	  repo_url: string address to the repository

	returns: Nothing
	"""
	with tempfile.TemporaryDirectory() as tempdir:
		logger.debug("Using temporary directory: %s", tempdir)
		git.Repo.clone_from(repo_url, tempdir)
		logger.info("Fetched repository: %s", repo_url)

		to_freeze = get_repos_to_freeze(tempdir)
		logger.info("Need to freeze: %s", to_freeze)

		frozen = {}
		for repo in to_freeze:
			frozen_url = freeze(repo, freeze_date, force)
			if frozen_url:
				frozen[repo] = frozen_url

		if len(frozen):
			update_repo_urls(tempdir, frozen)
		else:
			logger.warning("No repositories frozen - maybe none found or"
			 " all already frozen?")


if __name__ == '__main__':
	process_commandline()
	settings = read_settings(settings_file)
	do_freeze(repository, force)
