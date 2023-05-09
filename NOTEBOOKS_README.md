# Running notebooks with Xbench

We use `JupyterLab 3` and `Plotly` - please check `requirements.txt` for desired versions.
But, honestly, Vscode nowadays has the best Jupyter support - so it is highly recommended.

## Installation

From  https://plotly.com/python/getting-started/

```shell
pip install jupyterlab "ipywidgets>=7.5"
pip install plotly==4.14.3
# If you will be asked about nodejs please install it from: https://nodejs.org/en/
jupyter labextension install jupyterlab-plotly@4.14.3
jupyter labextension install @jupyter-widgets/jupyterlab-manager plotlywidget@4.14.3
```

## Generate html

Playing with notebooks surely a fun, but most regular people don't have them installed. Best way to share your work is to generate html version which includes your raw data and interactive graphs:

```shell
jupyter nbconvert notebooks/mynotebook.ipynb --execute --no-input --to html --output mynotebook.html
```

By default your notebook will skip all `code` cells so it looks nice a clean for external audience!
