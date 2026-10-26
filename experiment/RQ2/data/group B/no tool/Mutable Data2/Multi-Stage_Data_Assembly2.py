def get_uri(self) -> str:
    conn_type = getattr(self, "_prenormalized_conn_type", self.conn_type) or ""
    if "_" in conn_type:
        self.log.warning(
            "Connection schemes (type: %s) shall not contain '_' according to RFC3986.",
            conn_type,
        )

    if self.conn_type:
        uri = f"{self.conn_type.lower().replace('_', '-')}://"
    else:
        uri = "//"

    host_to_use: str | None
    protocol_to_add: str | None

    if self.host and "://" in self.host:
        protocol, host = self.host.split("://", 1)
        if protocol == self.conn_type:
            host_to_use = self.host
            protocol_to_add = None
        else:
            host_to_use = host
            protocol_to_add = protocol
    else:
        host_to_use = self.host
        protocol_to_add = None

    if protocol_to_add:
        uri += f"{protocol_to_add}://"

    authority_block = ""
    if self.login is not None:
        authority_block += quote(self.login, safe="")

    if self.password is not None:
        authority_block += ":" + quote(self.password, safe="")

    if authority_block > "":
        authority_block += "@"

        uri += authority_block

    host_block = ""
    if host_to_use:
        host_block += quote(host_to_use, safe="")

    if self.port:
        if host_block == "" and authority_block == "":
            host_block += f"@:{self.port}"
        else:
            host_block += f":{self.port}"

    if self.schema:
        host_block += f"/{quote(self.schema, safe='')}"

    uri += host_block

    if self.extra:
        extra_dict = self.extra_dejson
        can_flatten = True
        for value in extra_dict.values():
            if not isinstance(value, str):
                can_flatten = False
                break

        try:
            query: str | None = urlencode(extra_dict)
        except TypeError:
            query = None

        if can_flatten and query and extra_dict == dict(parse_qsl(query, keep_blank_values=True)):
            uri += ("?" if self.schema else "/?") + query
        else:
            uri += ("?" if self.schema else "/?") + urlencode({self.EXTRA_KEY: self.extra})
    return uri
