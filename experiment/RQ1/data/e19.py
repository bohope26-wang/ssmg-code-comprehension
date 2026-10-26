def package_data_export(records, schema, privacy_rules, delivery_options):
    exported = []
    rejected = []
    stats = defaultdict(int)
    fields = schema.get("fields", [])
    required_fields = {field["name"] for field in fields if field.get("required")}
    field_index = {field["name"]: field for field in fields}
    mask_fields = set(privacy_rules.get("mask_fields", []))
    drop_fields = set(privacy_rules.get("drop_fields", []))
    allow_regions = set(privacy_rules.get("allowed_regions", []))
    format_name = delivery_options.get("format", "json")
    if format_name not in {"json", "csv", "ndjson"}:
        raise ValueError("unsupported export format")
    def convert_value(value, field):
        kind = field.get("type", "string")
        if value in (None, ""):
            if field.get("default") is not None:
                value = field["default"]
            elif field.get("required"):
                raise ValueError("missing_required")
            else:
                return None
        if kind == "int":
            return int(value)
        if kind == "float":
            return float(value)
        if kind == "bool":
            return str(value).strip().lower() in {"true", "1", "yes", "y"}
        if kind == "date":
            return datetime.fromisoformat(str(value)).date().isoformat()
        if kind == "list":
            if isinstance(value, list):
                return value
            return [item.strip() for item in str(value).split(",") if item.strip()]
        return str(value).strip()
    def mask_value(name, value):
        if value is None:
            return None
        strategy = privacy_rules.get("strategies", {}).get(name, "redact")
        text = str(value)
        if strategy == "last4":
            return "*" * max(0, len(text) - 4) + text[-4:]
        if strategy == "email":
            local, _, domain = text.partition("@")
            return (local[:1] + "***@" + domain) if domain else "***"
        if strategy == "hash":
            return str(abs(hash(text)) % 10_000_000)
        return "***"
    for row_number, record in enumerate(records, start=1):
        region = record.get("region")
        if allow_regions and region not in allow_regions:
            rejected.append({"row": row_number, "reason": "region_not_allowed"})
            stats["rejected_region"] += 1
            continue
        missing = [name for name in required_fields if record.get(name) in (None, "")]
        if missing:
            rejected.append({"row": row_number, "reason": "missing_required", "fields": missing})
            stats["rejected_missing"] += 1
            if delivery_options.get("strict"):
                continue
        output = {}
        row_errors = []
        for name, field in field_index.items():
            if name in drop_fields:
                stats["field_dropped"] += 1
                continue
            raw_value = record.get(name)
            try:
                value = convert_value(raw_value, field)
            except (TypeError, ValueError):
                row_errors.append(name)
                value = field.get("default")
            if name in mask_fields:
                value = mask_value(name, value)
                stats["field_masked"] += 1
            choices = field.get("choices")
            if choices and value not in choices and value is not None:
                row_errors.append(name)
            output[name] = value
        if row_errors:
            rejected.append({"row": row_number, "reason": "conversion_error", "fields": sorted(set(row_errors))})
            stats["rejected_conversion"] += 1
            if delivery_options.get("strict"):
                continue
        exported.append(output)
        stats["exported"] += 1
    if delivery_options.get("include_header", True) and format_name == "csv":
        header = [name for name in field_index if name not in drop_fields]
    else:
        header = []
    checksum_seed = "|".join(str(row.get(name, "")) for row in exported for name in field_index if name not in drop_fields)
    manifest = {
        "format": format_name,
        "record_count": len(exported),
        "rejected_count": len(rejected),
        "header": header,
        "checksum": str(abs(hash(checksum_seed)) % 1_000_000_000),
        "stats": dict(stats),
    }
    return {"records": exported, "rejected": rejected, "manifest": manifest}
