def migrate_user_preferences(old_records, mapping, defaults, feature_flags):
    migrated = []
    errors = []
    stats = defaultdict(int)
    rename_map = mapping.get("rename", {})
    type_map = mapping.get("types", {})
    deprecated = set(mapping.get("deprecated", []))
    split_rules = mapping.get("split", {})
    merge_rules = mapping.get("merge", {})
    def coerce_value(name, value):
        target = type_map.get(name, "string")
        if value in (None, ""):
            return defaults.get(name)
        if target == "bool":
            return str(value).strip().lower() in {"true", "1", "yes", "on"}
        if target == "int":
            return int(value)
        if target == "float":
            return float(value)
        if target == "list":
            if isinstance(value, list):
                return value
            return [part.strip() for part in str(value).split(",") if part.strip()]
        if target == "dict":
            if isinstance(value, dict):
                return value
            raise ValueError("expected_dict")
        return str(value).strip()
    for row_number, record in enumerate(old_records, start=1):
        user_id = record.get("user_id") or record.get("id")
        if not user_id:
            errors.append({"row": row_number, "reason": "missing_user_id"})
            stats["missing_user_id"] += 1
            continue
        new_record = {"user_id": user_id, "settings": {}, "metadata": {"migrated": True, "warnings": []}}
        raw_settings = record.get("settings", record)
        for old_name, value in raw_settings.items():
            if old_name in {"user_id", "id"}:
                continue
            if old_name in deprecated:
                stats["deprecated_skipped"] += 1
                continue
            if old_name in split_rules:
                rule = split_rules[old_name]
                separator = rule.get("separator", ",")
                parts = [part.strip() for part in str(value).split(separator)]
                for target_name, index in rule.get("targets", {}).items():
                    if index < len(parts):
                        try:
                            new_record["settings"][target_name] = coerce_value(target_name, parts[index])
                        except (TypeError, ValueError):
                            new_record["metadata"]["warnings"].append(f"{target_name}:coerce_failed")
                            stats["coerce_failed"] += 1
                continue
            new_name = rename_map.get(old_name, old_name)
            try:
                new_record["settings"][new_name] = coerce_value(new_name, value)
            except (TypeError, ValueError):
                new_record["settings"][new_name] = defaults.get(new_name)
                new_record["metadata"]["warnings"].append(f"{new_name}:defaulted")
                stats["coerce_failed"] += 1
        for target_name, source_names in merge_rules.items():
            values = []
            for source_name in source_names:
                if source_name in new_record["settings"]:
                    values.append(new_record["settings"].pop(source_name))
            if values:
                if type_map.get(target_name) == "list":
                    merged = []
                    for value in values:
                        if isinstance(value, list):
                            merged.extend(value)
                        else:
                            merged.append(value)
                    new_record["settings"][target_name] = merged
                else:
                    new_record["settings"][target_name] = values[-1]
        for name, default_value in defaults.items():
            if name not in new_record["settings"]:
                new_record["settings"][name] = default_value
                stats["default_added"] += 1
        if feature_flags.get("normalize_theme"):
            theme = str(new_record["settings"].get("theme", "")).lower()
            if theme in {"darkmode", "night"}:
                new_record["settings"]["theme"] = "dark"
            elif theme in {"lightmode", "day"}:
                new_record["settings"]["theme"] = "light"
        if feature_flags.get("drop_empty_lists"):
            empty_list_keys = [key for key, value in new_record["settings"].items() if value == []]
            for key in empty_list_keys:
                del new_record["settings"][key]
                stats["empty_list_dropped"] += 1
        if feature_flags.get("record_source_version"):
            new_record["metadata"]["source_version"] = record.get("version", "unknown")
        migrated.append(new_record)
        stats["migrated"] += 1
    return {"records": migrated, "errors": errors, "stats": dict(stats)}
