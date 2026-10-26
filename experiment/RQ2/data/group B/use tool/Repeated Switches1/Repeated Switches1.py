def prepare_url(
    self,
    url: _t.UriType,
    params: _t.ParamsType,
) -> None:
    if isinstance(url, bytes):
        url = url.decode("utf8")
    else:
        url = str(url)
    url = url.lstrip()
    if ":" in url and not url.lower().startswith("http"):
        self.url = url
        return

    try:
        scheme, auth, host, port, path, query, fragment = parse_url(url)
    except LocationParseError as e:
        raise InvalidURL(*e.args)

    if not scheme:
        raise MissingSchema(
            f"Invalid URL {url!r}: No scheme supplied. "
            f"Perhaps you meant https://{url}?"
        )

    if not host:
        raise InvalidURL(f"Invalid URL {url!r}: No host supplied")

    if not unicode_is_ascii(host):
        try:
            host = self._get_idna_encoded_host(host)
        except UnicodeError:
            raise InvalidURL("URL has an invalid label.")
    elif host.startswith(("*", ".")):
        raise InvalidURL("URL has an invalid label.")

    netloc = auth or ""
    if netloc:
        netloc += "@"
    netloc += host
    if port:
        netloc += f":{port}"

    if not path:
        path = "/"

    if isinstance(params, (str, bytes)):
        params = to_native_string(params)

    if params is not None:
        enc_params = self._encode_params(params)
    else:
        enc_params = ""

    if enc_params:
        if query:
            query = f"{query}&{enc_params}"
        else:
            query = enc_params

    url = requote_uri(urlunparse((scheme, netloc, path, "", query, fragment)))
    self.url = url