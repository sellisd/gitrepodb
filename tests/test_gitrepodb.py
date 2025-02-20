import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner
from git import exc

from gitrepodb.gitrepodb import (
    add,
    clean_database,
    database_exists,
    init,
    pull_or_clone,
)


@pytest.fixture
def temp_db(tmp_path):
    """Fixture to create a temporary database path."""
    db_path = tmp_path / "test.db"
    return str(db_path)


def test_database_exists(temp_db):
    """Test database existence check functionality."""
    # Test with non-existent database
    assert not database_exists(temp_db)

    # Create an empty file
    Path(temp_db).touch()
    assert database_exists(temp_db)


def test_database_initialization(temp_db):
    """Test database initialization."""
    from click.testing import CliRunner

    runner = CliRunner()

    # Test initial creation
    result = runner.invoke(init, ["--name", temp_db])
    assert result.exit_code == 0
    assert Path(temp_db).exists()

    # Verify tables are created
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()

    # Check if tables exist
    tables_query = """
    SELECT name FROM sqlite_master 
    WHERE type='table' AND name IN ('projects', 'repositories', 'query_results')
    """
    cursor.execute(tables_query)
    tables = cursor.fetchall()
    assert len(tables) == 3

    # Test overwrite protection
    result = runner.invoke(init, ["--name", temp_db])
    assert result.exit_code == 0  # Should exit gracefully

    conn.close()


def test_clean_database(temp_db):
    """Test database cleaning functionality."""
    # Initialize database
    runner = CliRunner()
    result = runner.invoke(init, ["--name", temp_db, "--overwrite"])
    assert result.exit_code == 0
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()

    # Insert test data
    cursor.execute("""
    INSERT INTO repositories (repository_owner, repository_name, clone_url)
    VALUES ('owner1', 'repo1', 'url1')
    """)

    cursor.execute("""
    INSERT INTO repositories (repository_owner, repository_name, clone_url)
    VALUES ('owner2', 'repo2', 'url2')
    """)

    cursor.execute("""
    INSERT INTO projects (project, repository_owner, repository_name)
    VALUES ('test_project', 'owner1', 'repo1')
    """)

    conn.commit()

    # Run clean_database using Click runner
    result = runner.invoke(clean_database, ["--name", temp_db])
    assert result.exit_code == 0

    # Verify results
    cursor.execute("SELECT * FROM repositories")
    remaining_repos = cursor.fetchall()
    assert len(remaining_repos) == 1  # Only the repo in projects should remain

    cursor.execute("""
    SELECT repository_name FROM repositories 
    WHERE repository_owner='owner1' AND repository_name='repo1'
    """)
    assert cursor.fetchone() is not None  # repo1 should still exist

    conn.close()


def test_pull_or_clone(temp_db):
    """Test git pull or clone operations with mocking."""
    test_url = "git@github.com:test/repo.git"
    test_path = "/test/path"

    # Mock Repo class and its behavior
    with patch("gitrepodb.gitrepodb.Repo") as mock_repo:
        # Test case 1: Repository exists and needs pull
        mock_repo.return_value.git_dir = "/some/path"
        mock_repo.return_value.remotes.origin.pull = MagicMock()

        pull_or_clone(test_url, test_path, pull=True)
        mock_repo.return_value.remotes.origin.pull.assert_called_once()

        # Reset mock for next test
        mock_repo.reset_mock()

        # Test case 2: Repository doesn't exist and needs clone
        mock_repo.side_effect = exc.NoSuchPathError()
        with patch("gitrepodb.gitrepodb.Path") as mock_path:
            mock_path.return_value.mkdir = MagicMock()
            with patch("gitrepodb.gitrepodb.Repo.clone_from") as mock_clone:
                pull_or_clone(test_url, test_path)
                mock_clone.assert_called_once_with(test_url, test_path, depth=1)


def test_add_repositories(temp_db):
    """Test adding repositories to the database."""
    # Initialize database
    runner = CliRunner()
    result = runner.invoke(init, ["--name", temp_db, "--overwrite"])
    assert result.exit_code == 0
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()

    # Insert test query results
    cursor.execute("""
    INSERT INTO query_results 
    (project, repository_owner, repository_name, clone_url)
    VALUES 
    ('test_project', 'owner1', 'repo1', 'url1')
    """)
    conn.commit()

    # Test add functionality using Click runner
    result = runner.invoke(add, ["--name", temp_db, "--basepath", "./test_path"])
    assert result.exit_code == 0

    # Verify repositories were added
    cursor.execute("""
    SELECT * FROM repositories 
    WHERE repository_owner='owner1' AND repository_name='repo1'
    """)
    repo = cursor.fetchone()
    assert repo is not None

    # Verify projects were added
    cursor.execute("""
    SELECT * FROM projects 
    WHERE repository_owner='owner1' AND repository_name='repo1'
    """)
    project = cursor.fetchone()
    assert project is not None

    conn.close()
