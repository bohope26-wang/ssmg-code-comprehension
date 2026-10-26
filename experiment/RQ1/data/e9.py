def resolve_redirects(
    self,
    resp: Response,
    req: PreparedRequest,
    stream: bool = False,
    timeout: _t.TimeoutType = None,
    verify: _t.VerifyType = True,
    cert: _t.CertType = None,
    proxies: dict[str, str] | None = None,
    yield_requests: bool = False,
    **adapter_kwargs: Any,
) -> Generator[Response, None, None]:
    hist: list[Response] = []
    url = self.get_redirect_target(resp)
    previous_fragment = urlparse(req.url).fragment
    while url:
        prepared_request = req.copy()
        resp.history = hist[:]
        hist.append(resp)
        try:
            resp.content
        except (ChunkedEncodingError, ContentDecodingError, RuntimeError):
            resp.raw.read(decode_content=False)
        if len(resp.history) >= self.max_redirects:
            raise TooManyRedirects(
                f"Exceeded {self.max_redirects} redirects.", response=resp
            )
        resp.close()
        if url.startswith("//"):
            parsed_rurl = urlparse(resp.url)
            url = ":".join([to_native_string(parsed_rurl.scheme), url])
        parsed = urlparse(url)
        if parsed.fragment == "" and previous_fragment:
            parsed = parsed._replace(fragment=previous_fragment)
        elif parsed.fragment:
            previous_fragment = parsed.fragment
        url = parsed.geturl()
        if not parsed.netloc:
            url = urljoin(resp.url, requote_uri(url))
        else:
            url = requote_uri(url)
        prepared_request.url = to_native_string(url)
        self.rebuild_method(prepared_request, resp)
        if resp.status_code not in (
            codes.temporary_redirect,
            codes.permanent_redirect,
        ):
            purged_headers = ("Content-Length", "Content-Type", "Transfer-Encoding")
            for header in purged_headers:
                prepared_request.headers.pop(header, None)
            prepared_request.body = None
        headers = prepared_request.headers
        headers.pop("Cookie", None)
        cookie_jar = cast("CookieJar", prepared_request._cookies)
        extract_cookies_to_jar(cookie_jar, req, resp.raw)
        merge_cookies(cookie_jar, self.cookies)
        prepared_request.prepare_cookies(cookie_jar)
        proxies = self.rebuild_proxies(prepared_request, proxies)
        self.rebuild_auth(prepared_request, resp)
        rewindable = prepared_request._body_position is not None and (
            "Content-Length" in headers or "Transfer-Encoding" in headers
        )
        if rewindable:
            rewind_body(prepared_request)
        req = prepared_request
        if yield_requests:
            yield req
        else:
            resp = self.send(
                req,
                stream=stream,
                timeout=timeout,
                verify=verify,
                cert=cert,
                proxies=proxies,
                allow_redirects=False,
                **adapter_kwargs,
            )
            extract_cookies_to_jar(self.cookies, prepared_request, resp.raw)
            url = self.get_redirect_target(resp)
            yield resp