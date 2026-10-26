def _is_valid_dist_file(filename, filetype, metrics, *, scan=True):
    is_zipfile = bool(filename and zipfile.is_zipfile(filename))
    is_tarfile = bool(filename and tarfile.is_tarfile(filename))
    if is_zipfile and is_tarfile:
        return False, "File is both a zip and a tar file"
    if filename.endswith((".zip", ".whl")):
        if not is_zipfile:
            return False, "File is not a zipfile"
        zfp = None
        try:
            zfp = zipfile.ZipFile(filename)
            compressed_size = os.stat(filename).st_size
            decompressed_size = sum(e.file_size for e in zfp.infolist())
            if (
                decompressed_size > COMPRESSION_RATIO_MIN_SIZE
                and decompressed_size / compressed_size > COMPRESSION_RATIO_THRESHOLD
            ):
                sentry_sdk.capture_message(
                    f"File {filename} ({filetype}) exceeds compression ratio "
                    f"of {COMPRESSION_RATIO_THRESHOLD} "
                    f"({decompressed_size}/{compressed_size})"
                )
                return (
                    False,
                    "File exceeds compression ratio of "
                    f"{COMPRESSION_RATIO_THRESHOLD}",
                )
            for zinfo in zfp.infolist():
                if zinfo.compress_type not in {
                    zipfile.ZIP_STORED,
                    zipfile.ZIP_DEFLATED,
                }:
                    return (
                        False,
                        "File does not use a supported compression type",
                    )
            if filename.endswith(".zip"):
                top_level = _commonpath(zfp.namelist())
                if top_level in [".", "/", ""]:
                    return (
                        False,
                        "Incorrect number of top-level directories in sdist",
                    )
                target_file = os.path.join(top_level, "PKG-INFO")
                try:
                    zfp.read(target_file)
                except KeyError:
                    return False, f"PKG-INFO not found at {target_file}"
            if filename.endswith(".whl"):
                try:
                    name, version, _ = os.path.basename(filename).split("-", 2)
                except ValueError:
                    return (
                        False,
                        "Unable to parse name and version from wheel filename",
                    )
                target_file = os.path.join(f"{name}-{version}.dist-info", "WHEEL")
                try:
                    zfp.read(target_file)
                except KeyError:
                    return False, f"WHEEL not found at {target_file}"
            if scan:
                yara_match = scanner.check_members(
                    scanner.iter_zip_members(zfp),
                    archive_name=os.path.basename(filename),
                    archive_type="zip",
                    metrics=metrics,
                )
                if yara_match is not None:
                    sentry_sdk.capture_message(
                        f"YARA rule {yara_match.rule!r} matched "
                        f"{yara_match.member!r} in {os.path.basename(filename)}"
                    )
                    return False, yara_match.message
            zip_ok, zip_error = zipfiles.validate_zipfile(filename)
            if not zip_ok:
                return False, f"ZIP archive not accepted: {zip_error}. "
        except zipfile.BadZipFile:
            return False, None
        finally:
            if zfp is not None:
                zfp.close()
    elif filename.endswith(".tar.gz"):
        if not is_tarfile:
            return False, "File is not a tarfile"
        tar = None
        try:
            tar = tarfile.open(filename, "r:gz")
            timer = metrics.timed("warehouse.upload.tarfile.getnames")
            timer.__enter__()
            try:
                top_level = _commonpath(tar.getnames())
            except BaseException as exc:
                timer.__exit__(type(exc), exc, exc.__traceback__)
                raise
            else:
                timer.__exit__(None, None, None)

            if top_level in [".", "/", ""]:
                return (
                    False,
                    "Incorrect number of top-level directories in sdist",
                )
            target_file = os.path.join(top_level, "PKG-INFO")
            try:
                tar.getmember(target_file)
            except KeyError:
                return False, f"PKG-INFO not found at {target_file}"
            if scan:
                yara_match = scanner.check_members(
                    scanner.iter_tar_members(tar),
                    archive_name=os.path.basename(filename),
                    archive_type="tar",
                    metrics=metrics,
                )
                if yara_match is not None:
                    sentry_sdk.capture_message(
                        f"YARA rule {yara_match.rule!r} matched "
                        f"{yara_match.member!r} in {os.path.basename(filename)}"
                    )
                    return False, yara_match.message
        except (tarfile.ReadError, EOFError):
            return False, None
        finally:
            if tar is not None:
                tar.close()
    return True, None
