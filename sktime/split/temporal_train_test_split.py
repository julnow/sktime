#!/usr/bin/env python3 -u
# copyright: sktime developers, BSD-3-Clause License (see LICENSE file)
"""Implement cutoff dataset splitting for model evaluation and selection."""

__all__ = ["temporal_train_test_split"]

from typing import Optional

import pandas as pd

from sktime.split.base import BaseSplitter
from sktime.split.base._config import (
    ACCEPTED_Y_TYPES,
    FORECASTING_HORIZON_TYPES,
    SPLIT_TYPE,
    _split_by_fh,
)


def temporal_train_test_split(
    y: ACCEPTED_Y_TYPES,
    X: Optional[pd.DataFrame] = None,
    test_size: Optional[float] = None,
    train_size: Optional[float] = None,
    fh: Optional[FORECASTING_HORIZON_TYPES] = None,
) -> SPLIT_TYPE:
    """Split arrays or matrices into sequential train and test subsets.

    Creates train/test splits over endogenous arrays an optional exogenous
    arrays.

    This is a wrapper of scikit-learn's ``train_test_split`` that
    does not shuffle the data.

    Parameters
    ----------
    y : time series in sktime compatible data container format
    X : time series in sktime compatible data container format, optional, default=None
        y and X can be in one of the following formats:
        Series scitype: pd.Series, pd.DataFrame, or np.ndarray (1D or 2D)
            for vanilla forecasting, one time series
        Panel scitype: pd.DataFrame with 2-level row MultiIndex,
            3D np.ndarray, list of Series pd.DataFrame, or nested pd.DataFrame
            for global or panel forecasting
        Hierarchical scitype: pd.DataFrame with 3 or more level row MultiIndex
            for hierarchical forecasting
        Number of columns admissible depend on the "scitype:y" tag:
            if self.get_tag("scitype:y")=="univariate":
                y must have a single column/variable
            if self.get_tag("scitype:y")=="multivariate":
                y must have 2 or more columns
            if self.get_tag("scitype:y")=="both": no restrictions on columns apply
        For further details:
            on usage, see forecasting tutorial examples/01_forecasting.ipynb
            on specification of formats, examples/AA_datatypes_and_datasets.ipynb
    test_size : float, int or None, optional (default=None)
        If float, should be between 0.0 and 1.0 and represent the proportion
        of the dataset to include in the test split. If int, represents the
        relative number of test samples. If None, the value is set to the
        complement of the train size. If ``train_size`` is also None, it will
        be set to 0.25.
    train_size : float, int, or None, (default=None)
        If float, should be between 0.0 and 1.0 and represent the
        proportion of the dataset to include in the train split. If
        int, represents the relative number of train samples. If None,
        the value is automatically set to the complement of the test size.
    fh : ForecastingHorizon

    Returns
    -------
    splitting : tuple, length = 2 * len(arrays)
        List containing train-test split of `y` and `X` if given.
        if ``X is None``, returns ``(y_train, y_test)``.
        Else, returns ``(y_train, y_test, X_train, X_test)``.

    References
    ----------
    .. [1]  adapted from https://github.com/alkaline-ml/pmdarima/
    """
    if fh is not None:
        if test_size is not None or train_size is not None:
            raise ValueError(
                "If `fh` is given, `test_size` and `train_size` cannot "
                "also be specified."
            )
        return _split_by_fh(y, fh, X=X)

    temporal_splitter = TemporalTrainTestSplitter(
        test_size=test_size, train_size=train_size
    )

    y_train, y_test = list(temporal_splitter.split_series(y))[0]

    if X is not None:
        X_train = X.loc[y_train.index]
        X_test = X.loc[y_test.index]
        return y_train, y_test, X_train, X_test
    else:
        return y_train, y_test


class TemporalTrainTestSplitter(BaseSplitter):
    r"""Temporal train-test splitter, based on sample sizes of train or test set.

    Cuts test and train sets from the start or end of available data,
    based on ``test_size`` and ``train_size`` parameters,
    which can signify fractions of total number of indices,
    or an absolute number of integers to cut.

    If the data contains multiple time series (Panel or Hierarchical),
    fractions and train-test sets will be computed per individual time series.

    Parameters
    ----------
    test_size : float, int or None, optional (default=None)
        If float, must be between 0.0 and 1.0, and is interpreted as the proportion
        of the dataset to include in the test split. Proportions are rounded to the
        next integer count of samples.
        If int, is interpreted as total number of test samples.
        If None, the value is set to the complement of the train size.
        If ``train_size`` is also None, it will be set to 0.25.
    train_size : float, int, or None, (default=None)
        If float, must be between 0.0 and 1.0, and is interpreted as the proportion
        of the dataset to include in the train split. Proportions are rounded to the
        next integer count of samples.
        If int, is interpreted as total number of train samples.
        If None, the value is set to the complement of the test size.
    anchor : str, "start" (default) or "end"
        determines behaviour if train and test sizes do not sum up to all data
        if "start", cuts train and test set from start of available series
        if "end", cuts train and test set from end of available series

    Examples
    --------
    >>> import numpy as np
    >>> from sktime.split import TemporalTrainTestSplitter
    >>> ts = np.arange(10)
    >>> splitter = TemporalTrainTestSplitter(test_size=0.3)
    >>> list(splitter.split(ts)) # doctest: +SKIP
    """

    _tags = {"split_hierarchical": True}

    def __init__(self, train_size, test_size, anchor):
        self.train_size = train_size
        self.test_size = test_size
        self.anchor = anchor
        super().__init__()

        # in this case, the inner ExpandingGreedySplitter is not hierarchical
        train_size_none_flt = train_size is None or isinstance(train_size, int)
        if not isinstance(test_size, int) or not train_size_none_flt:
            self.set_tags(**{"split_hierarchical": False})

    def _split(self, y: pd.Index):
        from sktime.forecasting.model_selection import ExpandingGreedySplitter

        test_size = self.test_size
        train_size = self.train_size
        anchor = self.anchor

        if test_size is None and train_size is None:
            test_size = 0.25

        if train_size is None:
            anchor = "end"
        if test_size is None:
            anchor = "start"

        if anchor == "end":
            splitter = ExpandingGreedySplitter(test_size, folds=1)
            y_train_ix, y_test_ix = list(splitter.split(y))[0]
            if train_size is not None:
                splitter = ExpandingGreedySplitter(train_size, folds=1)
                _, y_train_ix = list(splitter.split(y_train_ix))[0]
        else:  # if anchor == "start"
            splitter = ExpandingGreedySplitter(train_size, folds=1, reverse=True)
            y_test_ix, y_train_ix = list(splitter.split(y))[0]
            if train_size is not None:
                splitter = ExpandingGreedySplitter(train_size, folds=1, reverse=True)
                y_test_ix, _ = list(splitter.split(y_test_ix))[0]

        yield y_train_ix, y_test_ix

    def get_n_splits(self, y: Optional[ACCEPTED_Y_TYPES] = None) -> int:
        """Return the number of splits.

        Since this splitter returns a single train/test split,
        this number is trivially 1.

        Parameters
        ----------
        y : pd.Series or pd.Index, optional (default=None)
            Time series to split

        Returns
        -------
        n_splits : int
            The number of splits.
        """
        return 1

    @classmethod
    def get_test_params(cls, parameter_set="default"):
        """Return testing parameter settings for the splitter.

        Parameters
        ----------
        parameter_set : str, default="default"
            Name of the set of test parameters to return, for use in tests. If no
            special parameters are defined for a value, will return `"default"` set.

        Returns
        -------
        params : dict or list of dict, default = {}
            Parameters to create testing instances of the class
            Each dict are parameters to construct an "interesting" test instance, i.e.,
            `MyClass(**params)` or `MyClass(**params[i])` creates a valid test instance.
            `create_test_instance` uses the first (or only) dictionary in `params`
        """
        params1 = {"test_size": 0.2, "train_size": 0.3}
        params2 = {"test_size": 2}
        params3 = {"train_size": 3}
        params4 = {}
        return [params1, params2, params3, params4]
