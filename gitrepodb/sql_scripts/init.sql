CREATE TABLE IF NOT EXISTS projects
(
  project TEXT,
  repository_owner TEXT,
  repository_name TEXT,
  PRIMARY KEY(project, repository_owner, repository_name)
);

CREATE TABLE IF NOT EXISTS repositories(
  repository_owner TEXT,
  repository_name TEXT,
  last_pulled TEXT,
  cleaned INTEGER,
  clone_url TEXT,
  repository_path TEXT,
  PRIMARY KEY(repository_owner, repository_name),
  FOREIGN KEY(repository_owner, repository_name)
  REFERENCES projects(repository_owner, repository_name)
);

CREATE TABLE IF NOT EXISTS query_results
(
  project TEXT,
  repository_owner TEXT,
  repository_name TEXT,
  query_string TEXT,
  query_timestamp TEXT,
  clone_url TEXT,
  PRIMARY KEY(project, repository_owner, repository_name),
  FOREIGN KEY(repository_owner, repository_name)
  REFERENCES repositories(repository_owner, repository_name)
);
