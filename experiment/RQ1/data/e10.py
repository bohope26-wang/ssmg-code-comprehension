def _check_psd_eigenvalues(lambdas, enable_warnings=False):
    lambdas = np.array(lambdas)
    is_double_precision = lambdas.dtype == np.float64
    significant_imag_ratio = 1e-5
    significant_neg_ratio = 1e-5 if is_double_precision else 5e-3
    significant_neg_value = 1e-10 if is_double_precision else 1e-6
    small_pos_ratio = 1e-12 if is_double_precision else 2e-7
    if not np.isreal(lambdas).all():
        max_imag_abs = np.abs(np.imag(lambdas)).max()
        max_real_abs = np.abs(np.real(lambdas)).max()
        if max_imag_abs > significant_imag_ratio * max_real_abs:
            raise ValueError(
                "There are significant imaginary parts in eigenvalues (%g "
                "of the maximum real part). Either the matrix is not PSD, or "
                "there was an issue while computing the eigendecomposition "
                "of the matrix." % (max_imag_abs / max_real_abs)
            )
        if enable_warnings:
            warnings.warn(
                "There are imaginary parts in eigenvalues (%g "
                "of the maximum real part). Either the matrix is not"
                " PSD, or there was an issue while computing the "
                "eigendecomposition of the matrix. Only the real "
                "parts will be kept." % (max_imag_abs / max_real_abs),
                PositiveSpectrumWarning,
            )
    lambdas = np.real(lambdas)
    max_eig = lambdas.max()
    if max_eig < 0:
        raise ValueError(
            "All eigenvalues are negative (maximum is %g). "
            "Either the matrix is not PSD, or there was an "
            "issue while computing the eigendecomposition of "
            "the matrix." % max_eig
        )
    else:
        min_eig = lambdas.min()
        if (
            min_eig < -significant_neg_ratio * max_eig
            and min_eig < -significant_neg_value
        ):
            raise ValueError(
                "There are significant negative eigenvalues (%g"
                " of the maximum positive). Either the matrix is "
                "not PSD, or there was an issue while computing "
                "the eigendecomposition of the matrix." % (-min_eig / max_eig)
            )
        elif min_eig < 0:
            if enable_warnings:
                warnings.warn(
                    "There are negative eigenvalues (%g of the "
                    "maximum positive). Either the matrix is not "
                    "PSD, or there was an issue while computing the"
                    " eigendecomposition of the matrix. Negative "
                    "eigenvalues will be replaced with 0." % (-min_eig / max_eig),
                    PositiveSpectrumWarning,
                )
            lambdas[lambdas < 0] = 0
    too_small_lambdas = (0 < lambdas) & (lambdas < small_pos_ratio * max_eig)
    if too_small_lambdas.any():
        if enable_warnings:
            warnings.warn(
                "Badly conditioned PSD matrix spectrum: the largest "
                "eigenvalue is more than %g times the smallest. "
                "Small eigenvalues will be replaced with 0."
                "" % (1 / small_pos_ratio),
                PositiveSpectrumWarning,
            )
        lambdas[too_small_lambdas] = 0
    return lambdas
