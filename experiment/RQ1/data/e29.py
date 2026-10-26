def consolidate_lab_sample_results(sample_batches, assay_catalog, quality_controls, reporting_rules):
    sample_results = []
    rerun_queue = []
    rejected_samples = []
    batch_summary = defaultdict(int)
    assay_index = {assay["id"]: assay for assay in assay_catalog if assay.get("id")}
    qc_by_assay = defaultdict(list)
    for qc in quality_controls:
        assay_id = qc.get("assay_id")
        if assay_id:
            qc_by_assay[assay_id].append(qc)
    for batch in sample_batches:
        batch_id = batch.get("id")
        received_at = batch.get("received_at")
        try:
            received_time = datetime.fromisoformat(str(received_at)) if received_at else None
        except ValueError:
            received_time = None
            batch_summary["bad_received_time"] += 1
        for sample in batch.get("samples", []):
            sample_id = sample.get("id")
            assay_id = sample.get("assay_id")
            patient_id = sample.get("patient_id")
            raw_value = sample.get("value")
            units = sample.get("units")
            flags = []
            comments = []
            status = "reportable"
            if not sample_id or not patient_id:
                rejected_samples.append({"batch_id": batch_id, "sample_id": sample_id, "reason": "missing_identity"})
                batch_summary["rejected"] += 1
                continue
            if assay_id not in assay_index:
                rejected_samples.append({"batch_id": batch_id, "sample_id": sample_id, "reason": "unknown_assay"})
                batch_summary["rejected"] += 1
                continue
            assay = assay_index[assay_id]
            try:
                numeric_value = float(raw_value)
            except (TypeError, ValueError):
                numeric_value = None
                status = "rerun"
                flags.append("non_numeric_result")
            expected_units = assay.get("units")
            if units != expected_units:
                conversion = assay.get("unit_conversions", {}).get((units, expected_units))
                if conversion and numeric_value is not None:
                    numeric_value *= float(conversion)
                    units = expected_units
                    flags.append("unit_converted")
                else:
                    status = "rerun"
                    flags.append("unit_mismatch")
            if sample.get("hemolyzed") and assay.get("hemolysis_sensitive"):
                status = "rerun"
                flags.append("hemolysis_interference")
            if sample.get("volume_ul", assay.get("minimum_volume_ul", 0)) < assay.get("minimum_volume_ul", 0):
                status = "rerun"
                flags.append("insufficient_volume")
            if received_time and sample.get("collected_at"):
                try:
                    collected_at = datetime.fromisoformat(str(sample.get("collected_at")))
                    stability_hours = assay.get("stability_hours")
                    if stability_hours and (received_time - collected_at).total_seconds() / 3600 > stability_hours:
                        status = "rerun"
                        flags.append("stability_exceeded")
                except ValueError:
                    flags.append("bad_collection_time")
            qc_failures = []
            for qc in qc_by_assay.get(assay_id, []):
                control_value = qc.get("value")
                low = qc.get("low")
                high = qc.get("high")
                try:
                    control_value = float(control_value)
                    low = float(low)
                    high = float(high)
                except (TypeError, ValueError):
                    qc_failures.append("invalid_qc_record")
                    continue
                if control_value < low or control_value > high:
                    qc_failures.append(qc.get("control_id", "qc_out_of_range"))
            if qc_failures:
                status = "hold" if status != "rerun" else status
                flags.extend(qc_failures)
            interpretation = "not_available"
            if numeric_value is not None and status == "reportable":
                low = assay.get("reference_low")
                high = assay.get("reference_high")
                critical_low = assay.get("critical_low")
                critical_high = assay.get("critical_high")
                if critical_low is not None and numeric_value <= float(critical_low):
                    interpretation = "critical_low"
                    flags.append("critical_result")
                elif critical_high is not None and numeric_value >= float(critical_high):
                    interpretation = "critical_high"
                    flags.append("critical_result")
                elif low is not None and numeric_value < float(low):
                    interpretation = "low"
                elif high is not None and numeric_value > float(high):
                    interpretation = "high"
                else:
                    interpretation = "normal"
            if "critical_result" in flags and not reporting_rules.get("allow_auto_release_critical", False):
                status = "hold"
                comments.append("critical_result_requires_review")
            if status == "rerun":
                rerun_queue.append({"sample_id": sample_id, "assay_id": assay_id, "reason": sorted(set(flags))})
            sample_results.append(
                {
                    "batch_id": batch_id,
                    "sample_id": sample_id,
                    "patient_id": patient_id,
                    "assay_id": assay_id,
                    "value": round(numeric_value, 4) if numeric_value is not None else None,
                    "units": units,
                    "status": status,
                    "interpretation": interpretation,
                    "flags": sorted(set(flags)),
                    "comments": comments,
                }
            )
            batch_summary[status] += 1
    releaseable = [row for row in sample_results if row["status"] == "reportable"]
    held = [row for row in sample_results if row["status"] == "hold"]
    return {
        "results": sample_results,
        "releaseable_count": len(releaseable),
        "held_count": len(held),
        "rerun_queue": rerun_queue,
        "rejected_samples": rejected_samples,
        "summary": dict(batch_summary),
    }