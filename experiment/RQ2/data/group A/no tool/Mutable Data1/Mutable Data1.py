def prepare_body(
    self, data: _t.DataType, files: _t.FilesType, json: _t.JsonType = None
) -> None:
    body = None
    content_type = None

    if not data and json is not None:
        content_type = "application/json"

        try:
            body = complexjson.dumps(json, allow_nan=False)
        except ValueError as ve:
            raise InvalidJSONError(ve, request=self)

        if not isinstance(body, bytes):
            body = body.encode("utf-8")

    is_iterable = isinstance(data, Iterable) or hasattr(data, "__iter__")
    if is_iterable and not isinstance(data, (str, bytes, list, tuple, Mapping)):
        try:
            length = super_len(data)
        except (TypeError, AttributeError, UnsupportedOperation):
            length = None

        body = data

        if getattr(body, "tell", None) is not None:
            try:
                self._body_position = body.tell()  
            except OSError:
                self._body_position = object()

        if files:
            raise NotImplementedError(
                "Streamed bodies and files are mutually exclusive."
            )

        if length:
            self.headers["Content-Length"] = builtin_str(length)
        else:
            self.headers["Transfer-Encoding"] = "chunked"
    else:
        raw_data = cast("_t.RawDataType | None", data)
        if files:
            (body, content_type) = self._encode_files(files, raw_data)
        else:
            if raw_data:
                body = self._encode_params(raw_data)
                if isinstance(data, basestring) or _t.has_read(data):
                    content_type = None
                else:
                    content_type = "application/x-www-form-urlencoded"

        self.prepare_content_length(body)

        if content_type and ("content-type" not in self.headers):
            self.headers["Content-Type"] = content_type

    self.body = body 
