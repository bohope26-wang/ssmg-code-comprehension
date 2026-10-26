# RQ1 Function Sources

The RQ1 dataset contains 30 Python functions from three source categories. The function IDs correspond to the file names `e1.py` through `e30.py`.

| Function IDs | Files | Source | Number of Functions |
|---|---|---|---|
| 1–10 | `e1.py`–`e10.py` | Public open-source repositories | 10 |
| 11–20 | `e11.py`–`e20.py` | Projects developed by one of the authors | 10 |
| 21–30 | `e21.py`–`e30.py` | Generated using GPT-5.5 | 10 |

## Functions 1–10: Public Open-Source Repositories

The following table lists the upstream projects and source-code locations for functions 1–10.

| File | Function Name | Source Project | Corresponding Source Code |
|---|---|---|---|
| `e1.py` | `Model._check_long_column_names` | [Django](https://github.com/django/django) | [django/db/models/base.py (lines 2410–2487)](https://github.com/django/django/blob/0e128d524d0a7c55a955570d6e5da983ac6ce6c7/django/db/models/base.py#L2410-L2487) |
| `e2.py` | `Connection.get_uri` | [Apache Airflow](https://github.com/apache/airflow) | [airflow-core/src/airflow/models/connection.py (lines 313–390)](https://github.com/apache/airflow/blob/602e150aace0ed5d4e22cd4df0cf49949bcd669d/airflow-core/src/airflow/models/connection.py#L313-L390) |
| `e3.py` | `PreparedRequest.prepare_body` | [Requests](https://github.com/psf/requests) | [src/requests/models.py (lines 576–652)](https://github.com/psf/requests/blob/611c6162cbc4ac2020a2f91c7cfa4f3abf9bbb60/src/requests/models.py#L576-L652) |
| `e4.py` | `Model._check_ordering` | [Django](https://github.com/django/django) | [django/db/models/base.py (lines 2301–2407)](https://github.com/django/django/blob/0e128d524d0a7c55a955570d6e5da983ac6ce6c7/django/db/models/base.py#L2301-L2407) |
| `e5.py` | `check_array` | [scikit-learn](https://github.com/scikit-learn/scikit-learn) | [sklearn/utils/validation.py (lines 729–1155)](https://github.com/scikit-learn/scikit-learn/blob/59106029d483678e79825f753bde67f8ade4332b/sklearn/utils/validation.py#L729-L1155) |
| `e6.py` | `PreparedRequest.prepare_url` | [Requests](https://github.com/psf/requests) | [src/requests/models.py (lines 483–563)](https://github.com/psf/requests/blob/611c6162cbc4ac2020a2f91c7cfa4f3abf9bbb60/src/requests/models.py#L483-L563) |
| `e7.py` | `_is_valid_dist_file` | [PyPI Warehouse](https://github.com/pypi/warehouse) | [warehouse/forklift/legacy.py (lines 169–362)](https://github.com/pypi/warehouse/blob/6af84343220fe213f312056ef4b18e9dc4350ed3/warehouse/forklift/legacy.py#L169-L362) |
| `e8.py` | `Model._check_local_fields` | [Django](https://github.com/django/django) | [django/db/models/base.py (lines 2222–2298)](https://github.com/django/django/blob/0e128d524d0a7c55a955570d6e5da983ac6ce6c7/django/db/models/base.py#L2222-L2298) |
| `e9.py` | `SessionRedirectMixin.resolve_redirects` | [Requests](https://github.com/psf/requests) | [src/requests/sessions.py (lines 186–307)](https://github.com/psf/requests/blob/611c6162cbc4ac2020a2f91c7cfa4f3abf9bbb60/src/requests/sessions.py#L186-L307) |
| `e10.py` | `_check_psd_eigenvalues` | [scikit-learn](https://github.com/scikit-learn/scikit-learn) | [sklearn/utils/validation.py (lines 1914–2084)](https://github.com/scikit-learn/scikit-learn/blob/59106029d483678e79825f753bde67f8ade4332b/sklearn/utils/validation.py#L1914-L2084) |

## Functions 11–20: Author-Developed Projects

Functions 11–20 (`e11.py`–`e20.py`) were drawn from projects developed by one of the authors. These functions form the author-developed portion of the RQ1 dataset.

## Functions 21–30: GPT-5.5-Generated Functions

Functions 21–30 (`e21.py`–`e30.py`) were generated using GPT-5.5. These functions form the AI-generated portion of the RQ1 dataset.
