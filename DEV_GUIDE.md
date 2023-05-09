# Developer's guide

Purpose of this guide to make possible develop code for for the small group.

Please make sure to install requirements_dev.txt first.

## IDE

VScode is highly recommended. but some plugin are required to make it works.

[GitLens](https://marketplace.visualstudio.com/items?itemName=eamodio.gitlens)

[Formatter](https://dev.to/adamlombard/how-to-use-the-black-python-code-formatter-in-vscode-3lo0)

```shell
pip install black
```


settings.json has the following:

```json
"python.formatting.blackArgs": [
        "--line-length",
        "88",
        "--preview",
    ],

```


[Linting](https://code.visualstudio.com/docs/python/linting)
We use mypy as a linter.

[Spell checker](https://marketplace.visualstudio.com/items?itemName=streetsidesoftware.code-spell-checker)
[Better brackets](https://marketplace.visualstudio.com/items?itemName=CoenraadS.bracket-pair-colorizer-2)
[Docustring](https://marketplace.visualstudio.com/items?itemName=njpwerner.autodocstring)
[Better comments](https://marketplace.visualstudio.com/items?itemName=aaron-bond.better-comments)
[Color theme](https://marketplace.visualstudio.com/items?itemName=barrsan.reui)

## Git best practices

Pleas install [git-flow](https://www.atlassian.com/git/tutorials/comparing-workflows/gitflow-workflow)

## Testing

Install development requirements

```shell
pip3 install -r requirements_dev.txt
```

We do code testing using pytest. Tests should be in the test directory and follow pytest requirements ('__test.py') in order to be discovered by pytest
You will need to setup your `PYTHONPATH` for running tests

```shell
# run all tests
$ PYTHONPATH=$(pwd):$PYTHONPATH XBENCH_HOME=$(pwd) pytest ./test/
```

## Coding style

[Google style docustring](
https://sphinxcontrib-napoleon.readthedocs.io/en/latest/example_google.html)

Mypy [hints cheat sheet](https://mypy.readthedocs.io/en/stable/cheat_sheet_py3.html)

## Running end-to-end integration test

```shell
./bin/xbench.sh run -c <your clsuter name> -t itest -i itest -b sysbench -w itest -o /tmp -a /tmp
```

## git pre-commit hooks

We don't want to commit ipython notebook outputs into the repo.  Here is a git pre-commit
hook that I use to automatically strip the outputs from ipython notebooks.

```shell
#!/usr/bin/env bash
# requires `nbstripout` to be available on your PATH
# can be installed with `pip`
#set -x

find . -name '*.ipynb' -type f | while read nb; do
        jupyter nbconvert --clear-output --inplace ${nb}
done
```

To install the pre-commit hook, make sure you have installed `nbstripout` with `pip`,
then copy this script to `.git/hooks/pre-commit` and make it executable with
`chmod +x .git/hooks/pre-commit`.  Now when you go to commit, the script will run
automatically for you.
