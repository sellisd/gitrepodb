from setuptools import setup

setup(
    name="gitrepodb",
    version='0.0.1',
    py_modules=['gitrepodb'],
    install_requires=[
      'Click'
    ],
    package_data={'gitrepodb': ['sql_scripts/*.sql']},
    entry_points='''
        [console_scripts]
        gitrepodb=gitrepodb.gitrepodb:gitrepodb
    ''',
)
