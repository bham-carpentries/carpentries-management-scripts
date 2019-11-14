#!/usr/bin/env python

# Core modules
import argparse
import logging
import os.path
import re
import sys
import tempfile
import urllib.parse
import warnings

# 3rd part imports
import dateparser
import git
import github

# Local imports
import util

logger = logging.getLogger(__name__)
tempdirs = []
repository = None
force = None
carry_on = False
freeze_date = None
settings_file = 'settings.ini'
settings = None
dry_run = False

def process_commandline(args_list=None):
    """
    Processes command line arguments.

    args:
        args_list: Override using the real command line arguments with
                   this list.  Intended for testing.
    """
    parser = argparse.ArgumentParser(
        description= \
        'Freeze the version of a Birmingham Carpentries course for posterity.'
    )
    parser.add_argument(
        '-d', '--debug',
        dest='debug',
        action='store_true',
        help='turn on debug mode (produces more detailed output).  Implicitly'
             ' turns on --dry-run.'
    )
    parser.add_argument(
        '-s', '--settings',
        dest='settings_file',
        action='store',
        help='Specify the settings file - defaults to "settings.ini" in the'
            ' current working directory.  See settings.ini.example for an'
            ' example.'
    )
    parser.add_argument(
        '--force',
        dest='force',
        action='store_true',
        help='force freeze even if repos already looks frozen (based on url)'
    )
    parser.add_argument(
        '--continue',
        dest='carry_on',
        action='store_true',
        help='Carry on regardless if the frozen repository already exists'
            ' (will not update existing repositories - just assumes they are'
            ' already faithful snapshots)'
    )
    parser.add_argument(
        '--dry-run',
        dest='dry_run',
        action='store_true',
        help='Logs (at info level) what would be done but does not actually'
             ' make any changes.'
    )
    parser.add_argument(
        '--no-dry-run',
        dest='no_dry_run',
        action='store_true',
        help='Forcibly turn off dry-run mode (only useful with -d/--debug).'
    )
    parser.add_argument(
        'repo',
        action='store',
        help='Repository to freeze (i.e. the repository with the schedule'
            ' whose repos you want to freeze).  Can be the repository'
            ' (github.com/.../...) or Git Pages (...\\.github.io/...).'
    )
    parser.add_argument(
        'date',
        action='store',
        help='Date to use in the prefix of the new (frozen) repositories.  Any'
            ' date parseable by the dateparser'
            ' (https://dateparser.readthedocs.io) module is fine.'
    )
    
    logger.debug("Parsing args list (will use sys.argv if None): %s", args_list)
    args = parser.parse_args(args_list)

    global dry_run
    
    if args.debug:
        my_logging_level=logging.DEBUG    
    else:
        my_logging_level=logging.INFO

    if not logger.hasHandlers():
        if __name__ == '__main__':
            logger_format = "[%(levelname)7s] %(message)s"
        else:
            logger_format = "[%(levelname)7s] %(name)s: %(message)s"

        logging.basicConfig(level=my_logging_level, format=logger_format)

    logger.setLevel(my_logging_level)
    if args.debug:
        if args.no_dry_run:
            logger.warning(
                "I seem to be in debug mode but dry-run has been explicitly"
                " disabled.  Not implicitly turning it on."
            )
        else:
            dry_run = True
            logger.debug("Debug enabled - implicitly turned on dry-run mode.")
    
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
    
    if args.carry_on:
        global carry_on
        carry_on = True

    if args.dry_run and args.no_dry_run:
        logger.critical(
            "Cannot specify --dry-run and --no-dry-run (does not make sense!)"
        )
        sys.exit(1)
    elif args.dry_run:
        dry_run = True
        logger.info("Turned on dry-run mode.")

    logger.debug("Got repository '%s' from command line", repository)

def _get_schedule_file_relative_path():
    """
    Returns the relative path of the schedule file to the git repo root.

    Used by _get_schedule_file_path and update_repo_urls so we only have
    to fix it in one place if   it changes.
    """
    return os.path.join('_includes', 'swc', 'schedule.html')
 
def _get_index_file_relative_path():
    """
    Returns the relative path of the index file to the git repo root.

    Used by _get_index_file_path and update_repo_urls so we only have
    to fix it in one place if   it changes.
    """
    return 'index.md'

def  __get_schedule_file_path(repo_root):
    """
    Returns the path of the schedule file - used by _get_schedule_file,
    _write_schedule_file and update_repo_urls so we only have to fix it
    in one place if it changes.
    """
    return os.path.join(repo_root, _get_schedule_file_relative_path())


def  __get_index_file_path(repo_root):
    """
    Returns the path of the schedule file - used by _get_index_file,
    _write_index_file and update_repo_urls so we only have to fix it
    in one place if it changes.
    """
    return os.path.join(repo_root, _get_index_file_relative_path())

def _get_schedule_file(repo_root):
    """
    Read the content of the schedule file.

    args:
        repo_root: Root of the cloned repository with the file in.

    returns:
        contents of the file as a list of lines (via .readlines())
    """
    schedule_path = __get_schedule_file_path(repo_root)
    logger.debug("Reading schedule from: %s", schedule_path)
    with open(schedule_path) as schedule_file:
        schedule = schedule_file.readlines()
    return schedule

def _get_index_file(repo_root):
    """
    Read the content of the index file.

    args:
        repo_root: Root of the cloned repository with the file in.

    returns:
        contents of the file as a list of lines (via .readlines())
    """
    index_path = __get_index_file_path(repo_root)
    logger.debug("Reading index from: %s", index_path)
    with open(index_path) as index_file:
        index = index_file.readlines()
    return index

def _write_schedule_file(repo_root, lines):
    """
    Write new contents to the schedule file.

    args:
        repo_root: Root of the cloned repository with the file in.
        lines: list of lines to write (mirroring return value of
            _get_schedule_file)

    returns:
        Nothing
    """
    schedule_path = __get_schedule_file_path(repo_root)
    logger.debug("Writing new schedule to: %s", schedule_path)

    with open(schedule_path, 'w') as schedule_file:
        schedule_file.writelines(lines)

def _write_index_file(repo_root, lines):
    """
    Write new contents to the index file.

    args:
        repo_root: Root of the cloned repository with the file in.
        lines: list of lines to write (mirroring return value of
            _get_index_file)

    returns:
        Nothing
    """
    index_path = __get_index_file_path(repo_root)
    logger.debug("Writing new index to: %s", index_path)

    with open(index_path, 'w') as index_file:
        index_file.writelines(lines)

def _github_io_to_github_com(url):
    """
    Converts <org>.github.io/<repo> to github.com/<org>/<repo>

    args:
        url: urllib object of the parsed source url

    returns:
        New urllib object for the new url
    """
    assert url.netloc.endswith('.github.io'), \
        "_github_io_to_github_com called with non-github.io url: %s" % \
        url.geturl()

    new_netloc = 'github.com'
    path_prefix = url.netloc[:-10]
    new_url = url._replace(
        netloc=new_netloc,
        path=''.join(['/', path_prefix, url.path])
    )
    logger.info(
        "Converted github pages url '%s' to repo '%s'",
        url.geturl(), new_url.geturl()
    )
    return new_url

def get_repos_to_freeze(repo_root):
    """
    Finds the repos referenced by the schedule, to get a list to freeze.

    args:
        repo_root: string which is the path to a clone of the repo to
            freeze.

    returns:
        list of urls that are linked to from the schedule
    """
    schedule = _get_schedule_file(repo_root)
    repos_to_freeze = []
    link_re = re.compile(r'<a\s+(?:[^\s]+\s+)?href="(?P<url>[^"]+)"')
    for line in schedule:
        start = 0
        while start >= 0:
            match = link_re.search(line, start)
            if match:
                # Found a match - store the url found
                url = urllib.parse.urlparse(match.group('url').strip())
                if url.netloc.endswith('.github.io'):
                    url = _github_io_to_github_com(url)

                repos_to_freeze.append( (match.group('url'), url.geturl()) )
                # Check the rest of the string for another url
                start = match.end()
            else:
                start = -1 # No match, so exit loop
    logger.debug("get_repos_to_freeze found: %s", repos_to_freeze)
    return repos_to_freeze

def _get_organisation_repo_from_url(repo_url):
    """
    Attempts to guess organisation and repository from Github url

    We need this information to use the github API.

    args:
        repo_url: url to examine

    returns:
        tuple of (organisation, repository)
    """
    url = urllib.parse.urlparse(repo_url)

    if url.netloc.endswith('.github.io'):
        url = _github_io_to_github_com(url)

    logger.debug("Url path is '%s'", url.path)
    split_path = url.path.split('/')

    # If the url ends with a '/' the last part of the url is at index
    # -2 ([-1] is '').
    if split_path[-1] == '':
        last_path_part = -2
    else:
        last_path_part = -1

    # Should be ['', <organisation name>, <repo>(, '')]
    if len(split_path) not in (3, 4):
        logger.error("Path length mismatch in url: %s", url.geturl())
        raise RuntimeError("Path length is wrong!")

    organisation = split_path[1]
    repo_name = split_path[last_path_part]
    return (organisation, repo_name)

def _get_github_instance():
    """
    Initialise a new github.Github object from the settings file.

    args:
        None

    returns:
        New Github object
    """
    return github.Github(settings['github']['accesstoken'])


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
    gh = _get_github_instance()

    gh_org = gh.get_organization(organisation)

    create_args = {'name': repo_name}
    if homepage is not None:
        create_args['homepage'] = homepage
    new_repo =  gh_org.create_repo(**create_args)
    return new_repo.clone_url

def set_github_default_branch(organisation, repo_name, branch='master'):
    """
    Sets the default branch on a github repo.

    args:
        organisation: organisation to update in
        repo_name: name of repo to update
        branch: branch to set as default ('master' if not specified)

    returns:
        Nothing
    """
    _get_github_instance().get_organization(organisation).get_repo(repo_name)\
        .edit(default_branch=branch)

def get_github_homepage(organisation, repo_name):
    """
    Gets the homepage for a repository.

    args:
        organisation: organisation to create in
        repo_name: name to create

    returns:
        homepage of the repository

    """
    return _get_github_instance().get_organization(organisation)\
        .get_repo(repo_name).homepage

def import_to(source, dest):
    """
    Import repository from source to dest.

    Works very similarly to the github import tool - clones the source,
    updates the remote and pushes to the new remote.

    Based on GitHubs guide on mirroring a repository:
        https://help.github.com/articles/duplicating-a-repository/

    args:
        source: source repository url
        dest: destination repository url
    """
    with tempfile.TemporaryDirectory() as tempdir:
        logger.debug("Using temporary directory: %s", tempdir)
        repo = git.Repo.clone_from(source, tempdir, bare=True)
        logger.info("Fetched repository: %s", source)
        repo.delete_remote('origin')
        repo.create_remote('origin', dest)
        repo.remote('origin').push(mirror=True)
        logger.info("Pushed to new reposotory: %s", dest)


def update_frozen_repository(repo_url, course_repository):
    """
    Adds a note and back-reference to the frozen copy of a repository.

    args:
        repo_url: Url of the frozen repo
        course_repository: Url of the course repository (the backlink
            will be determined from this repositories Github homepage)

    returns:
        Nothing
    """

    # Find the organisation and repository for the course homepage
    (organisation, repository) = _get_organisation_repo_from_url(
        course_repository
    )
    logger.debug(
        "Finding homepage for repo %s in %s",
        repository,
        organisation
    )
    # Get the homepage (for the link back)
    backlink = get_github_homepage(organisation, repository)
    # Infer the course date from the repository start, if it looks like
    # a date (the first 10 characters are all 0-9 or '-'s)
    if re.match('[0-9-]{10}', repository):
        course_date = dateparser.parse(repository[:10]).date()
    else:
        course_date = None
    logger.debug("Schedule back-link will be to: %s", backlink)
    with tempfile.TemporaryDirectory() as tempdir:
        logger.debug("Using temporary directory: %s", tempdir)
        if '@' not in repo_url:
            repo_url = repo_url.replace(
                '://',
                '://%(user)s@' % {
                    'user': settings['github']['accesstoken'],
                }
            )

        if dry_run:
            old_repo_url = re.sub(r'[0-9-]{10}-bham_', '', repo_url)
            logger.info(
                "DRY-RUN - Would clone repo from %s but using %s instead",
                repo_url, old_repo_url
            )
            repo = git.Repo.clone_from(old_repo_url, tempdir)
            # To be on the safe-side, don't want any code accidentally
            # pushing to our live courses.
            repo.delete_remote(repo.remote('origin'))
        else:
            repo = git.Repo.clone_from(repo_url, tempdir)
        
        # Read the old index
        with open(os.path.join(tempdir, 'index.md')) as f:
            old_index = f.readlines()

        # Modify it - the file starts with some meta data seperated by
        # a line above and below beginning with dashes.  Find the last
        # dashes and insert the message.
        new_index = []
        dash_count = 0
        for line in old_index:
            if line.startswith('--'):
                dash_count += 1
                if dash_count == 2:
                    # Make sure to include the original line of dashes first
                    new_index.append(line)
                    # 2nd line beginning with dashes
                    message = [
                        "This is the version taught at the"
                        " [Software carpentries](%s) workshop" % backlink
                    ]
                    if course_date is not None:
                        message.append(
                            " beginning on %s" % course_date.strftime(
                                "%A %d %B %Y"
                            )
                        )
                    message.append('.\n')
                    new_index.append(''.join(message))
                    # Don't re-add this line by falling through -
                    # force next loop
                    continue
            new_index.append(line)

        # Write the new file
        with open(os.path.join(tempdir, 'index.md'), 'w') as f:
            f.writelines(new_index)
        
        ri = repo.index
        ri.add(['index.md'])
        ri.commit("""Updated index with back link to course schedule.

Automatic commit from freeze script.
""")
        if dry_run:
            logger.info(
                "DRY-RUN - Would push updated repository from '%s' to origin",
                tempdir
            )
        else:
            # This is why we make sure to have 'user@' in the remote url when
            # this was cloned at the start of do_freeze.
            repo.remote('origin').push()


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
    (organisation, repo_name) = _get_organisation_repo_from_url(repo_url)
    # Does the url path already start with something that looks like
    # a YYYY-MM-DD-bham_ format (20..-*.-^.-bham_ where . is any digit,
    # * is 0 or 1 and ^ is 0, 1, 2 or 3)?
    if re.match('20[0-9]{2}-[01][0-9]-[0-3][0-9]-bham_',
        repo_name):
        logger.warning(
            "Repository '%s' looks like it is already frozen",
            repo_url
        )
        if not force:
            logger.error("Will not freeze this one without a force!")
            return False
        else:
            logger.info("Force specified, freezing anyway.")

    repo_name = '%s-bham_' % freeze_date.isoformat() + repo_name
    repo_homepage = "https://%s.github.io/%s" % (organisation, repo_name)

    if dry_run:
        logger.info(
            "DRY-RUN - Would have created a a new repository, %s, in"
            " organisation, %s, with homepage: %s", repo_name, organisation,
            repo_homepage
        )
        # Set a (semi-)dummy value for the next step
        new_repo_url = "https://github.com/%s/%s.git" % (
            organisation,
            repo_name
        )
    else:
        # Create the new remote repository
        new_repo_url = create_github_repo(
            organisation, repo_name, repo_homepage
        )
        logger.info(
            "Created repository which will be published at: %s",
            repo_homepage
        )

    # This is why we need an access token rather than username/password
    new_repo_url = new_repo_url.replace(
        '://',
        '://%(user)s@' % {
            'user': settings['github']['accesstoken'],
        }
    )

    if dry_run:
        logger.info(
            "DRY-RUN - Would have imported old repo, %s, to new repo, %s",
            repo_url,
            new_repo_url
        )
    else:
        import_to(repo_url, new_repo_url)
        set_github_default_branch(organisation, repo_name, 'gh-pages')
        logger.debug("Set default branch to gh-pages on new repo.")

    logger.info("Imported repository.")

    update_frozen_repository(new_repo_url, repository)
    return repo_homepage

def update_repo_links(gitdirectory, frozen_urls):
    """
    Updates the urls in the clone of the carpentries homepage.

    Changes the urls then commits the new version automatically.

    args:
        gitdirectory: location of the local clone of the repository to
            update
        frozen_urls: dict mapping the old url (key) to new url (value)

    returns:
        Nothing
    """
    repo = git.Repo(gitdirectory)
    old_schedule = _get_schedule_file(gitdirectory)
    new_schedule = []
    for line in old_schedule:
        new_line = line
        for (old_url, new_url) in frozen_urls.items():
            new_line = new_line.replace(old_url, new_url)
        new_schedule.append(new_line)
    _write_schedule_file(gitdirectory, new_schedule)
    index = _get_index_file(gitdirectory)
    # Github has recently (around July 2019) stopped updating git.io on
    # any file update, it only refreshes now if the index.md gets
    # changed (the schedule, which is included, is not longer
    # sufficient)
    #
    # This block of code basically removes a blank line, if the last 2
    # lines in the index file are blank, or adds a new blank line in any
    # other case.
    if index[-2:] == ['', '']:
        del index[-1]
    else:
        index.append('')
    _write_index_file(gitdirectory, index)
    ri = repo.index
    schedule_file_location = _get_schedule_file_relative_path()
    index_file_location = _get_index_file_relative_path()
    logger.debug(
        "Adding modified %s and %s ready to commit",
        schedule_file_location, index_file_location
    )
    ri.add([schedule_file_location, index_file_location])
    ri.commit("""Updated schedule with frozen urls.

Automatic commit from freeze script.
""")

    if dry_run:
        logger.info(
            "DRY-RUN - Would push updated repository from '%s' to origin",
            gitdirectory
        )
    else:
        # This is why we make sure to have 'user@' in the remote url when
        # this was cloned at the start of do_freeze.
        repo.remote('origin').push()

def do_freeze(repo_url, force=False):
    """
    Freeze the repository.

    Clones the repository, finds repositories referenced by the schedule
    and creates new snapshot repositories of them in GitHub.  Then
    updates the links in the schedule and commits the new version back.

    args:
      repo_url: string address to the repository
      force: Passed through to freeze()

    returns: Nothing
    """
    with tempfile.TemporaryDirectory() as tempdir:
        logger.debug("Using temporary directory: %s", tempdir)

        if 'github.io' in repo_url.lower():
            url = urllib.parse.urlparse(repo_url)
            new_url = _github_io_to_github_com(url)
            repo_url = new_url.geturl()
            logger.info("Converted github.io url to %s", repo_url)

        # Make life easy when we try to push the changes at the end.
        if 'github' in repo_url.lower() and '@' not in repo_url:
            repo_url = repo_url.replace(
                '://',
                '://%(user)s@' % {
                    'user': settings['github']['accesstoken'],
                }
            )
        git.Repo.clone_from(repo_url, tempdir)
        logger.info("Fetched repository: %s", repo_url)

        to_freeze = get_repos_to_freeze(tempdir)
        logger.info("Need to freeze: %s", to_freeze)

        # if _test:
        #     # Abort
        #     warnings.warn("***TEST SET TO TRUE - ABORTING***", RuntimeWarning)
        #     logger.info("do_freeze is aborting after clone and get_repos_to_freeze")
        #     return

        frozen = {}
        for (homepage, repo) in to_freeze:
            if homepage in frozen:
                # Some repos are specified twice - e.g. the R and Python
                # inputs are on the schedule twice, once each day.
                # Trying to re-freeze the same repository will fail (and
                # makes no sense).
                continue # Skip to next repo.
            frozen_url = freeze(repo, freeze_date, force)
            if frozen_url:
                frozen[homepage] = frozen_url

        if len(frozen):
            update_repo_links(tempdir, frozen)
        else:
            logger.warning(
                "No repositories frozen - maybe none found or all already"
                " frozen?"
             )

if __name__ == '__main__':
    process_commandline()
    settings = util.read_settings(settings_file)
    # Check for mandatory settings
    # Lots of this code relies on there being an access token
    if 'github' not in settings:
        logger.error(
            "No GitHub settings found! (Have they been put in %s?)",
            settings_file
        )
        raise RuntimeError("No GitHub settings found.")
    elif 'accesstoken' not in settings['github']:
        logger.error(
            "No access token found for GitHub! (Have they been put in %s?)",
            settings_file
        )
        raise RuntimeError("No GitHub access token")
    do_freeze(repository, force)
