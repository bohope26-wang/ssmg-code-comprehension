def check_array(
    array, accept_sparse=False, *, accept_large_sparse=True, dtype="numeric",
    order=None, copy=False, force_writeable=False, ensure_all_finite=True,
    ensure_non_negative=False, ensure_2d=True, allow_nd=False,
    ensure_min_samples=1, ensure_min_features=1, estimator=None, input_name="",
):
    if isinstance(array, np.matrix):
        raise TypeError("np.matrix is not supported. Convert it with np.asarray.")

    array_orig = array
    estimator_name = _check_estimator_name(estimator)
    context = " by %s" % estimator_name if estimator is not None else ""

    dtype_numeric = isinstance(dtype, str) and dtype == "numeric"
    dtype_orig = getattr(array, "dtype", None)
    type_if_series = None

    if hasattr(array, "iloc") and hasattr(array, "dtype"):
        type_if_series = type(array)
        if isinstance(array.dtype, np.dtype):
            dtype_orig = array.dtype
        elif _is_pandas_string_dtype(array.dtype):
            dtype_orig = object
        else:
            dtype_orig = None

    if dtype_numeric:
        if dtype_orig is not None and (
            (hasattr(dtype_orig, "kind") and dtype_orig.kind == "O")
            or dtype_orig == object
        ):
            dtype = np.float64
        else:
            dtype = None

    if isinstance(dtype, (list, tuple)):
        if dtype_orig is not None and dtype_orig in dtype:
            dtype = None
        else:
            dtype = dtype[0]

    if ensure_all_finite not in (True, False, "allow-nan"):
        raise ValueError(f"Invalid ensure_all_finite={ensure_all_finite!r}.")

    if dtype is not None:
        dtype = np.dtype(dtype)

    if sp.issparse(array):
        _ensure_no_complex_data(array)
        array = _ensure_sparse_format(
            array,
            accept_sparse=accept_sparse,
            dtype=dtype,
            copy=copy,
            ensure_all_finite=ensure_all_finite,
            accept_large_sparse=accept_large_sparse,
            estimator_name=estimator_name,
            input_name=input_name,
        )
        if ensure_2d and array.ndim < 2:
            raise ValueError(f"Expected 2D sparse input, got shape {array.shape}.")
    else:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", ComplexWarning)
                if dtype is not None and np.issubdtype(dtype, np.integer):
                    array = np.asarray(array, order=order)
                    if np.issubdtype(array.dtype, np.floating):
                        _assert_all_finite(
                            array,
                            allow_nan=False,
                            msg_dtype=dtype,
                            estimator_name=estimator_name,
                            input_name=input_name,
                        )
                    array = array.astype(dtype, copy=False)
                else:
                    array = np.asarray(array, dtype=dtype, order=order)
        except ComplexWarning as complex_warning:
            raise ValueError(f"Complex data not supported\n{array}") from complex_warning

        _ensure_no_complex_data(array)

        if ensure_2d:
            if array.ndim == 0:
                raise ValueError(
                    "Expected 2D array, got scalar array instead. "
                    "Use reshape(-1, 1) or reshape(1, -1)."
                )
            if array.ndim == 1:
                if type_if_series is not None:
                    raise ValueError(f"Expected a 2D container but got {type_if_series}.")
                raise ValueError(
                    "Expected 2D array, got 1D array instead. "
                    "Use reshape(-1, 1) or reshape(1, -1)."
                )

        if dtype_numeric and hasattr(array.dtype, "kind") and array.dtype.kind in "USV":
            raise ValueError("dtype='numeric' is not compatible with strings.")

        if not allow_nd and array.ndim >= 3:
            raise ValueError(f"Found dim {array.ndim}, while dim <= 2 is required{context}.")

        if ensure_all_finite:
            _assert_all_finite(
                array,
                input_name=input_name,
                estimator_name=estimator_name,
                allow_nan=ensure_all_finite == "allow-nan",
            )

        if copy and np.may_share_memory(array, array_orig):
            array = np.array(array, dtype=dtype, order=order, copy=True)

    if ensure_min_samples > 0:
        n_samples = _num_samples(array)
        if n_samples < ensure_min_samples:
            raise ValueError(
                "Found %d sample(s); minimum is %d%s."
                % (n_samples, ensure_min_samples, context)
            )

    if ensure_min_features > 0 and array.ndim == 2:
        n_features = array.shape[1]
        if n_features < ensure_min_features:
            raise ValueError(
                "Found %d feature(s); minimum is %d%s."
                % (n_features, ensure_min_features, context)
            )

    if ensure_non_negative:
        whom = input_name
        if estimator_name:
            whom += f" in {estimator_name}"
        check_non_negative(array, whom)

    if force_writeable:
        array_data = array.data if sp.issparse(array) else array
        flags = getattr(array_data, "flags", None)
        if not getattr(flags, "writeable", True):
            array = array.copy()

    return array
