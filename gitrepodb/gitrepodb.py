import importlib.resources as pkg_resources
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from sqlite3 import Error
import logging

import click
from dotenv import load_dotenv
from git import Repo, exc
from github import Github
from github.GithubException import BadCredentialsException
from tqdm import tqdm

project_dict = {'python': 'python',
                'jupyter': '"Jupyter Notebook"',
                'java': 'Java'}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@click.group()
def gitrepodb():
    pass


@gitrepodb.command()
@click.option('--name', default='./repositories.db', help='Remove repositories that are not used in any project from the database.')
def clean_database(name):
    """Delete rows in repository table that do not belong to a project."""
    if not database_exists(name):
        return
    connection = sqlite3.connect(name)
    cursor = connection.cursor()
    try:
        logger.info("Cleaning database...")
        delete_query = """
        DELETE
        FROM repositories
        WHERE NOT EXISTS
            (SELECT *
             FROM projects
             WHERE projects.repository_owner = repositories.repository_owner
               AND projects.repository_name = repositories.repository_name)
        """
        cursor.execute(delete_query)
        connection.commit()
        logger.info("Database cleaned successfully.")
    except Error as e:
        logger.error(f"Error cleaning database: {e}")
    finally:
        connection.close()


def database_exists(name):
    "Check if database exists"
    if not Path(name).exists():
        logger.error(f"Database {name} does not exist, check spelling or create by running: gitrepodb init")
        return False
    else:
        logger.info(f"Database {name} exists.")
        return True


@gitrepodb.command()
@click.option('--name', default='./repositories.db', help='Path and file name '
              'of database', show_default=True)
@click.option('--overwrite/--no-overwrite', default=False, help='Overwrite '
              'database file if existing', show_default=True)
def init(name, overwrite):
    conn = None
    if(not overwrite):
        if Path(name).exists():
            print(f"{name} already exists I am not overwriting")
            return
    try:
        connection = sqlite3.connect(name)
        cursor = connection.cursor()
        sql_script = (pkg_resources.files(
            'gitrepodb.sql_scripts').joinpath('init.sql').read_text())
        cursor.executescript(sql_script)
        connection.commit()
        connection.close()
        logger.info(f"Database created in: {name}")
    except Error as e:
        logger.error(e)


@gitrepodb.command()
@click.option('--name', default='./repositories.db', help='Path and file name '
              'of database', show_default=True)
@click.option('--basepath', default='./scratch', help='Path where all '
              'repositories will be stored', show_default=True)
def add(name, basepath):
    """Add query results to database."""
    if not database_exists(name):
        return
    connection = sqlite3.connect(name)
    cursor = connection.cursor()
    query_to_projects_string = """
    REPLACE
    INTO projects
    SELECT
      project,
      repository_owner,
      repository_name
    FROM query_results
    """
    query_to_repositories_string = """
    REPLACE
    INTO repositories
    (
      repository_owner,
      repository_name,
      clone_url
      )
    SELECT repository_owner,
      repository_name,
      clone_url
    FROM query_results
    """
    build_path_string = f"""
    UPDATE repositories
    SET repository_path = '{basepath}{os.sep}' || repository_owner || '{os.sep}' || repository_name
    """
    cursor.execute(query_to_projects_string)
    cursor.execute(query_to_repositories_string)
    cursor.execute(build_path_string)
    connection.commit()
    connection.close()
    logger.info("Added query to database.")


@gitrepodb.command()
@click.option('--name', default='./repositories.db', help='Path and file name '
              'of database', show_default=True)
@click.option('--project', default=None, help='Download to disk repositories '
              ' in project', show_default=True, required=True)
@click.option('--update', default=False, help='If repository is already '
              'cloned, pull to update', show_default=True)
def download(name, project, update):
    if not database_exists(name):
        return
    connection = sqlite3.connect(name)
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()
    select_projects_string = f"""
    SELECT projects.repository_owner,
      projects.repository_name,
      repositories.repository_path,
      clone_url
    FROM projects
      INNER JOIN repositories
      ON projects.repository_owner = repositories.repository_owner
        AND projects.repository_name = repositories.repository_name
        AND projects.project = "{project}"
    """
    cursor.execute(select_projects_string)
    rows = cursor.fetchall()
    for row in rows:
        pull_or_clone(row['clone_url'], row['repository_path'], update)
        # update database
        if update:
            last_pulled = datetime.utcnow().isoformat()
            cursor.execute("""
            UPDATE repositories
            SET last_pulled = ?
            WHERE repository_owner = ? AND repository_name = ?
            """, (last_pulled, row.repository_owner, row.repository_name))


@gitrepodb.command()
@click.option('--project', default='python',
              help='Assign the query to a project', show_default=True,
              required=True)
@click.option('--query', default=None, help='Query using github API. If none'
              ' is provided [defautl] then query using project as language',
              show_default=True)
@click.option('--name', default='./repositories.db', help='Path and file name '
              'of database', show_default=True)
@click.option('--head', default=5000,
              help='Maximum number of repositories in query',
              show_default=True)
def query(project, query, name, head):
    """Query GitHub API and insert results into query_results table"""
    if not database_exists(name):
        return
    if query is None and project:
        if project in project_dict:
            query = f"language:{project_dict[project]},sort:stars-desc:archived=False"
        else:
            logger.error(f"Unknown project {project}")
            return
    load_dotenv()
    try:
        logger.info(f"Querying github with query {query}")
        g = Github(os.getenv('github'))
        repositories = g.search_repositories(query=query)
        logger.info(f"got {repositories.totalCount} repositories, will keep the top {head}")
    except BadCredentialsException as e:
        logger.error(e)
    connection = sqlite3.connect(name)
    cursor = connection.cursor()
    cursor.execute('DELETE FROM query_results')
    logger.info("Adding to database:")
    for count, repo in tqdm(enumerate(repositories)):
        if count >= int(head):
            break
        insert_query_string = """
        REPLACE INTO query_results
          (
            project,
            repository_owner,
            repository_name,
            query_string,
            query_timestamp,
            clone_url
          )
        VALUES
          (?, ?, ?, ?, ?, ?)
        """
        query_timestamp = datetime.utcnow().isoformat()
        cursor.execute(insert_query_string, (project,
                                             repo.owner.login,
                                             repo.name,
                                             query,
                                             query_timestamp,
                                             repo.ssh_url))
    connection.commit()
    connection.close()


@gitrepodb.command()
@click.option('--project', default='python', help='Query for popular project_dict '
              'based on language', show_default=True)
@click.option('--name', default='./repositories.db', help='Path and file name '
              'of database', show_default=True)
def sync(project, name):
    if not database_exists(name):
        return
    "Sync query results to database, add query results and remove existing ones in the same project"
    connection = sqlite3.connect(name)
    cursor = connection.cursor()
    update_repositories_string = """
    REPLACE INTO repositories(repository_owner, repository_name, clone_url)
    SELECT query_results.repository_owner,
           query_results.repository_name,
           query_results.clone_url
    FROM query_results
    INNER JOIN projects ON projects.repository_owner = query_results.repository_owner
    AND projects.repository_name = query_results.repository_name
    AND projects.project=query_results.project
    """
    cursor.execute(update_repositories_string)
    delete_not_in_query_string = """
    DELETE
    FROM projects
    WHERE NOT EXISTS
        (SELECT *
         FROM query_results
         WHERE query_results.project = projects.project
           AND query_results.repository_name = projects.repository_name
           AND query_results.repository_owner = projects.repository_owner)
    """
    cursor.executescript(delete_not_in_query_string)
    connection.commit()
    connection.close()


def clone(url, path):
    try:
        Repo.clone_from(url, path, depth=1)
    except exc.BadCredentialsException:
        logger.error("Bad credenttials")
    except exc.UnknownObjectException:
        logger.error("Non existing repository")


def pull_or_clone(url, path, pull=True):
    try:
        Repo(path).git_dir
        logger.info(f"Repository {url} already exists in {path}")
        if pull:
            logger.info(" pulling...")
            Repo(path).remotes.origin.pull()
        else:
            logger.info(" skipping...")
    except exc.InvalidGitRepositoryError:
        logger.info(f"{path} is not a git repository, will clone {path} in it")
        clone(url, path)
    except exc.NoSuchPathError:
        logger.info(f"Clonning {url} into {path}")
        Path(path).mkdir(parents=True)
        Repo.clone_from(url, path, depth=1)
