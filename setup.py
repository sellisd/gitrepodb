from setuptools import setup

setup(
    name="gitrepodb",
    version='0.0.1',
    py_modules=['gitrepodb'],
    python_requires='>=3.9',  # use importlib.resources
    install_requires=[
      'click',
      'python-dotenv',
      'PyGithub',
      'GitPython',
      'tqdm'
    ],
    package_data={'gitrepodb': ['sql_scripts/*.sql']},
    packages=['gitrepodb'],
    entry_points={
        'console_scripts':
        [
          'gitrepodb=gitrepodb.gitrepodb:gitrepodb'
        ]
    },
)
