def _check_ordering(cls):
    if cls._meta._ordering_clash:
        return [
            checks.Error(
                "'ordering' and 'order_with_respect_to' cannot be used together.",
                obj=cls,
                id="models.E021",
            ),
        ]

    if cls._meta.order_with_respect_to or not cls._meta.ordering:
        return []

    if not isinstance(cls._meta.ordering, (list, tuple)):
        return [
            checks.Error(
                "'ordering' must be a tuple or list (even if you want to order by "
                "only one field).",
                obj=cls,
                id="models.E014",
            )
        ]

    errors = []
    fields = cls._meta.ordering
    fields = (f for f in fields if isinstance(f, str) and f != "?")
    fields = (f.removeprefix("-") for f in fields)
    _fields = []
    related_fields = []
    for f in fields:
        if LOOKUP_SEP in f:
            related_fields.append(f)
        else:
            _fields.append(f)
    fields = _fields
    
    for field in related_fields:
        _cls = cls
        fld = None
        for part in field.split(LOOKUP_SEP):
            try:
                if part == "pk":
                    fld = _cls._meta.pk
                else:
                    fld = _cls._meta.get_field(part)
                if fld.is_relation:
                    _cls = fld.path_infos[-1].to_opts.model
                else:
                    _cls = None
            except (FieldDoesNotExist, AttributeError):
                if fld is None or (
                    fld.get_transform(part) is None and fld.get_lookup(part) is None
                ):
                    errors.append(
                        checks.Error(
                            "'ordering' refers to the nonexistent field, "
                            "related field, or lookup '%s'." % field,
                            obj=cls,
                            id="models.E015",
                        )
                    )
    fields = {f for f in fields if f != "pk"}
    invalid_fields = []
    opts = cls._meta
    valid_fields = set(
        chain.from_iterable(
            (
                (f.name, f.attname)
                if not (f.auto_created and not f.concrete)
                else (f.field.related_query_name(),)
            )
            for f in chain(opts.fields, opts.related_objects)
        )
    )
    invalid_fields.extend(fields - valid_fields)
    for invalid_field in invalid_fields:
        errors.append(
            checks.Error(
                "'ordering' refers to the nonexistent field, related "
                "field, or lookup '%s'." % invalid_field,
                obj=cls,
                id="models.E015",
            )
        )
    return errors