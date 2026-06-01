from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request, send_file, make_response

from container import container
from services.report_service import ReportService
from utils.decorators import token_required

logger = logging.getLogger(__name__)

report_bp = Blueprint("report", __name__, url_prefix="/api/reports")


def _add_no_cache_headers(response):
    """Add headers to prevent report data caching - ensures fresh data on every request"""
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


def _has_area_access(user_id: int, is_admin: bool, plant: str, area: str) -> bool:
    """Check area access using the per-user assignment system (user_area_assignments).
    No fallback — empty assignments means no access. All access is configured via Admin panel."""
    if is_admin:
        return True

    # Per-user explicit area assignments (sole authority)
    assigned = container.area_access_service.get_user_area_access(user_id)
    if assigned is None:
        # Service error / admin bypass signal
        return True
    if assigned:
        return any(a.get("plant") == plant and a.get("area") == area for a in assigned)

    # No assignments configured → no access
    return False


def _log_generation(report_type: str, plant: str, area: str, report_date: datetime.date, generated_by: int, export_format: str, row_count: int, duration_ms: int, status: str) -> None:
    try:
        with container.historical_service.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO historian_meta.report_gen_log
                    (report_type, plant, area, report_date, generated_by, export_format, row_count, duration_ms, ip_address, status)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    report_type,
                    plant,
                    area,
                    report_date,
                    generated_by,
                    export_format,
                    row_count,
                    duration_ms,
                    request.remote_addr,
                    status,
                ),
            )
            container.historical_service.connection.commit()
    except Exception as ex:
        logger.warning(f"Failed to write report_gen_log: {ex}")


@report_bp.route("/areas", methods=["GET"])
@token_required
def get_report_areas(current_user):
    """
    Returns the list of plant/area/server_progid combinations visible to this user.

    SOURCE OF TRUTH: historian_meta.plants_areas  (admin-managed via Admin → Area Access)
    NOT tag_master — tag_master plant/area columns are raw metadata; the admin panel
    controls what is visible through plants_areas + user_area_assignments.

    Access rules:
      - Admin (is_admin=True)  → all active areas
      - Non-admin              → only areas explicitly assigned in user_area_assignments
      - Non-admin with no assignments → empty list (sees nothing)
    """
    try:
        user_id  = current_user["user_id"]
        is_admin = current_user.get("is_admin", False)

        # get_user_area_access returns:
        #   None   → admin bypass (all areas)
        #   []     → no assignments (empty)
        #   [...]  → list of assigned {id, plant, area, plant_code, area_code, display_name, server_progid}
        assigned = container.area_access_service.get_user_area_access(user_id)

        if assigned is None or is_admin:
            # Admin: return all active areas from plants_areas
            all_areas = container.area_access_service.get_all_plants_areas(active_only=True)
            areas = [
                {
                    "plant":        a["plant"],
                    "area":         a["area"],
                    "server_progid": a.get("server_progid") or "Unknown",
                    "display_name": a.get("display_name", f"{a['plant']} / {a['area']}"),
                }
                for a in all_areas
            ]
        else:
            # Non-admin: return only their explicitly assigned areas
            areas = [
                {
                    "plant":        a["plant"],
                    "area":         a["area"],
                    "server_progid": a.get("server_progid") or "Unknown",
                    "display_name": a.get("display_name", f"{a['plant']} / {a['area']}"),
                }
                for a in assigned
            ]

        # Deduplicate (same plant/area from multiple assignments)
        seen = set()
        unique_areas = []
        for a in areas:
            key = (a["plant"], a["area"], a["server_progid"])
            if key not in seen:
                seen.add(key)
                unique_areas.append(a)

        unique_areas.sort(key=lambda x: (x["plant"], x["area"], x["server_progid"]))
        return jsonify({"areas": unique_areas}), 200

    except Exception as ex:
        logger.exception(f"Failed to fetch report areas: {ex}")
        return jsonify({"error": "Failed to fetch report areas"}), 500


@report_bp.route("/daily", methods=["GET"])
@token_required
def get_daily_report(current_user):
    started = time.time()

    if not container.historical_service.connection:
        return jsonify({"error": "Database not connected"}), 503

    date_str = request.args.get("date")
    plant = request.args.get("plant")
    area = request.args.get("area")
    source_id = request.args.get("source_id") or None
    page_str = request.args.get("page", "1")
    page_size_str = request.args.get("page_size", "20")

    if not date_str or not plant or not area:
        return jsonify({"error": "date, plant and area are required"}), 400

    try:
        report_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

    try:
        page = int(page_str)
        page_size = int(page_size_str)
        if page < 1:
            raise ValueError("page must be >= 1")
        if page_size < 1 or page_size > 500:
            raise ValueError("page_size must be between 1 and 500")
    except ValueError:
        return jsonify({"error": "Invalid pagination. page must be >= 1 and page_size must be between 1 and 500"}), 400

    # Support comma-separated plants and areas for multi-select
    plants = [p.strip() for p in plant.split(",") if p.strip()]
    areas = [a.strip() for a in area.split(",") if a.strip()]
    
    if not plants:
        return jsonify({"error": "At least one plant must be specified"}), 400
    if not areas:
        return jsonify({"error": "At least one area must be specified"}), 400
    
    # Check access for all areas
    for area_name in areas:
        # Use first plant for access check (legacy compatibility)
        if not _has_area_access(current_user["user_id"], current_user.get("is_admin", False), plants[0], area_name):
            return jsonify({"error": f"Access denied for plant/area: {plants[0]}/{area_name}"}), 403

    try:
        service = ReportService(container.historical_service.connection, container.config)
        data = service.build_daily_report(
            report_date,
            plants,  # Pass list of plants
            areas,  # Pass list of areas
            current_user.get("username", "system"),
            page=page,
            page_size=page_size,
            source_id=source_id,
        )

        duration_ms = int((time.time() - started) * 1000)
        _log_generation("DAILY", ",".join(plants), ",".join(areas), report_date, current_user["user_id"], "JSON", len(data.get("rows", [])), duration_ms, "SUCCESS")

        response = make_response(jsonify(data), 200)
        return _add_no_cache_headers(response)
    except Exception as ex:
        logger.exception(f"Daily report generation failed: {ex}")
        duration_ms = int((time.time() - started) * 1000)
        _log_generation("DAILY", ",".join(plants), ",".join(areas), report_date, current_user["user_id"], "JSON", 0, duration_ms, "FAILED")
        return jsonify({"error": "Failed to generate daily report"}), 500


@report_bp.route("/daily/export", methods=["GET"])
@token_required
def export_daily_report(current_user):
    started = time.time()

    if not container.historical_service.connection:
        return jsonify({"error": "Database not connected"}), 503

    date_str = request.args.get("date")
    plant = request.args.get("plant")
    area = request.args.get("area")
    source_id = request.args.get("source_id") or None
    # Optional: comma-separated tag_ids for filtered download
    tag_ids_raw = request.args.get("tag_ids") or None
    tag_ids = [t.strip() for t in tag_ids_raw.split(",") if t.strip()] if tag_ids_raw else None

    if not date_str or not plant or not area:
        return jsonify({"error": "date, plant and area are required"}), 400

    try:
        report_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

    plants = [p.strip() for p in plant.split(",") if p.strip()]
    areas = [a.strip() for a in area.split(",") if a.strip()]

    if not plants:
        return jsonify({"error": "At least one plant must be specified"}), 400
    if not areas:
        return jsonify({"error": "At least one area must be specified"}), 400

    for area_name in areas:
        if not _has_area_access(current_user["user_id"], current_user.get("is_admin", False), plants[0], area_name):
            return jsonify({"error": f"Access denied for plant/area: {plants[0]}/{area_name}"}), 403

    try:
        service = ReportService(container.historical_service.connection, container.config)
        data = service.build_daily_report(
            report_date, plants, areas,
            current_user.get("username", "system"),
            source_id=source_id,
        )
        xlsx = service.export_to_excel(data, tag_ids=tag_ids)

        duration_ms = int((time.time() - started) * 1000)
        _log_generation("DAILY", ",".join(plants), ",".join(areas), report_date, current_user["user_id"], "XLSX", len(data.get("rows", [])), duration_ms, "SUCCESS")

        safe_area = "_".join(areas).replace(" ", "_")
        safe_plant = "_".join(plants).replace(" ", "_")
        filename = f"Daily_Report_{safe_area}_{safe_plant}_{report_date.isoformat()}.xlsx"
        return send_file(
            xlsx,
            as_attachment=True,
            download_name=filename,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as ex:
        logger.exception(f"Daily report export failed: {ex}")
        duration_ms = int((time.time() - started) * 1000)
        _log_generation("DAILY", plant, ",".join(areas), report_date, current_user["user_id"], "XLSX", 0, duration_ms, "FAILED")
        return jsonify({"error": "Failed to export daily report"}), 500


# ------------------------------------------------------------------ #
# Shift Report Endpoints                                               #
# ------------------------------------------------------------------ #

@report_bp.route("/shifts", methods=["GET"])
@token_required
def get_active_shifts(current_user):
    """Return all active regular shifts for the shift selector UI."""
    if not container.historical_service.connection:
        return jsonify({"error": "Database not connected"}), 503

    try:
        with container.historical_service.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT shift_code, shift_name,
                       start_time::text AS start_time,
                       end_time::text   AS end_time
                FROM historian_meta.shifts
                WHERE is_active = TRUE
                  AND shift_type = 'regular'
                ORDER BY start_time
                """
            )
            rows = cursor.fetchall()

        shifts = []
        for row in rows:
            if isinstance(row, dict):
                shifts.append({
                    "shift_code": row["shift_code"],
                    "shift_name": row["shift_name"],
                    "start_time": str(row["start_time"]),
                    "end_time": str(row["end_time"]),
                })
            else:
                shifts.append({
                    "shift_code": row[0],
                    "shift_name": row[1],
                    "start_time": str(row[2]),
                    "end_time": str(row[3]),
                })
        return jsonify({"shifts": shifts}), 200
    except Exception as ex:
        logger.exception(f"Failed to fetch shifts: {ex}")
        return jsonify({"error": "Failed to fetch shifts"}), 500


@report_bp.route("/shift", methods=["GET"])
@token_required
def get_shift_report(current_user):
    started = time.time()

    if not container.historical_service.connection:
        return jsonify({"error": "Database not connected"}), 503

    date_str = request.args.get("date")
    plant = request.args.get("plant")
    area = request.args.get("area")
    shift_code = (request.args.get("shift_code") or "").upper().strip()
    source_id = request.args.get("source_id") or None
    page_str = request.args.get("page", "1")
    page_size_str = request.args.get("page_size", "20")

    if not date_str or not plant or not area or not shift_code:
        return jsonify({"error": "date, plant, area and shift_code are required"}), 400

    try:
        report_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

    try:
        page = int(page_str)
        page_size = int(page_size_str)
        if page < 1:
            raise ValueError("page must be >= 1")
        if page_size < 1 or page_size > 500:
            raise ValueError("page_size must be between 1 and 500")
    except ValueError:
        return jsonify({"error": "Invalid pagination. page must be >= 1 and page_size must be between 1 and 500"}), 400

    if not _has_area_access(current_user["user_id"], current_user.get("is_admin", False), plant, area):
        return jsonify({"error": "Access denied for this plant/area"}), 403

    try:
        service = ReportService(container.historical_service.connection, container.config)
        data = service.build_shift_report(
            report_date, shift_code, plant, area,
            current_user.get("username", "system"),
            page=page, page_size=page_size,
            source_id=source_id,
        )
        duration_ms = int((time.time() - started) * 1000)
        _log_generation("SHIFT", plant, area, report_date, current_user["user_id"], "JSON", len(data.get("rows", [])), duration_ms, "SUCCESS")
        response = make_response(jsonify(data), 200)
        return _add_no_cache_headers(response)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as ex:
        logger.exception(f"Shift report generation failed: {ex}")
        duration_ms = int((time.time() - started) * 1000)
        _log_generation("SHIFT", plant, area, report_date, current_user["user_id"], "JSON", 0, duration_ms, "FAILED")
        return jsonify({"error": "Failed to generate shift report"}), 500


@report_bp.route("/shift/export", methods=["GET"])
@token_required
def export_shift_report(current_user):
    started = time.time()

    if not container.historical_service.connection:
        return jsonify({"error": "Database not connected"}), 503

    date_str = request.args.get("date")
    plant = request.args.get("plant")
    area = request.args.get("area")
    shift_code = (request.args.get("shift_code") or "").upper().strip()
    source_id = request.args.get("source_id") or None
    tag_ids_raw = request.args.get("tag_ids") or None
    tag_ids = [t.strip() for t in tag_ids_raw.split(",") if t.strip()] if tag_ids_raw else None

    if not date_str or not plant or not area or not shift_code:
        return jsonify({"error": "date, plant, area and shift_code are required"}), 400

    try:
        report_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

    if not _has_area_access(current_user["user_id"], current_user.get("is_admin", False), plant, area):
        return jsonify({"error": "Access denied for this plant/area"}), 403

    try:
        service = ReportService(container.historical_service.connection, container.config)
        data = service.build_shift_report(
            report_date, shift_code, plant, area,
            current_user.get("username", "system"),
            source_id=source_id,
        )
        xlsx = service.export_shift_to_excel(data, tag_ids=tag_ids)

        duration_ms = int((time.time() - started) * 1000)
        _log_generation("SHIFT", plant, area, report_date, current_user["user_id"], "XLSX", len(data.get("rows", [])), duration_ms, "SUCCESS")

        safe_area = area.replace(" ", "_")
        safe_plant = plant.replace(" ", "_") if isinstance(plant, str) else "_".join(plant).replace(" ", "_")
        filename = f"Shift_Report_{safe_area}_{safe_plant}_{report_date.isoformat()}_{shift_code}.xlsx"
        return send_file(
            xlsx,
            as_attachment=True,
            download_name=filename,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as ex:
        logger.exception(f"Shift report export failed: {ex}")
        duration_ms = int((time.time() - started) * 1000)
        _log_generation("SHIFT", plant, area, report_date, current_user["user_id"], "XLSX", 0, duration_ms, "FAILED")
        return jsonify({"error": "Failed to export shift report"}), 500


# ------------------------------------------------------------------ #
# Monthly Report Endpoints                                             #
# ------------------------------------------------------------------ #

def _validate_monthly_date_range(from_date, to_date) -> None:
    if from_date > to_date:
        raise ValueError("from_date must be less than or equal to to_date")

    day_count = (to_date - from_date).days + 1
    if day_count < 1 or day_count > 31:
        raise ValueError("Date range must be between 1 and 31 days (inclusive)")


@report_bp.route("/monthly", methods=["GET"])
@token_required
def get_monthly_report(current_user):
    started = time.time()

    if not container.historical_service.connection:
        return jsonify({"error": "Database not connected"}), 503

    from_date_str = request.args.get("from_date")
    to_date_str = request.args.get("to_date")
    plant = request.args.get("plant")
    area = request.args.get("area")
    source_id = request.args.get("source_id") or None
    page_str = request.args.get("page", "1")
    page_size_str = request.args.get("page_size", "20")

    if not from_date_str or not to_date_str or not plant or not area:
        return jsonify({"error": "from_date, to_date, plant and area are required"}), 400

    try:
        from_date = datetime.strptime(from_date_str, "%Y-%m-%d").date()
        to_date = datetime.strptime(to_date_str, "%Y-%m-%d").date()
        _validate_monthly_date_range(from_date, to_date)
    except ValueError as ve:
        return jsonify({"error": str(ve) if str(ve) else "Invalid date format. Use YYYY-MM-DD"}), 400

    try:
        page = int(page_str)
        page_size = int(page_size_str)
        if page < 1:
            raise ValueError("page must be >= 1")
        if page_size < 1 or page_size > 500:
            raise ValueError("page_size must be between 1 and 500")
    except ValueError:
        return jsonify({"error": "Invalid pagination. page must be >= 1 and page_size must be between 1 and 500"}), 400

    if not _has_area_access(current_user["user_id"], current_user.get("is_admin", False), plant, area):
        return jsonify({"error": "Access denied for this plant/area"}), 403

    try:
        service = ReportService(container.historical_service.connection, container.config)
        data = service.build_monthly_report(
            from_date,
            to_date,
            plant,
            area,
            current_user.get("username", "system"),
            page=page,
            page_size=page_size,
            source_id=source_id,
        )

        duration_ms = int((time.time() - started) * 1000)
        _log_generation("MONTHLY", plant, area, from_date, current_user["user_id"], "JSON", len(data.get("rows", [])), duration_ms, "SUCCESS")
        response = make_response(jsonify(data), 200)
        return _add_no_cache_headers(response)
    except Exception as ex:
        logger.exception(f"Monthly report generation failed: {ex}")
        duration_ms = int((time.time() - started) * 1000)
        _log_generation("MONTHLY", plant, area, from_date, current_user["user_id"], "JSON", 0, duration_ms, "FAILED")
        return jsonify({"error": "Failed to generate monthly report"}), 500


@report_bp.route("/monthly/export", methods=["GET"])
@token_required
def export_monthly_report(current_user):
    started = time.time()

    if not container.historical_service.connection:
        return jsonify({"error": "Database not connected"}), 503

    from_date_str = request.args.get("from_date")
    to_date_str = request.args.get("to_date")
    plant = request.args.get("plant")
    area = request.args.get("area")
    source_id = request.args.get("source_id") or None
    tag_ids_raw = request.args.get("tag_ids") or None
    tag_ids = [t.strip() for t in tag_ids_raw.split(",") if t.strip()] if tag_ids_raw else None

    if not from_date_str or not to_date_str or not plant or not area:
        return jsonify({"error": "from_date, to_date, plant and area are required"}), 400

    try:
        from_date = datetime.strptime(from_date_str, "%Y-%m-%d").date()
        to_date = datetime.strptime(to_date_str, "%Y-%m-%d").date()
        _validate_monthly_date_range(from_date, to_date)
    except ValueError as ve:
        return jsonify({"error": str(ve) if str(ve) else "Invalid date format. Use YYYY-MM-DD"}), 400

    if not _has_area_access(current_user["user_id"], current_user.get("is_admin", False), plant, area):
        return jsonify({"error": "Access denied for this plant/area"}), 403

    try:
        service = ReportService(container.historical_service.connection, container.config)
        data = service.build_monthly_report(
            from_date, to_date, plant, area,
            current_user.get("username", "system"),
            source_id=source_id,
        )
        xlsx = service.export_monthly_to_excel(data, tag_ids=tag_ids)

        duration_ms = int((time.time() - started) * 1000)
        _log_generation("MONTHLY", plant, area, from_date, current_user["user_id"], "XLSX", len(data.get("rows", [])), duration_ms, "SUCCESS")

        safe_area = area.replace(" ", "_")
        safe_plant = plant.replace(" ", "_") if isinstance(plant, str) else "_".join(plant).replace(" ", "_")
        filename = f"Monthly_Report_{safe_area}_{safe_plant}_{from_date.isoformat()}_to_{to_date.isoformat()}.xlsx"
        return send_file(
            xlsx,
            as_attachment=True,
            download_name=filename,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as ex:
        logger.exception(f"Monthly report export failed: {ex}")
        duration_ms = int((time.time() - started) * 1000)
        _log_generation("MONTHLY", plant, area, from_date, current_user["user_id"], "XLSX", 0, duration_ms, "FAILED")
        return jsonify({"error": "Failed to export monthly report"}), 500
