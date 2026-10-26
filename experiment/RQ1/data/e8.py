def _check_local_fields(cls, fields, option):
    from django.db import models
    forward_fields_map = {}
    for field in cls._meta._get_fields(reverse=False):
        forward_fields_map[field.name] = field
        if hasattr(field, "attname"):
            forward_fields_map[field.attname] = field
    errors = []
    for field_name in fields:
        try:
            field = forward_fields_map[field_name]
        except KeyError:
            errors.append(
                checks.Error(
                    "'%s' refers to the nonexistent field '%s'."
                    % (
                        option,
                        field_name,
                    ),
                    obj=cls,
                    id="models.E012",
                )
            )
        else:
            if isinstance(field.remote_field, models.ManyToManyRel):
                errors.append(
                    checks.Error(
                        "'%s' refers to a ManyToManyField '%s', but "
                        "ManyToManyFields are not permitted in '%s'."
                        % (
                            option,
                            field_name,
                            option,
                        ),
                        obj=cls,
                        id="models.E013",
                    )
                )
            elif isinstance(field, models.CompositePrimaryKey):
                errors.append(
                    checks.Error(
                        f"{option!r} refers to a CompositePrimaryKey "
                        f"{field_name!r}, but CompositePrimaryKeys are not "
                        f"permitted in {option!r}.",
                        obj=cls,
                        id="models.E048",
                    )
                )
            elif (
                isinstance(field.remote_field, ForeignObjectRel)
                and field not in cls._meta.local_concrete_fields
                and len(field.from_fields) > 1
            ):
                errors.append(
                    checks.Error(
                        f"{option!r} refers to a ForeignObject {field_name!r} with "
                        "multiple 'from_fields', which is not supported for that "
                        "option.",
                        obj=cls,
                        id="models.E049",
                    )
                )
            elif field not in cls._meta.local_fields:
                errors.append(
                    checks.Error(
                        "'%s' refers to field '%s' which is not local to model "
                        "'%s'." % (option, field_name, cls._meta.object_name),
                        hint="This issue may be caused by multi-table inheritance.",
                        obj=cls,
                        id="models.E016",
                    )
                )
    return errors