def process_media_asset_pipeline(assets, transcode_profiles, rights_catalog, publishing_rules):
    asset_results = []
    transcode_jobs = []
    blocked_assets = []
    profile_index = {profile["name"]: profile for profile in transcode_profiles if profile.get("name")}
    rights_index = {item["asset_id"]: item for item in rights_catalog if item.get("asset_id")}
    allowed_regions = set(publishing_rules.get("regions", []))
    required_profiles = list(publishing_rules.get("required_profiles", []))
    max_duration = int(publishing_rules.get("max_duration_seconds", 4 * 3600))
    summary = defaultdict(int)
    for asset in assets:
        asset_id = asset.get("id")
        media_type = asset.get("type", "video")
        duration = int(asset.get("duration_seconds", 0) or 0)
        source_path = str(asset.get("source_path", "")).strip()
        metadata = asset.get("metadata", {}) or {}
        requested_regions = set(asset.get("regions", [])) or allowed_regions
        status = "ready"
        reasons = []
        warnings = []
        jobs_for_asset = []
        if not asset_id:
            status = "blocked"
            reasons.append("missing_asset_id")
        if not source_path:
            status = "blocked"
            reasons.append("missing_source_path")
        if duration <= 0:
            status = "blocked"
            reasons.append("invalid_duration")
        if duration > max_duration:
            status = "blocked"
            reasons.append("duration_exceeds_policy")
        if media_type not in {"video", "audio"}:
            status = "blocked"
            reasons.append("unsupported_media_type")
        title = str(metadata.get("title", "")).strip()
        language = str(metadata.get("language", "")).strip().lower()
        rating = str(metadata.get("rating", "")).strip().upper()
        if len(title) < publishing_rules.get("min_title_length", 3):
            warnings.append("short_or_missing_title")
            if publishing_rules.get("require_title"):
                status = "blocked"
                reasons.append("title_required")
        if language not in publishing_rules.get("allowed_languages", [language]):
            status = "blocked"
            reasons.append("language_not_allowed")
        if rating in publishing_rules.get("blocked_ratings", []):
            status = "blocked"
            reasons.append("rating_blocked")
        rights = rights_index.get(asset_id)
        if not rights:
            status = "blocked"
            reasons.append("missing_rights")
            permitted_regions = set()
        else:
            permitted_regions = set(rights.get("regions", []))
            if rights.get("expires_at"):
                try:
                    expires_at = datetime.fromisoformat(str(rights["expires_at"]))
                    if expires_at < datetime.utcnow():
                        status = "blocked"
                        reasons.append("rights_expired")
                except ValueError:
                    status = "blocked"
                    reasons.append("invalid_rights_expiry")
            if not requested_regions.issubset(permitted_regions):
                status = "blocked"
                reasons.append("requested_region_not_permitted")
            if rights.get("exclusive_to") and rights.get("exclusive_to") != publishing_rules.get("platform"):
                status = "blocked"
                reasons.append("exclusive_rights_conflict")
        if not required_profiles:
            if media_type == "video":
                required_profiles = ["video_720p", "video_1080p"]
            else:
                required_profiles = ["audio_aac"]
        for profile_name in required_profiles:
            profile = profile_index.get(profile_name)
            if not profile:
                warnings.append(f"profile_missing:{profile_name}")
                status = "review" if status == "ready" else status
                continue
            if media_type not in profile.get("media_types", [media_type]):
                warnings.append(f"profile_incompatible:{profile_name}")
                continue
            if profile.get("max_duration") and duration > int(profile["max_duration"]):
                warnings.append(f"profile_duration_limit:{profile_name}")
                status = "review" if status == "ready" else status
                continue
            job_priority = int(asset.get("priority", 5) or 5)
            if rating in publishing_rules.get("sensitive_ratings", []):
                job_priority += 2
            if asset.get("release_date"):
                try:
                    release_date = datetime.fromisoformat(str(asset["release_date"]))
                    if (release_date - datetime.utcnow()).days <= 2:
                        job_priority -= 2
                except ValueError:
                    warnings.append("bad_release_date")
            job = {
                "asset_id": asset_id,
                "profile": profile_name,
                "source": source_path,
                "target_extension": profile.get("extension", "mp4"),
                "priority": max(1, job_priority),
                "estimated_minutes": round(duration / max(1, int(profile.get("speed_factor", 60))), 2),
            }
            jobs_for_asset.append(job)
        if status == "blocked":
            blocked_assets.append({"asset_id": asset_id, "reasons": sorted(set(reasons))})
            summary["blocked"] += 1
        elif status == "review" or warnings:
            summary["review"] += 1
            if status == "ready":
                status = "review"
        else:
            summary["ready"] += 1
        if status != "blocked":
            transcode_jobs.extend(jobs_for_asset)
        asset_results.append(
            {
                "asset_id": asset_id,
                "status": status,
                "media_type": media_type,
                "duration_seconds": duration,
                "regions": sorted(requested_regions),
                "job_count": len(jobs_for_asset) if status != "blocked" else 0,
                "warnings": sorted(set(warnings)),
                "reasons": sorted(set(reasons)),
            }
        )
    transcode_jobs.sort(key=lambda row: (row["priority"], -row["estimated_minutes"], row["asset_id"], row["profile"]))
    return {
        "assets": asset_results,
        "transcode_jobs": transcode_jobs,
        "blocked_assets": blocked_assets,
        "summary": dict(summary),
    }
