import importlib.resources as pkg_resources
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from sqlite3 import Error

import click
from dotenv import load_dotenv
from git import Repo, exc
from github import Github
from github.GithubException import BadCredentialsException
from tqdm import tqdm

project_dict = {'python': 'python',
                'jupyter': 'Jupyter Notebook',
                'java': 'Java'}


@click.group()
def gitrepodb():
    pass


@gitrepodb.command()
@click.option('--name', default='./repositories.db', help='Remove repositories that are not used in any project from the database.')
def clean_database(name):
    # delete rows in repository table that do not belong to a project
    connection = sqlite3.connect(name)
    cursor = connection.cursor()
    """
    DELETE
    FROM repositories
    WHERE NOT EXISTS
        (SELECT *
         FROM projects
         WHERE projects.repository_owner = repositories.repository_owner
           AND projects.repository_name = repositories.repository_name)
    """
    connection.commit()
    connection.close()


@gitrepodb.command()
@click.option('--name', default='./repositories.db', help='Path and file name '
              'of database')
def init(name):
    conn = None
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
        print(f"Database created in: {name}")
    except Error as e:
        print(e)


@gitrepodb.command()
@click.option('--project', default='python', help='Query for popular project_dict '
              'based on language', show_default=True)
@click.option('--name', default='./repositories.db', help='Path and file name '
              'of database', show_default=True)
@click.option('--basepath', default='/mnt/Data/scratch', help='Base path where all repositories will be stored')
def add(project, name, basepath):
    """Add query results to database."""
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
    print("Added query to database.")


@gitrepodb.command()
@click.option('--name', default='./repositories.db', help='Clone or pull repositories from database')
@click.option('--project', default=None, help='Clone or pull repositories in specific project')
@click.option('--update', default=False, help='If repository exists already on disk git pull to update')
def download(name, project, update):
    connection = sqlite3.connect(name)
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()
    select_projects_string = """
    SELECT projects.repository_owner,
      projects.repository_name,
      repositories.repository_path,
      clone_url
    FROM projects
      LEFT JOIN repositories
      ON projects.repository_owner = repositories.repository_owner
        AND projects.repository_name = repositories.repository_name
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
@click.option('--project', default='python', help='Assign the query to a project', show_default=True, required=True)
@click.option('--query', default=None, help='Query using github API if none is provided [defautl] then query using project as language', show_default=True)
@click.option('--name', default='./repositories.db', help='Path and file name '
              'of database', show_default=True)
@click.option('--head', default=10, help='Maximum number of repositories in query')
@click.option('--basepath', default='/mnt/Data/scratch', help='Base path where all repositories will be stored')
def query(project, query, name, head, basepath):
    if query is None and project:
        if project in project_dict:
            query = f"language:{project_dict[project]},sort:stars-desc:archived=False"
        else:
            print(f"Unknown project {project}")
            return
    load_dotenv()
    try:
        print("Querying github...", end="")
        g = Github(os.getenv('github'))
        repositories = g.search_repositories(query=query)
        print(f"got {repositories.totalCount} repositories.")
    except BadCredentialsException as e:
        print(e)
    connection = sqlite3.connect(name)
    cursor = connection.cursor()
    cursor.execute('DELETE FROM query_results')
    for count, repo in enumerate(repositories):
        if count > int(head):
            break
        repository_path = Path(basepath, repo.owner.login, repo.name)
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
                                             repo.clone_url))
    connection.commit()
    connection.close()


@gitrepodb.command()
@click.option('--project', default='python', help='Query for popular project_dict '
              'based on language', show_default=True)
@click.option('--name', default='./repositories.db', help='Path and file name '
              'of database', show_default=True)
def sync(project, name):
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
        Repo.clone_from(url, path)
    except exc.BadCredentialsException:
        print("Bad credenttials")
    except exc.UnknownObjectException:
        print("Non existing repository")


def pull_or_clone(url, path, pull=True):
    try:
        Repo(path).git_dir
        print(f"Repository {url} already exists in {path}", end='')
        if pull:
            print(" pulling...")
            Repo(path).remotes.origin.pull()
        else:
            print(" skipping...")
    except exc.InvalidGitRepositoryError:
        print(f"{path} is not a git repository, will clone {path} in it")
        clone(url, path)
    except exc.NoSuchPathError:
        print(f"Clonning {url} into {path}")
        Path(path).mkdir(parents=True)
        Repo.clone_from(url, path)
