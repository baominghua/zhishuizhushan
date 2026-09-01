from __future__ import annotations

from typing import Any


PLATFORM_MYSQL_TABLES = [
    "v2_extension_records",
    "forest_blocks",
    "forest_block_geometries",
    "forest_block_versions",
    "forest_subcompartments",
    "forest_subcompartment_geometries",
    "forest_subcompartment_versions",
    "resource_surveys",
    "resource_snapshots",
    "resource_snapshot_versions",
    "attachments",
    "attachment_links",
    "attachment_events",
    "forest_rights",
    "forest_right_versions",
    "forest_right_block_links",
    "map_layers",
    "map_layer_block_links",
    "map_layer_right_links",
    "business_records",
    "business_record_block_links",
    "business_record_right_links",
    "business_record_links",
    "business_record_attributes",
    "harvest_quotas",
    "harvest_applications",
    "harvest_application_block_links",
    "harvest_application_right_links",
    "harvest_events",
    "harvest_batches",
    "safety_alerts",
    "safety_events",
    "safety_event_block_links",
    "safety_event_timeline",
    "labor_workers",
    "labor_teams",
    "labor_team_members",
    "labor_jobs",
    "labor_job_block_links",
    "labor_attendance",
    "labor_job_timeline",
    "iot_devices",
    "iot_device_block_links",
    "iot_device_maintenance",
    "drone_missions",
    "drone_mission_block_links",
    "drone_mission_timeline",
    "ai_findings",
    "ai_finding_block_links",
    "ai_finding_timeline",
    "ai_model_assets",
    "ai_inference_runs",
    "ai_inference_run_block_links",
    "mobile_sync_operations",
    "mobile_evidence",
    "mobile_tracks",
    "mobile_upload_sessions",
    "operations_notification_reads",
    "dictionary_types",
    "dictionary_items",
    "admin_roles",
    "admin_role_permissions",
    "admin_role_menu_modules",
    "admin_users",
    "admin_organizations",
    "admin_user_roles",
    "admin_user_credentials",
    "admin_sessions",
    "platform_runtime_config",
    "import_batches",
    "import_batch_block_links",
    "import_batch_right_links",
    "import_batch_scene_links",
    "import_batch_events",
    "forest_block_scene_links",
    "remote_sensing_scenes",
    "remote_sensing_scene_geometries",
    "remote_sensing_scene_events",
    "remote_sensing_tasks",
    "remote_sensing_task_events",
]

REMOTE_SENSING_MYSQL_TABLES = (
    "remote_sensing_scenes",
    "remote_sensing_scene_geometries",
    "remote_sensing_scene_events",
    "remote_sensing_tasks",
    "remote_sensing_task_events",
)
PLATFORM_CORE_MYSQL_TABLES = tuple(
    table for table in PLATFORM_MYSQL_TABLES if table not in REMOTE_SENSING_MYSQL_TABLES
)

MYSQL_INDEX_UPGRADES = {
    (
        "dictionary_items",
        "uq_dictionary_item_code",
    ): (
        "ALTER TABLE dictionary_items ADD UNIQUE KEY "
        "uq_dictionary_item_code (dictionary_type_id, level_code, item_code)"
    ),
    (
        "forest_blocks",
        "idx_forest_blocks_operation",
    ): "ALTER TABLE forest_blocks ADD INDEX idx_forest_blocks_operation (base_type, operation_type)",
    (
        "forest_blocks",
        "idx_forest_blocks_town_active_updated",
    ): "ALTER TABLE forest_blocks ADD INDEX idx_forest_blocks_town_active_updated (town_code, deleted_at, updated_at)",
    (
        "forest_blocks",
        "idx_forest_blocks_town_active_area",
    ): "ALTER TABLE forest_blocks ADD INDEX idx_forest_blocks_town_active_area (deleted_at, town_code, area_mu)",
    (
        "forest_blocks",
        "idx_forest_blocks_operation_active",
    ): "ALTER TABLE forest_blocks ADD INDEX idx_forest_blocks_operation_active (deleted_at, base_type, operation_type)",
}

MYSQL_COLUMN_UPGRADES = {
    (
        "mobile_evidence",
        "deleted_at",
    ): "ALTER TABLE mobile_evidence ADD COLUMN deleted_at DATETIME(6) NULL AFTER created_at",
    (
        "import_batch_block_links",
        "target_json",
    ): "ALTER TABLE import_batch_block_links ADD COLUMN target_json JSON NULL",
    (
        "import_batch_right_links",
        "target_json",
    ): "ALTER TABLE import_batch_right_links ADD COLUMN target_json JSON NULL",
    (
        "safety_alerts",
        "review_json",
    ): "ALTER TABLE safety_alerts ADD COLUMN review_json JSON NULL AFTER raw_payload",
}

MYSQL_NULLABLE_COLUMN_UPGRADES = {
    ("drone_missions", "drone_device_id"): (
        "ALTER TABLE drone_missions MODIFY COLUMN drone_device_id CHAR(36) NULL"
    ),
    ("drone_missions", "device_code"): (
        "ALTER TABLE drone_missions MODIFY COLUMN device_code VARCHAR(128) NULL"
    ),
    ("drone_missions", "device_name"): (
        "ALTER TABLE drone_missions MODIFY COLUMN device_name VARCHAR(255) NULL"
    ),
    ("drone_missions", "planned_start_at"): (
        "ALTER TABLE drone_missions MODIFY COLUMN planned_start_at DATETIME(6) NULL"
    ),
    ("drone_missions", "planned_end_at"): (
        "ALTER TABLE drone_missions MODIFY COLUMN planned_end_at DATETIME(6) NULL"
    ),
}


def mysql_index_upgrade_statements(existing_indexes: set[tuple[str, str]]) -> list[str]:
    return [
        statement
        for (table_name, index_name), statement in MYSQL_INDEX_UPGRADES.items()
        if (table_name, index_name) not in existing_indexes
    ]


def mysql_column_upgrade_statements(existing_columns: set[tuple[str, str]]) -> list[str]:
    return [
        statement
        for (table_name, column_name), statement in MYSQL_COLUMN_UPGRADES.items()
        if (table_name, column_name) not in existing_columns
    ]


def mysql_nullable_column_upgrade_statements(
    column_nullability: dict[tuple[str, str], str],
) -> list[str]:
    return [
        statement
        for key, statement in MYSQL_NULLABLE_COLUMN_UPGRADES.items()
        if str(column_nullability.get(key) or "").upper() == "NO"
    ]


def apply_mysql_schema_upgrades(cur: Any) -> None:
    cur.execute(
        "SELECT table_name, index_name FROM information_schema.statistics "
        "WHERE table_schema = DATABASE()"
    )
    existing_indexes = {(str(row[0]), str(row[1])) for row in cur.fetchall()}
    cur.execute(
        "SELECT is_nullable, column_default FROM information_schema.columns "
        "WHERE table_schema = DATABASE() "
        "AND table_name = 'dictionary_items' "
        "AND column_name = 'level_code'"
    )
    level_columns = cur.fetchall()
    level_column = level_columns[0] if level_columns else None
    if level_column and (
        str(level_column[0]).upper() != "NO"
        or str(level_column[1] or "") != ""
    ):
        cur.execute("UPDATE dictionary_items SET level_code = '' WHERE level_code IS NULL")
        cur.execute(
            "ALTER TABLE dictionary_items MODIFY COLUMN "
            "level_code VARCHAR(40) NOT NULL DEFAULT ''"
        )
    if ("dictionary_items", "uq_dictionary_item_code") in existing_indexes:
        cur.execute(
            "SELECT column_name FROM information_schema.statistics "
            "WHERE table_schema = DATABASE() "
            "AND table_name = 'dictionary_items' "
            "AND index_name = 'uq_dictionary_item_code' "
            "ORDER BY seq_in_index"
        )
        columns = tuple(str(row[0]) for row in cur.fetchall())
        if columns != ("dictionary_type_id", "level_code", "item_code"):
            cur.execute(
                "ALTER TABLE dictionary_items "
                "DROP INDEX uq_dictionary_item_code, "
                "ADD UNIQUE KEY uq_dictionary_item_code "
                "(dictionary_type_id, level_code, item_code)"
            )
    for statement in mysql_index_upgrade_statements(existing_indexes):
        cur.execute(statement)
    cur.execute(
        "SELECT table_name, column_name, is_nullable FROM information_schema.columns "
        "WHERE table_schema = DATABASE()"
    )
    column_rows = cur.fetchall()
    existing_columns = {(str(row[0]), str(row[1])) for row in column_rows}
    for statement in mysql_column_upgrade_statements(existing_columns):
        cur.execute(statement)
    column_nullability = {
        (str(row[0]), str(row[1])): str(row[2]) for row in column_rows
    }
    for statement in mysql_nullable_column_upgrade_statements(column_nullability):
        cur.execute(statement)


def mysql_schema_statements() -> list[str]:
    table_options = "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci"
    return [
        f"""
        CREATE TABLE IF NOT EXISTS v2_extension_records (
            collection_key VARCHAR(64) NOT NULL,
            id CHAR(36) NOT NULL,
            area_code VARCHAR(32),
            version_no INT UNSIGNED NOT NULL DEFAULT 1,
            idempotency_key VARCHAR(191),
            record_json JSON NOT NULL,
            created_at DATETIME(6) NOT NULL,
            updated_at DATETIME(6) NOT NULL,
            deleted_at DATETIME(6),
            PRIMARY KEY (collection_key,id),
            UNIQUE KEY uq_v2_extension_idempotency (collection_key,idempotency_key),
            KEY idx_v2_extension_area (collection_key,area_code,deleted_at),
            KEY idx_v2_extension_updated (collection_key,updated_at),
            KEY idx_v2_extension_deleted (deleted_at)
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS forest_blocks (
            id CHAR(36) PRIMARY KEY,
            block_code VARCHAR(128) NOT NULL,
            name VARCHAR(255) NOT NULL,
            county_code VARCHAR(32),
            county_name VARCHAR(128),
            town_code VARCHAR(32),
            town_name VARCHAR(128),
            village_code VARCHAR(32),
            village_name VARCHAR(128),
            base_type VARCHAR(64),
            operation_type VARCHAR(64),
            forest_type VARCHAR(64),
            area_mu DECIMAL(18,4),
            slope_degree DECIMAL(8,3),
            ownership_status VARCHAR(64),
            management_status VARCHAR(64),
            quality_grade VARCHAR(32),
            health_status VARCHAR(64),
            risk_level VARCHAR(32),
            bamboo_age VARCHAR(64),
            avg_dbh_cm DECIMAL(10,3),
            avg_height_m DECIMAL(10,3),
            standing_density DECIMAL(18,4),
            carbon_estimate_tco2e DECIMAL(18,4),
            yield_estimate JSON,
            tags JSON,
            properties JSON,
            source_batch_id CHAR(36),
            created_at DATETIME(6) NOT NULL,
            updated_at DATETIME(6) NOT NULL,
            deleted_at DATETIME(6),
            UNIQUE KEY uq_forest_blocks_code (block_code),
            KEY idx_forest_blocks_county (county_code),
            KEY idx_forest_blocks_town (town_code),
            KEY idx_forest_blocks_town_active_updated (town_code, deleted_at, updated_at),
            KEY idx_forest_blocks_town_active_area (deleted_at, town_code, area_mu),
            KEY idx_forest_blocks_village (village_code),
            KEY idx_forest_blocks_operation (base_type, operation_type),
            KEY idx_forest_blocks_operation_active (deleted_at, base_type, operation_type),
            KEY idx_forest_blocks_management (management_status),
            KEY idx_forest_blocks_quality (quality_grade),
            KEY idx_forest_blocks_health (health_status),
            KEY idx_forest_blocks_risk (risk_level),
            KEY idx_forest_blocks_updated (updated_at),
            KEY idx_forest_blocks_deleted (deleted_at)
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS forest_block_geometries (
            forest_block_id CHAR(36) PRIMARY KEY,
            geometry GEOMETRY NOT NULL SRID 4326,
            centroid POINT NOT NULL SRID 4326,
            min_longitude DECIMAL(11,8) NOT NULL,
            min_latitude DECIMAL(11,8) NOT NULL,
            max_longitude DECIMAL(11,8) NOT NULL,
            max_latitude DECIMAL(11,8) NOT NULL,
            vertex_count INT UNSIGNED NOT NULL DEFAULT 0,
            updated_at DATETIME(6) NOT NULL,
            SPATIAL INDEX idx_forest_block_geometry (geometry),
            SPATIAL INDEX idx_forest_block_centroid (centroid),
            KEY idx_forest_block_bbox (min_longitude, min_latitude, max_longitude, max_latitude),
            CONSTRAINT fk_forest_block_geometry_block
                FOREIGN KEY (forest_block_id) REFERENCES forest_blocks(id) ON DELETE CASCADE
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS forest_block_versions (
            id CHAR(36) PRIMARY KEY,
            forest_block_id CHAR(36) NOT NULL,
            change_type VARCHAR(32) NOT NULL,
            snapshot JSON NOT NULL,
            source_version_id CHAR(36),
            created_by VARCHAR(128),
            created_at DATETIME(6) NOT NULL,
            KEY idx_forest_block_versions_block_time (forest_block_id, created_at),
            CONSTRAINT fk_forest_block_version_block
                FOREIGN KEY (forest_block_id) REFERENCES forest_blocks(id) ON DELETE CASCADE
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS forest_subcompartments (
            id CHAR(36) PRIMARY KEY,
            subcompartment_code VARCHAR(128) NOT NULL,
            name VARCHAR(255) NOT NULL,
            forest_block_id CHAR(36) NOT NULL,
            area_mu DECIMAL(18,4),
            land_category VARCHAR(64),
            forest_category VARCHAR(64),
            origin VARCHAR(64),
            age_group VARCHAR(64),
            bamboo_species VARCHAR(128),
            slope_degree DECIMAL(8,3),
            aspect VARCHAR(64),
            elevation_m DECIMAL(10,3),
            quality_grade VARCHAR(32),
            health_status VARCHAR(64),
            risk_level VARCHAR(32),
            management_status VARCHAR(64),
            tags JSON,
            properties JSON,
            source_batch_id CHAR(36),
            version INT UNSIGNED NOT NULL DEFAULT 1,
            created_by VARCHAR(128),
            created_at DATETIME(6) NOT NULL,
            updated_at DATETIME(6) NOT NULL,
            deleted_at DATETIME(6),
            UNIQUE KEY uq_forest_subcompartments_code (subcompartment_code),
            KEY idx_forest_subcompartments_block (forest_block_id),
            KEY idx_forest_subcompartments_block_active (forest_block_id, deleted_at),
            KEY idx_forest_subcompartments_management (management_status),
            KEY idx_forest_subcompartments_risk (risk_level),
            KEY idx_forest_subcompartments_updated (updated_at),
            KEY idx_forest_subcompartments_deleted (deleted_at),
            CONSTRAINT fk_forest_subcompartment_block
                FOREIGN KEY (forest_block_id) REFERENCES forest_blocks(id) ON DELETE RESTRICT
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS forest_subcompartment_geometries (
            forest_subcompartment_id CHAR(36) PRIMARY KEY,
            geometry GEOMETRY NOT NULL SRID 4326,
            centroid POINT NOT NULL SRID 4326,
            min_longitude DECIMAL(11,8) NOT NULL,
            min_latitude DECIMAL(11,8) NOT NULL,
            max_longitude DECIMAL(11,8) NOT NULL,
            max_latitude DECIMAL(11,8) NOT NULL,
            vertex_count INT UNSIGNED NOT NULL DEFAULT 0,
            updated_at DATETIME(6) NOT NULL,
            SPATIAL INDEX idx_forest_subcompartment_geometry (geometry),
            SPATIAL INDEX idx_forest_subcompartment_centroid (centroid),
            KEY idx_forest_subcompartment_bbox (
                min_longitude, min_latitude, max_longitude, max_latitude
            ),
            CONSTRAINT fk_forest_subcompartment_geometry_record
                FOREIGN KEY (forest_subcompartment_id)
                REFERENCES forest_subcompartments(id) ON DELETE CASCADE
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS forest_subcompartment_versions (
            id CHAR(36) PRIMARY KEY,
            forest_subcompartment_id CHAR(36) NOT NULL,
            change_type VARCHAR(32) NOT NULL,
            version INT UNSIGNED NOT NULL,
            snapshot JSON NOT NULL,
            created_by VARCHAR(128),
            created_at DATETIME(6) NOT NULL,
            KEY idx_forest_subcompartment_versions_record_time (
                forest_subcompartment_id, created_at
            ),
            CONSTRAINT fk_forest_subcompartment_version_record
                FOREIGN KEY (forest_subcompartment_id)
                REFERENCES forest_subcompartments(id) ON DELETE CASCADE
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS resource_surveys (
            id CHAR(36) PRIMARY KEY,
            survey_no VARCHAR(128) NOT NULL,
            name VARCHAR(255) NOT NULL,
            survey_type VARCHAR(64) NOT NULL,
            survey_date DATE NOT NULL,
            status VARCHAR(32) NOT NULL,
            organization VARCHAR(255),
            surveyor VARCHAR(255),
            source_type VARCHAR(64),
            method VARCHAR(128),
            notes TEXT,
            properties JSON,
            version INT UNSIGNED NOT NULL DEFAULT 1,
            created_by VARCHAR(128),
            created_at DATETIME(6) NOT NULL,
            updated_at DATETIME(6) NOT NULL,
            completed_at DATETIME(6),
            deleted_at DATETIME(6),
            UNIQUE KEY uq_resource_surveys_no (survey_no),
            KEY idx_resource_surveys_date_status (survey_date, status),
            KEY idx_resource_surveys_deleted (deleted_at)
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS resource_snapshots (
            id CHAR(36) PRIMARY KEY,
            resource_survey_id CHAR(36) NOT NULL,
            forest_subcompartment_id CHAR(36) NOT NULL,
            previous_snapshot_id CHAR(36),
            sampled_at DATETIME(6),
            area_mu DECIMAL(18,4),
            bamboo_species VARCHAR(128),
            origin VARCHAR(64),
            age_group VARCHAR(64),
            bamboo_density_per_mu DECIMAL(18,4),
            avg_dbh_cm DECIMAL(10,3),
            avg_height_m DECIMAL(10,3),
            standing_volume_m3 DECIMAL(18,4),
            biomass_t DECIMAL(18,4),
            carbon_estimate_tco2e DECIMAL(18,4),
            quality_grade VARCHAR(32),
            health_status VARCHAR(64),
            risk_level VARCHAR(32),
            sample_plot_count INT UNSIGNED,
            evidence_urls JSON,
            properties JSON,
            version INT UNSIGNED NOT NULL DEFAULT 1,
            created_by VARCHAR(128),
            created_at DATETIME(6) NOT NULL,
            updated_at DATETIME(6) NOT NULL,
            deleted_at DATETIME(6),
            UNIQUE KEY uq_resource_snapshot_survey_subcompartment (
                resource_survey_id, forest_subcompartment_id
            ),
            KEY idx_resource_snapshots_subcompartment_time (
                forest_subcompartment_id, sampled_at
            ),
            KEY idx_resource_snapshots_deleted (deleted_at),
            CONSTRAINT fk_resource_snapshot_survey
                FOREIGN KEY (resource_survey_id) REFERENCES resource_surveys(id) ON DELETE CASCADE,
            CONSTRAINT fk_resource_snapshot_subcompartment
                FOREIGN KEY (forest_subcompartment_id)
                REFERENCES forest_subcompartments(id) ON DELETE RESTRICT,
            CONSTRAINT fk_resource_snapshot_previous
                FOREIGN KEY (previous_snapshot_id) REFERENCES resource_snapshots(id) ON DELETE SET NULL
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS resource_snapshot_versions (
            id CHAR(36) PRIMARY KEY,
            resource_snapshot_id CHAR(36) NOT NULL,
            change_type VARCHAR(32) NOT NULL,
            version INT UNSIGNED NOT NULL,
            snapshot JSON NOT NULL,
            created_by VARCHAR(128),
            created_at DATETIME(6) NOT NULL,
            KEY idx_resource_snapshot_versions_record_time (
                resource_snapshot_id, created_at
            ),
            CONSTRAINT fk_resource_snapshot_version_record
                FOREIGN KEY (resource_snapshot_id)
                REFERENCES resource_snapshots(id) ON DELETE CASCADE
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS attachments (
            id CHAR(36) PRIMARY KEY,
            original_name VARCHAR(512) NOT NULL,
            stored_name VARCHAR(160) NOT NULL,
            object_key VARCHAR(512) NOT NULL,
            content_type VARCHAR(255),
            size_bytes BIGINT UNSIGNED NOT NULL,
            sha256 CHAR(64) NOT NULL,
            category VARCHAR(64) NOT NULL DEFAULT 'document',
            description TEXT,
            status VARCHAR(32) NOT NULL DEFAULT 'active',
            properties JSON,
            version INT UNSIGNED NOT NULL DEFAULT 1,
            uploaded_by VARCHAR(128),
            created_at DATETIME(6) NOT NULL,
            updated_at DATETIME(6) NOT NULL,
            deleted_at DATETIME(6),
            KEY idx_attachments_hash (sha256),
            KEY idx_attachments_category_status (category, status, deleted_at),
            KEY idx_attachments_created (created_at)
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS attachment_links (
            id CHAR(36) PRIMARY KEY,
            attachment_id CHAR(36) NOT NULL,
            entity_type VARCHAR(80) NOT NULL,
            entity_id VARCHAR(160) NOT NULL,
            relation_type VARCHAR(64) NOT NULL DEFAULT 'evidence',
            created_by VARCHAR(128),
            created_at DATETIME(6) NOT NULL,
            deleted_at DATETIME(6),
            UNIQUE KEY uq_attachment_link_active (attachment_id, entity_type, entity_id, relation_type),
            KEY idx_attachment_links_entity (entity_type, entity_id, deleted_at),
            CONSTRAINT fk_attachment_link_attachment
                FOREIGN KEY (attachment_id) REFERENCES attachments(id) ON DELETE RESTRICT
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS attachment_events (
            id CHAR(36) PRIMARY KEY,
            attachment_id CHAR(36) NOT NULL,
            action VARCHAR(64) NOT NULL,
            actor VARCHAR(128),
            detail JSON,
            created_at DATETIME(6) NOT NULL,
            KEY idx_attachment_events_record_time (attachment_id, created_at),
            CONSTRAINT fk_attachment_event_attachment
                FOREIGN KEY (attachment_id) REFERENCES attachments(id) ON DELETE CASCADE
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS forest_rights (
            id CHAR(36) PRIMARY KEY,
            archive_code VARCHAR(160) NOT NULL,
            certificate_no VARCHAR(160),
            holder VARCHAR(255) NOT NULL,
            certificate_type VARCHAR(64),
            right_type VARCHAR(128),
            ownership_type VARCHAR(64),
            right_start DATE,
            right_end DATE,
            contract_no VARCHAR(160),
            circulation_status VARCHAR(64),
            archive_status VARCHAR(64),
            registrar VARCHAR(128),
            missing_items TEXT,
            area_mu DECIMAL(18,4),
            county_code VARCHAR(32),
            county_name VARCHAR(128),
            town_code VARCHAR(32),
            town_name VARCHAR(128),
            village_code VARCHAR(32),
            village_name VARCHAR(128),
            documents JSON,
            properties JSON,
            created_at DATETIME(6) NOT NULL,
            updated_at DATETIME(6) NOT NULL,
            deleted_at DATETIME(6),
            UNIQUE KEY uq_forest_rights_archive_code (archive_code),
            KEY idx_forest_rights_certificate (certificate_no),
            KEY idx_forest_rights_holder (holder),
            KEY idx_forest_rights_status (archive_status),
            KEY idx_forest_rights_county (county_code),
            KEY idx_forest_rights_deleted (deleted_at)
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS forest_right_versions (
            id CHAR(36) PRIMARY KEY,
            forest_right_id CHAR(36) NOT NULL,
            change_type VARCHAR(32) NOT NULL,
            snapshot JSON NOT NULL,
            source_version_id CHAR(36),
            created_by VARCHAR(128),
            created_at DATETIME(6) NOT NULL,
            KEY idx_forest_right_versions_right_time (forest_right_id, created_at),
            CONSTRAINT fk_forest_right_version_right
                FOREIGN KEY (forest_right_id) REFERENCES forest_rights(id) ON DELETE CASCADE
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS forest_right_block_links (
            forest_right_id CHAR(36) NOT NULL,
            forest_block_id CHAR(36) NOT NULL,
            link_status VARCHAR(32) NOT NULL DEFAULT 'active',
            linked_at DATETIME(6) NOT NULL,
            UNIQUE KEY uq_forest_right_block (forest_right_id, forest_block_id),
            KEY idx_forest_right_block_block (forest_block_id),
            CONSTRAINT fk_forest_right_block_right
                FOREIGN KEY (forest_right_id) REFERENCES forest_rights(id) ON DELETE CASCADE,
            CONSTRAINT fk_forest_right_block_block
                FOREIGN KEY (forest_block_id) REFERENCES forest_blocks(id) ON DELETE CASCADE
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS map_layers (
            id CHAR(36) PRIMARY KEY,
            record_code VARCHAR(128) NOT NULL,
            name VARCHAR(255) NOT NULL,
            status VARCHAR(64),
            layer_type VARCHAR(64),
            data_source VARCHAR(255),
            style JSON,
            z_index INT,
            visible_on_dashboard BOOLEAN NOT NULL DEFAULT TRUE,
            properties JSON,
            created_at DATETIME(6) NOT NULL,
            updated_at DATETIME(6) NOT NULL,
            deleted_at DATETIME(6),
            UNIQUE KEY uq_map_layers_code (record_code),
            KEY idx_map_layers_status_type (status, layer_type),
            KEY idx_map_layers_dashboard (visible_on_dashboard, z_index),
            KEY idx_map_layers_deleted (deleted_at)
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS map_layer_block_links (
            map_layer_id CHAR(36) NOT NULL,
            forest_block_id CHAR(36) NOT NULL,
            UNIQUE KEY uq_map_layer_block (map_layer_id, forest_block_id),
            KEY idx_map_layer_block_block (forest_block_id),
            CONSTRAINT fk_map_layer_block_layer FOREIGN KEY (map_layer_id) REFERENCES map_layers(id) ON DELETE CASCADE,
            CONSTRAINT fk_map_layer_block_block FOREIGN KEY (forest_block_id) REFERENCES forest_blocks(id) ON DELETE CASCADE
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS map_layer_right_links (
            map_layer_id CHAR(36) NOT NULL,
            forest_right_id CHAR(36) NOT NULL,
            UNIQUE KEY uq_map_layer_right (map_layer_id, forest_right_id),
            KEY idx_map_layer_right_right (forest_right_id),
            CONSTRAINT fk_map_layer_right_layer FOREIGN KEY (map_layer_id) REFERENCES map_layers(id) ON DELETE CASCADE,
            CONSTRAINT fk_map_layer_right_right FOREIGN KEY (forest_right_id) REFERENCES forest_rights(id) ON DELETE CASCADE
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS business_records (
            id CHAR(36) PRIMARY KEY,
            module_key VARCHAR(96) NOT NULL,
            record_code VARCHAR(160) NOT NULL,
            name VARCHAR(255) NOT NULL,
            status VARCHAR(64),
            properties JSON,
            payload JSON,
            created_at DATETIME(6) NOT NULL,
            updated_at DATETIME(6) NOT NULL,
            deleted_at DATETIME(6),
            UNIQUE KEY uq_business_module_code (module_key, record_code),
            KEY idx_business_module_status (module_key, status),
            KEY idx_business_updated (updated_at),
            KEY idx_business_deleted (deleted_at)
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS business_record_block_links (
            business_record_id CHAR(36) NOT NULL,
            forest_block_id CHAR(36) NOT NULL,
            UNIQUE KEY uq_business_record_block (business_record_id, forest_block_id),
            KEY idx_business_record_block_block (forest_block_id),
            CONSTRAINT fk_business_block_record FOREIGN KEY (business_record_id) REFERENCES business_records(id) ON DELETE CASCADE,
            CONSTRAINT fk_business_block_block FOREIGN KEY (forest_block_id) REFERENCES forest_blocks(id) ON DELETE CASCADE
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS business_record_right_links (
            business_record_id CHAR(36) NOT NULL,
            forest_right_id CHAR(36) NOT NULL,
            UNIQUE KEY uq_business_record_right (business_record_id, forest_right_id),
            KEY idx_business_record_right_right (forest_right_id),
            CONSTRAINT fk_business_right_record FOREIGN KEY (business_record_id) REFERENCES business_records(id) ON DELETE CASCADE,
            CONSTRAINT fk_business_right_right FOREIGN KEY (forest_right_id) REFERENCES forest_rights(id) ON DELETE CASCADE
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS business_record_links (
            source_record_id CHAR(36) NOT NULL,
            relation_type VARCHAR(96) NOT NULL,
            target_module_key VARCHAR(96) NOT NULL,
            target_record_id CHAR(36) NOT NULL,
            sort_order INT NOT NULL DEFAULT 0,
            properties JSON,
            UNIQUE KEY uq_business_record_link (
                source_record_id, relation_type, target_module_key, target_record_id
            ),
            KEY idx_business_record_link_target (target_module_key, target_record_id),
            KEY idx_business_record_link_relation (relation_type, source_record_id),
            CONSTRAINT fk_business_record_link_source
                FOREIGN KEY (source_record_id) REFERENCES business_records(id) ON DELETE CASCADE,
            CONSTRAINT fk_business_record_link_target
                FOREIGN KEY (target_record_id) REFERENCES business_records(id) ON DELETE CASCADE
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS business_record_attributes (
            business_record_id CHAR(36) NOT NULL,
            module_key VARCHAR(96) NOT NULL,
            field_key VARCHAR(96) NOT NULL,
            value_type VARCHAR(24) NOT NULL,
            text_value VARCHAR(1024),
            number_value DECIMAL(24,8),
            date_value DATE,
            datetime_value DATETIME(6),
            boolean_value BOOLEAN,
            updated_at DATETIME(6) NOT NULL,
            UNIQUE KEY uq_business_record_attribute (business_record_id, field_key),
            KEY idx_business_attribute_text (module_key, field_key, text_value(191)),
            KEY idx_business_attribute_number (module_key, field_key, number_value),
            KEY idx_business_attribute_date (module_key, field_key, date_value),
            KEY idx_business_attribute_datetime (module_key, field_key, datetime_value),
            KEY idx_business_attribute_boolean (module_key, field_key, boolean_value),
            CONSTRAINT fk_business_attribute_record
                FOREIGN KEY (business_record_id) REFERENCES business_records(id) ON DELETE CASCADE
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS harvest_quotas (
            id CHAR(36) PRIMARY KEY,
            quota_year SMALLINT UNSIGNED NOT NULL,
            authority_name VARCHAR(255) NOT NULL,
            forest_type VARCHAR(64),
            block_code VARCHAR(128),
            quota_area_mu DECIMAL(18,4) NOT NULL DEFAULT 0,
            quota_quantity_ton DECIMAL(18,4) NOT NULL DEFAULT 0,
            used_area_mu DECIMAL(18,4) NOT NULL DEFAULT 0,
            used_quantity_ton DECIMAL(18,4) NOT NULL DEFAULT 0,
            status VARCHAR(32) NOT NULL DEFAULT 'active',
            notes VARCHAR(1000),
            created_by VARCHAR(128),
            created_at DATETIME(6) NOT NULL,
            updated_at DATETIME(6) NOT NULL,
            deleted_at DATETIME(6),
            KEY idx_harvest_quota_year_status (quota_year, status, deleted_at),
            KEY idx_harvest_quota_block (block_code, deleted_at)
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS harvest_applications (
            id CHAR(36) PRIMARY KEY,
            application_no VARCHAR(64) NOT NULL,
            name VARCHAR(255) NOT NULL,
            applicant_type VARCHAR(32) NOT NULL,
            applicant_id CHAR(36) NOT NULL,
            applicant_name VARCHAR(255) NOT NULL,
            status VARCHAR(32) NOT NULL,
            harvest_type VARCHAR(32) NOT NULL,
            requested_area_mu DECIMAL(18,4) NOT NULL,
            requested_quantity_ton DECIMAL(18,4) NOT NULL DEFAULT 0,
            quota_id CHAR(36) NOT NULL,
            work_start_at DATETIME(6) NOT NULL,
            work_end_at DATETIME(6) NOT NULL,
            purpose VARCHAR(1000),
            quota_check_json JSON NOT NULL,
            approval_json JSON NOT NULL,
            operation_json JSON NOT NULL,
            verification_json JSON NOT NULL,
            version INT UNSIGNED NOT NULL DEFAULT 1,
            created_by VARCHAR(128),
            created_at DATETIME(6) NOT NULL,
            updated_at DATETIME(6) NOT NULL,
            deleted_at DATETIME(6),
            UNIQUE KEY uq_harvest_application_no (application_no),
            KEY idx_harvest_application_status (status, deleted_at, updated_at),
            KEY idx_harvest_application_subject (applicant_type, applicant_id),
            KEY idx_harvest_application_quota (quota_id),
            CONSTRAINT fk_harvest_application_quota FOREIGN KEY (quota_id) REFERENCES harvest_quotas(id)
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS harvest_application_block_links (
            harvest_application_id CHAR(36) NOT NULL,
            forest_block_id CHAR(36) NOT NULL,
            block_code VARCHAR(128) NOT NULL,
            declared_area_mu DECIMAL(18,4),
            PRIMARY KEY (harvest_application_id, forest_block_id),
            KEY idx_harvest_block_link_code (block_code),
            CONSTRAINT fk_harvest_block_link_application FOREIGN KEY (harvest_application_id) REFERENCES harvest_applications(id) ON DELETE CASCADE,
            CONSTRAINT fk_harvest_block_link_block FOREIGN KEY (forest_block_id) REFERENCES forest_blocks(id)
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS harvest_application_right_links (
            harvest_application_id CHAR(36) NOT NULL,
            forest_right_id CHAR(36) NOT NULL,
            archive_code VARCHAR(128) NOT NULL,
            PRIMARY KEY (harvest_application_id, forest_right_id),
            KEY idx_harvest_right_link_code (archive_code),
            CONSTRAINT fk_harvest_right_link_application FOREIGN KEY (harvest_application_id) REFERENCES harvest_applications(id) ON DELETE CASCADE,
            CONSTRAINT fk_harvest_right_link_right FOREIGN KEY (forest_right_id) REFERENCES forest_rights(id)
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS harvest_events (
            id CHAR(36) PRIMARY KEY,
            harvest_application_id CHAR(36) NOT NULL,
            action VARCHAR(64) NOT NULL,
            from_status VARCHAR(32),
            to_status VARCHAR(32),
            actor VARCHAR(128),
            note VARCHAR(2000),
            event_json JSON NOT NULL,
            created_at DATETIME(6) NOT NULL,
            KEY idx_harvest_event_application (harvest_application_id, created_at),
            KEY idx_harvest_event_action (action, created_at),
            CONSTRAINT fk_harvest_event_application FOREIGN KEY (harvest_application_id) REFERENCES harvest_applications(id) ON DELETE CASCADE
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS harvest_batches (
            id CHAR(36) PRIMARY KEY,
            batch_no VARCHAR(64) NOT NULL,
            harvest_application_id CHAR(36) NOT NULL,
            trace_code VARCHAR(96) NOT NULL,
            actual_area_mu DECIMAL(18,4) NOT NULL,
            actual_quantity_ton DECIMAL(18,4) NOT NULL DEFAULT 0,
            block_codes JSON NOT NULL,
            resource_version_ids JSON NOT NULL,
            created_by VARCHAR(128),
            created_at DATETIME(6) NOT NULL,
            UNIQUE KEY uq_harvest_batch_no (batch_no),
            UNIQUE KEY uq_harvest_batch_application (harvest_application_id),
            UNIQUE KEY uq_harvest_trace_code (trace_code),
            CONSTRAINT fk_harvest_batch_application FOREIGN KEY (harvest_application_id) REFERENCES harvest_applications(id)
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS safety_events (
            id CHAR(36) PRIMARY KEY,
            incident_no VARCHAR(64) NOT NULL,
            title VARCHAR(255) NOT NULL,
            event_type VARCHAR(64) NOT NULL,
            severity VARCHAR(24) NOT NULL,
            status VARCHAR(32) NOT NULL,
            source_type VARCHAR(32) NOT NULL,
            source_ref VARCHAR(128),
            location_text VARCHAR(500),
            longitude DECIMAL(11,8),
            latitude DECIMAL(11,8),
            responsibility_unit VARCHAR(255),
            assignee_name VARCHAR(128),
            deadline_at DATETIME(6),
            description TEXT,
            resolution_json JSON NOT NULL,
            review_json JSON NOT NULL,
            version INT UNSIGNED NOT NULL DEFAULT 1,
            created_by VARCHAR(128),
            created_at DATETIME(6) NOT NULL,
            updated_at DATETIME(6) NOT NULL,
            closed_at DATETIME(6),
            deleted_at DATETIME(6),
            UNIQUE KEY uq_safety_incident_no (incident_no),
            KEY idx_safety_event_status (status, severity, deleted_at, updated_at),
            KEY idx_safety_event_assignee (assignee_name, status, deadline_at),
            KEY idx_safety_event_source (source_type, source_ref)
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS safety_event_block_links (
            safety_event_id CHAR(36) NOT NULL,
            forest_block_id CHAR(36) NOT NULL,
            block_code VARCHAR(128) NOT NULL,
            PRIMARY KEY (safety_event_id, forest_block_id),
            KEY idx_safety_event_block_code (block_code, safety_event_id),
            CONSTRAINT fk_safety_event_block_event FOREIGN KEY (safety_event_id) REFERENCES safety_events(id) ON DELETE CASCADE,
            CONSTRAINT fk_safety_event_block_block FOREIGN KEY (forest_block_id) REFERENCES forest_blocks(id)
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS safety_event_timeline (
            id CHAR(36) PRIMARY KEY,
            safety_event_id CHAR(36) NOT NULL,
            action VARCHAR(64) NOT NULL,
            from_status VARCHAR(32),
            to_status VARCHAR(32),
            actor VARCHAR(128),
            note VARCHAR(2000),
            event_json JSON NOT NULL,
            created_at DATETIME(6) NOT NULL,
            KEY idx_safety_timeline_event (safety_event_id, created_at),
            KEY idx_safety_timeline_action (action, created_at),
            CONSTRAINT fk_safety_timeline_event FOREIGN KEY (safety_event_id) REFERENCES safety_events(id) ON DELETE CASCADE
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS safety_alerts (
            id CHAR(36) PRIMARY KEY,
            alert_no VARCHAR(64) NOT NULL,
            title VARCHAR(255) NOT NULL,
            alert_type VARCHAR(64) NOT NULL,
            severity VARCHAR(24) NOT NULL,
            status VARCHAR(32) NOT NULL,
            source_type VARCHAR(32) NOT NULL,
            source_ref VARCHAR(128),
            device_code VARCHAR(128),
            location_text VARCHAR(500),
            longitude DECIMAL(11,8),
            latitude DECIMAL(11,8),
            description TEXT,
            block_codes JSON NOT NULL,
            raw_payload JSON NOT NULL,
            review_json JSON NOT NULL,
            safety_event_id CHAR(36),
            occurred_at DATETIME(6) NOT NULL,
            created_at DATETIME(6) NOT NULL,
            updated_at DATETIME(6) NOT NULL,
            UNIQUE KEY uq_safety_alert_no (alert_no),
            KEY idx_safety_alert_status (status, severity, occurred_at),
            KEY idx_safety_alert_source (source_type, source_ref),
            KEY idx_safety_alert_event (safety_event_id),
            CONSTRAINT fk_safety_alert_event FOREIGN KEY (safety_event_id) REFERENCES safety_events(id) ON DELETE SET NULL
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS labor_workers (
            id CHAR(36) PRIMARY KEY,
            worker_no VARCHAR(64) NOT NULL,
            name VARCHAR(128) NOT NULL,
            mobile VARCHAR(32),
            id_card_mask VARCHAR(32),
            gender VARCHAR(16),
            employment_status VARCHAR(32) NOT NULL,
            skill_codes JSON NOT NULL,
            qualifications_json JSON NOT NULL,
            training_status VARCHAR(32) NOT NULL,
            credit_score DECIMAL(5,2) NOT NULL DEFAULT 100,
            home_address VARCHAR(500),
            emergency_contact VARCHAR(128),
            notes TEXT,
            created_by VARCHAR(128),
            created_at DATETIME(6) NOT NULL,
            updated_at DATETIME(6) NOT NULL,
            deleted_at DATETIME(6),
            UNIQUE KEY uq_labor_worker_no (worker_no),
            KEY idx_labor_worker_status (employment_status, training_status, deleted_at),
            KEY idx_labor_worker_name_mobile (name, mobile)
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS labor_teams (
            id CHAR(36) PRIMARY KEY,
            team_no VARCHAR(64) NOT NULL,
            name VARCHAR(160) NOT NULL,
            status VARCHAR(32) NOT NULL,
            leader_worker_id CHAR(36),
            leader_name VARCHAR(128),
            contact_phone VARCHAR(32),
            service_area VARCHAR(500),
            skill_codes JSON NOT NULL,
            notes TEXT,
            created_by VARCHAR(128),
            created_at DATETIME(6) NOT NULL,
            updated_at DATETIME(6) NOT NULL,
            deleted_at DATETIME(6),
            UNIQUE KEY uq_labor_team_no (team_no),
            KEY idx_labor_team_status (status, deleted_at),
            CONSTRAINT fk_labor_team_leader FOREIGN KEY (leader_worker_id) REFERENCES labor_workers(id) ON DELETE SET NULL
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS labor_team_members (
            labor_team_id CHAR(36) NOT NULL,
            labor_worker_id CHAR(36) NOT NULL,
            member_role VARCHAR(32) NOT NULL DEFAULT 'member',
            joined_at DATETIME(6) NOT NULL,
            left_at DATETIME(6),
            PRIMARY KEY (labor_team_id, labor_worker_id),
            KEY idx_labor_team_member_worker (labor_worker_id, left_at),
            CONSTRAINT fk_labor_member_team FOREIGN KEY (labor_team_id) REFERENCES labor_teams(id) ON DELETE CASCADE,
            CONSTRAINT fk_labor_member_worker FOREIGN KEY (labor_worker_id) REFERENCES labor_workers(id)
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS labor_jobs (
            id CHAR(36) PRIMARY KEY,
            job_no VARCHAR(64) NOT NULL,
            title VARCHAR(255) NOT NULL,
            status VARCHAR(32) NOT NULL,
            employer_type VARCHAR(32) NOT NULL,
            employer_id CHAR(36),
            employer_name VARCHAR(160) NOT NULL,
            work_type VARCHAR(64) NOT NULL,
            required_headcount INT UNSIGNED NOT NULL,
            unit_price DECIMAL(14,2) NOT NULL,
            price_unit VARCHAR(32) NOT NULL,
            planned_start_at DATETIME(6) NOT NULL,
            planned_end_at DATETIME(6) NOT NULL,
            team_id CHAR(36),
            team_name VARCHAR(160),
            contract_no VARCHAR(96),
            contract_start_at DATETIME(6),
            contract_end_at DATETIME(6),
            payment_terms VARCHAR(1000),
            actual_quantity DECIMAL(14,2),
            settlement_amount DECIMAL(14,2),
            settlement_json JSON NOT NULL,
            instructions TEXT,
            version INT UNSIGNED NOT NULL DEFAULT 1,
            created_by VARCHAR(128),
            created_at DATETIME(6) NOT NULL,
            updated_at DATETIME(6) NOT NULL,
            closed_at DATETIME(6),
            deleted_at DATETIME(6),
            UNIQUE KEY uq_labor_job_no (job_no),
            UNIQUE KEY uq_labor_contract_no (contract_no),
            KEY idx_labor_job_status (status, planned_start_at, deleted_at),
            KEY idx_labor_job_team (team_id, status),
            CONSTRAINT fk_labor_job_team FOREIGN KEY (team_id) REFERENCES labor_teams(id) ON DELETE SET NULL
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS labor_job_block_links (
            labor_job_id CHAR(36) NOT NULL,
            forest_block_id CHAR(36) NOT NULL,
            block_code VARCHAR(128) NOT NULL,
            PRIMARY KEY (labor_job_id, forest_block_id),
            KEY idx_labor_job_block_code (block_code, labor_job_id),
            CONSTRAINT fk_labor_job_block_job FOREIGN KEY (labor_job_id) REFERENCES labor_jobs(id) ON DELETE CASCADE,
            CONSTRAINT fk_labor_job_block_block FOREIGN KEY (forest_block_id) REFERENCES forest_blocks(id)
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS labor_attendance (
            id CHAR(36) PRIMARY KEY,
            labor_job_id CHAR(36) NOT NULL,
            labor_worker_id CHAR(36) NOT NULL,
            work_date DATE NOT NULL,
            check_in_at DATETIME(6),
            check_out_at DATETIME(6),
            work_hours DECIMAL(6,2) NOT NULL,
            work_quantity DECIMAL(12,2),
            status VARCHAR(32) NOT NULL,
            verifier_name VARCHAR(128),
            note VARCHAR(1000),
            created_by VARCHAR(128),
            created_at DATETIME(6) NOT NULL,
            updated_at DATETIME(6) NOT NULL,
            UNIQUE KEY uq_labor_attendance_day (labor_job_id, labor_worker_id, work_date),
            KEY idx_labor_attendance_worker (labor_worker_id, work_date),
            CONSTRAINT fk_labor_attendance_job FOREIGN KEY (labor_job_id) REFERENCES labor_jobs(id) ON DELETE CASCADE,
            CONSTRAINT fk_labor_attendance_worker FOREIGN KEY (labor_worker_id) REFERENCES labor_workers(id)
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS labor_job_timeline (
            id CHAR(36) PRIMARY KEY,
            labor_job_id CHAR(36) NOT NULL,
            action VARCHAR(64) NOT NULL,
            from_status VARCHAR(32),
            to_status VARCHAR(32),
            actor VARCHAR(128),
            note VARCHAR(2000),
            event_json JSON NOT NULL,
            created_at DATETIME(6) NOT NULL,
            KEY idx_labor_timeline_job (labor_job_id, created_at),
            CONSTRAINT fk_labor_timeline_job FOREIGN KEY (labor_job_id) REFERENCES labor_jobs(id) ON DELETE CASCADE
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS iot_devices (
            id CHAR(36) PRIMARY KEY,
            device_code VARCHAR(128) NOT NULL,
            name VARCHAR(255) NOT NULL,
            device_type VARCHAR(64) NOT NULL,
            vendor VARCHAR(160),
            model VARCHAR(160),
            serial_no VARCHAR(160),
            status VARCHAR(32) NOT NULL,
            connectivity_status VARCHAR(32) NOT NULL,
            owner_unit VARCHAR(255),
            custodian VARCHAR(128),
            firmware_version VARCHAR(96),
            installed_at DATETIME(6),
            last_seen_at DATETIME(6),
            longitude DECIMAL(11,8),
            latitude DECIMAL(11,8),
            location_text VARCHAR(500),
            metadata_json JSON NOT NULL,
            created_by VARCHAR(128),
            created_at DATETIME(6) NOT NULL,
            updated_at DATETIME(6) NOT NULL,
            deleted_at DATETIME(6),
            UNIQUE KEY uq_iot_device_code (device_code),
            UNIQUE KEY uq_iot_device_serial (serial_no),
            KEY idx_iot_device_type_status (device_type, status, deleted_at),
            KEY idx_iot_device_connectivity (connectivity_status, last_seen_at)
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS iot_device_block_links (
            iot_device_id CHAR(36) NOT NULL,
            forest_block_id CHAR(36) NOT NULL,
            block_code VARCHAR(128) NOT NULL,
            PRIMARY KEY (iot_device_id, forest_block_id),
            KEY idx_iot_device_block_code (block_code, iot_device_id),
            CONSTRAINT fk_iot_device_block_device FOREIGN KEY (iot_device_id) REFERENCES iot_devices(id) ON DELETE CASCADE,
            CONSTRAINT fk_iot_device_block_block FOREIGN KEY (forest_block_id) REFERENCES forest_blocks(id)
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS iot_device_maintenance (
            id CHAR(36) PRIMARY KEY,
            iot_device_id CHAR(36) NOT NULL,
            work_order_no VARCHAR(64) NOT NULL,
            maintenance_type VARCHAR(64) NOT NULL,
            status VARCHAR(32) NOT NULL,
            scheduled_at DATETIME(6),
            completed_at DATETIME(6),
            assignee_name VARCHAR(128),
            description TEXT,
            result TEXT,
            created_by VARCHAR(128),
            created_at DATETIME(6) NOT NULL,
            updated_at DATETIME(6) NOT NULL,
            UNIQUE KEY uq_iot_maintenance_no (work_order_no),
            KEY idx_iot_maintenance_device (iot_device_id, status, scheduled_at),
            CONSTRAINT fk_iot_maintenance_device FOREIGN KEY (iot_device_id) REFERENCES iot_devices(id) ON DELETE CASCADE
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS drone_missions (
            id CHAR(36) PRIMARY KEY,
            mission_no VARCHAR(64) NOT NULL,
            title VARCHAR(255) NOT NULL,
            mission_type VARCHAR(64) NOT NULL,
            status VARCHAR(32) NOT NULL,
            drone_device_id CHAR(36),
            device_code VARCHAR(128),
            device_name VARCHAR(255),
            pilot_name VARCHAR(128),
            route_name VARCHAR(255),
            objective TEXT,
            planned_start_at DATETIME(6),
            planned_end_at DATETIME(6),
            actual_start_at DATETIME(6),
            actual_end_at DATETIME(6),
            flight_summary JSON NOT NULL,
            result_asset_urls JSON NOT NULL,
            version INT UNSIGNED NOT NULL DEFAULT 1,
            created_by VARCHAR(128),
            created_at DATETIME(6) NOT NULL,
            updated_at DATETIME(6) NOT NULL,
            closed_at DATETIME(6),
            deleted_at DATETIME(6),
            UNIQUE KEY uq_drone_mission_no (mission_no),
            KEY idx_drone_mission_status (status, planned_start_at, deleted_at),
            KEY idx_drone_mission_device (drone_device_id, status),
            CONSTRAINT fk_drone_mission_device FOREIGN KEY (drone_device_id) REFERENCES iot_devices(id)
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS drone_mission_block_links (
            drone_mission_id CHAR(36) NOT NULL,
            forest_block_id CHAR(36) NOT NULL,
            block_code VARCHAR(128) NOT NULL,
            PRIMARY KEY (drone_mission_id, forest_block_id),
            KEY idx_drone_mission_block_code (block_code, drone_mission_id),
            CONSTRAINT fk_drone_mission_block_mission FOREIGN KEY (drone_mission_id) REFERENCES drone_missions(id) ON DELETE CASCADE,
            CONSTRAINT fk_drone_mission_block_block FOREIGN KEY (forest_block_id) REFERENCES forest_blocks(id)
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS drone_mission_timeline (
            id CHAR(36) PRIMARY KEY,
            drone_mission_id CHAR(36) NOT NULL,
            action VARCHAR(64) NOT NULL,
            from_status VARCHAR(32),
            to_status VARCHAR(32),
            actor VARCHAR(128),
            note VARCHAR(2000),
            event_json JSON NOT NULL,
            created_at DATETIME(6) NOT NULL,
            KEY idx_drone_timeline_mission (drone_mission_id, created_at),
            CONSTRAINT fk_drone_timeline_mission FOREIGN KEY (drone_mission_id) REFERENCES drone_missions(id) ON DELETE CASCADE
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS ai_findings (
            id CHAR(36) PRIMARY KEY,
            finding_no VARCHAR(64) NOT NULL,
            title VARCHAR(255) NOT NULL,
            finding_type VARCHAR(64) NOT NULL,
            status VARCHAR(32) NOT NULL,
            model_code VARCHAR(128) NOT NULL,
            model_version VARCHAR(96) NOT NULL,
            confidence DECIMAL(7,6) NOT NULL,
            source_asset_url VARCHAR(1000),
            drone_mission_id CHAR(36),
            iot_device_id CHAR(36),
            device_code VARCHAR(128),
            location_text VARCHAR(500),
            longitude DECIMAL(11,8),
            latitude DECIMAL(11,8),
            result_json JSON NOT NULL,
            review_json JSON NOT NULL,
            safety_alert_id CHAR(36),
            occurred_at DATETIME(6) NOT NULL,
            created_by VARCHAR(128),
            created_at DATETIME(6) NOT NULL,
            updated_at DATETIME(6) NOT NULL,
            deleted_at DATETIME(6),
            UNIQUE KEY uq_ai_finding_no (finding_no),
            KEY idx_ai_finding_status (status, finding_type, occurred_at),
            KEY idx_ai_finding_mission (drone_mission_id),
            KEY idx_ai_finding_device (iot_device_id),
            CONSTRAINT fk_ai_finding_mission FOREIGN KEY (drone_mission_id) REFERENCES drone_missions(id) ON DELETE SET NULL,
            CONSTRAINT fk_ai_finding_device FOREIGN KEY (iot_device_id) REFERENCES iot_devices(id) ON DELETE SET NULL,
            CONSTRAINT fk_ai_finding_alert FOREIGN KEY (safety_alert_id) REFERENCES safety_alerts(id) ON DELETE SET NULL
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS ai_finding_block_links (
            ai_finding_id CHAR(36) NOT NULL,
            forest_block_id CHAR(36) NOT NULL,
            block_code VARCHAR(128) NOT NULL,
            PRIMARY KEY (ai_finding_id, forest_block_id),
            KEY idx_ai_finding_block_code (block_code, ai_finding_id),
            CONSTRAINT fk_ai_finding_block_finding FOREIGN KEY (ai_finding_id) REFERENCES ai_findings(id) ON DELETE CASCADE,
            CONSTRAINT fk_ai_finding_block_block FOREIGN KEY (forest_block_id) REFERENCES forest_blocks(id)
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS ai_finding_timeline (
            id CHAR(36) PRIMARY KEY,
            ai_finding_id CHAR(36) NOT NULL,
            action VARCHAR(64) NOT NULL,
            from_status VARCHAR(32),
            to_status VARCHAR(32),
            actor VARCHAR(128),
            note VARCHAR(2000),
            event_json JSON NOT NULL,
            created_at DATETIME(6) NOT NULL,
            KEY idx_ai_timeline_finding (ai_finding_id, created_at),
            CONSTRAINT fk_ai_timeline_finding FOREIGN KEY (ai_finding_id) REFERENCES ai_findings(id) ON DELETE CASCADE
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS ai_model_assets (
            id CHAR(36) PRIMARY KEY,
            asset_no VARCHAR(64) NOT NULL,
            asset_type VARCHAR(32) NOT NULL,
            name VARCHAR(255) NOT NULL,
            code VARCHAR(128) NOT NULL,
            version VARCHAR(96),
            status VARCHAR(32) NOT NULL,
            parent_id CHAR(36),
            framework VARCHAR(128),
            runtime_target VARCHAR(255),
            description VARCHAR(2000),
            metrics_json JSON NOT NULL,
            metadata_json JSON NOT NULL,
            created_by VARCHAR(128),
            created_at DATETIME(6) NOT NULL,
            updated_at DATETIME(6) NOT NULL,
            deleted_at DATETIME(6),
            UNIQUE KEY uq_ai_model_asset_no (asset_no),
            KEY idx_ai_model_asset_ledger (asset_type, status, updated_at),
            KEY idx_ai_model_asset_parent (parent_id, asset_type),
            CONSTRAINT fk_ai_model_asset_parent FOREIGN KEY (parent_id) REFERENCES ai_model_assets(id) ON DELETE SET NULL
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS ai_inference_runs (
            id CHAR(36) PRIMARY KEY,
            run_no VARCHAR(64) NOT NULL,
            title VARCHAR(255) NOT NULL,
            status VARCHAR(32) NOT NULL,
            model_asset_id CHAR(36) NOT NULL,
            deployment_asset_id CHAR(36),
            finding_id CHAR(36),
            parameters_json JSON NOT NULL,
            output_json JSON NOT NULL,
            error_message VARCHAR(2000),
            requested_at DATETIME(6) NOT NULL,
            started_at DATETIME(6),
            completed_at DATETIME(6),
            duration_ms BIGINT,
            created_by VARCHAR(128),
            created_at DATETIME(6) NOT NULL,
            updated_at DATETIME(6) NOT NULL,
            deleted_at DATETIME(6),
            UNIQUE KEY uq_ai_inference_run_no (run_no),
            KEY idx_ai_inference_ledger (status, requested_at),
            KEY idx_ai_inference_model (model_asset_id, requested_at),
            CONSTRAINT fk_ai_inference_model FOREIGN KEY (model_asset_id) REFERENCES ai_model_assets(id),
            CONSTRAINT fk_ai_inference_deployment FOREIGN KEY (deployment_asset_id) REFERENCES ai_model_assets(id),
            CONSTRAINT fk_ai_inference_finding FOREIGN KEY (finding_id) REFERENCES ai_findings(id) ON DELETE SET NULL
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS ai_inference_run_block_links (
            ai_inference_run_id CHAR(36) NOT NULL,
            forest_block_id CHAR(36) NOT NULL,
            block_code VARCHAR(128) NOT NULL,
            PRIMARY KEY (ai_inference_run_id, forest_block_id),
            KEY idx_ai_inference_block_code (block_code, ai_inference_run_id),
            CONSTRAINT fk_ai_inference_block_run FOREIGN KEY (ai_inference_run_id) REFERENCES ai_inference_runs(id) ON DELETE CASCADE,
            CONSTRAINT fk_ai_inference_block_block FOREIGN KEY (forest_block_id) REFERENCES forest_blocks(id)
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS mobile_sync_operations (
            id CHAR(36) PRIMARY KEY,
            client_operation_id VARCHAR(128) NOT NULL,
            user_id VARCHAR(128) NOT NULL,
            entity_type VARCHAR(64) NOT NULL,
            entity_id VARCHAR(128),
            action VARCHAR(64) NOT NULL,
            base_version VARCHAR(128),
            status VARCHAR(32) NOT NULL,
            request_json JSON NOT NULL,
            result_json JSON NOT NULL,
            error_code VARCHAR(64),
            occurred_at DATETIME(6) NOT NULL,
            received_at DATETIME(6) NOT NULL,
            completed_at DATETIME(6),
            UNIQUE KEY uq_mobile_operation_user_client (user_id, client_operation_id),
            KEY idx_mobile_operation_status (user_id, status, received_at),
            KEY idx_mobile_operation_entity (entity_type, entity_id, received_at)
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS mobile_evidence (
            id CHAR(36) PRIMARY KEY,
            evidence_no VARCHAR(64) NOT NULL,
            user_id VARCHAR(128) NOT NULL,
            task_type VARCHAR(64),
            task_id VARCHAR(128),
            file_name VARCHAR(255) NOT NULL,
            stored_name VARCHAR(255) NOT NULL,
            content_type VARCHAR(128) NOT NULL,
            byte_size BIGINT UNSIGNED NOT NULL,
            sha256 CHAR(64) NOT NULL,
            captured_at DATETIME(6),
            longitude DECIMAL(11,8),
            latitude DECIMAL(11,8),
            created_at DATETIME(6) NOT NULL,
            deleted_at DATETIME(6),
            UNIQUE KEY uq_mobile_evidence_no (evidence_no),
            KEY idx_mobile_evidence_task (task_type, task_id, created_at),
            KEY idx_mobile_evidence_user (user_id, created_at)
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS mobile_tracks (
            id CHAR(36) PRIMARY KEY,
            client_track_id VARCHAR(128) NOT NULL,
            user_id VARCHAR(128) NOT NULL,
            task_type VARCHAR(64) NOT NULL,
            task_id VARCHAR(128) NOT NULL,
            status VARCHAR(32) NOT NULL,
            points_json JSON NOT NULL,
            point_count INT UNSIGNED NOT NULL,
            distance_meters DECIMAL(14,3) NOT NULL DEFAULT 0,
            started_at DATETIME(6) NOT NULL,
            ended_at DATETIME(6) NOT NULL,
            created_at DATETIME(6) NOT NULL,
            deleted_at DATETIME(6),
            UNIQUE KEY uq_mobile_track_user_client (user_id, client_track_id),
            KEY idx_mobile_track_task (task_type, task_id, started_at),
            KEY idx_mobile_track_status (status, deleted_at, created_at)
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS mobile_upload_sessions (
            id CHAR(36) PRIMARY KEY,
            user_id VARCHAR(128) NOT NULL,
            task_type VARCHAR(64),
            task_id VARCHAR(128),
            file_name VARCHAR(255) NOT NULL,
            content_type VARCHAR(128) NOT NULL,
            total_bytes BIGINT UNSIGNED NOT NULL,
            total_chunks INT UNSIGNED NOT NULL,
            expected_sha256 CHAR(64),
            received_chunks_json JSON NOT NULL,
            status VARCHAR(32) NOT NULL,
            evidence_id CHAR(36),
            created_at DATETIME(6) NOT NULL,
            updated_at DATETIME(6) NOT NULL,
            expires_at DATETIME(6) NOT NULL,
            deleted_at DATETIME(6),
            KEY idx_mobile_upload_user (user_id, status, updated_at),
            KEY idx_mobile_upload_task (task_type, task_id, updated_at)
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS dictionary_types (
            id CHAR(36) PRIMARY KEY,
            type_code VARCHAR(100) NOT NULL,
            name VARCHAR(160) NOT NULL,
            category VARCHAR(80) NOT NULL,
            hierarchy_enabled BOOLEAN NOT NULL DEFAULT FALSE,
            value_mode VARCHAR(24) NOT NULL DEFAULT 'code',
            description TEXT,
            status VARCHAR(32) NOT NULL DEFAULT 'active',
            sort_order INT NOT NULL DEFAULT 0,
            system_defined BOOLEAN NOT NULL DEFAULT FALSE,
            properties JSON,
            created_at DATETIME(6) NOT NULL,
            updated_at DATETIME(6) NOT NULL,
            deleted_at DATETIME(6),
            UNIQUE KEY uq_dictionary_type_code (type_code),
            KEY idx_dictionary_type_category (category, status, sort_order),
            KEY idx_dictionary_type_deleted (deleted_at)
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS dictionary_items (
            id CHAR(36) PRIMARY KEY,
            dictionary_type_id CHAR(36) NOT NULL,
            item_code VARCHAR(120) NOT NULL,
            label VARCHAR(200) NOT NULL,
            parent_item_id CHAR(36),
            level_code VARCHAR(40) NOT NULL DEFAULT '',
            full_name VARCHAR(500),
            pinyin VARCHAR(300),
            initials VARCHAR(120),
            search_aliases JSON,
            sort_order INT NOT NULL DEFAULT 0,
            status VARCHAR(32) NOT NULL DEFAULT 'active',
            metadata JSON,
            source VARCHAR(40) NOT NULL DEFAULT 'manual',
            created_at DATETIME(6) NOT NULL,
            updated_at DATETIME(6) NOT NULL,
            deleted_at DATETIME(6),
            UNIQUE KEY uq_dictionary_item_code (dictionary_type_id, level_code, item_code),
            KEY idx_dictionary_item_lookup (dictionary_type_id, parent_item_id, status, sort_order),
            KEY idx_dictionary_item_level (dictionary_type_id, level_code, status),
            KEY idx_dictionary_item_label (dictionary_type_id, label),
            KEY idx_dictionary_item_deleted (deleted_at),
            CONSTRAINT fk_dictionary_item_type
                FOREIGN KEY (dictionary_type_id) REFERENCES dictionary_types(id) ON DELETE CASCADE,
            CONSTRAINT fk_dictionary_item_parent
                FOREIGN KEY (parent_item_id) REFERENCES dictionary_items(id) ON DELETE SET NULL
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS admin_roles (
            id CHAR(36) PRIMARY KEY,
            role_code VARCHAR(96) NOT NULL,
            name VARCHAR(160) NOT NULL,
            status VARCHAR(32),
            data_scopes JSON,
            properties JSON,
            created_at DATETIME(6) NOT NULL,
            updated_at DATETIME(6) NOT NULL,
            deleted_at DATETIME(6),
            UNIQUE KEY uq_admin_roles_code (role_code),
            KEY idx_admin_roles_status (status),
            KEY idx_admin_roles_deleted (deleted_at)
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS admin_role_permissions (
            admin_role_id CHAR(36) NOT NULL,
            permission_code VARCHAR(160) NOT NULL,
            UNIQUE KEY uq_admin_role_permission (admin_role_id, permission_code),
            KEY idx_admin_role_permission_code (permission_code),
            CONSTRAINT fk_admin_role_permission_role FOREIGN KEY (admin_role_id) REFERENCES admin_roles(id) ON DELETE CASCADE
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS admin_role_menu_modules (
            admin_role_id CHAR(36) NOT NULL,
            module_key VARCHAR(96) NOT NULL,
            UNIQUE KEY uq_admin_role_module (admin_role_id, module_key),
            KEY idx_admin_role_module_key (module_key),
            CONSTRAINT fk_admin_role_module_role FOREIGN KEY (admin_role_id) REFERENCES admin_roles(id) ON DELETE CASCADE
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS admin_users (
            id CHAR(36) PRIMARY KEY,
            username VARCHAR(128) NOT NULL,
            display_name VARCHAR(160) NOT NULL,
            status VARCHAR(32),
            data_scopes JSON,
            properties JSON,
            created_at DATETIME(6) NOT NULL,
            updated_at DATETIME(6) NOT NULL,
            deleted_at DATETIME(6),
            UNIQUE KEY uq_admin_users_username (username),
            KEY idx_admin_users_status (status),
            KEY idx_admin_users_deleted (deleted_at)
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS admin_organizations (
            id CHAR(36) PRIMARY KEY,
            organization_code VARCHAR(96) NOT NULL,
            name VARCHAR(200) NOT NULL,
            short_name VARCHAR(120),
            parent_id CHAR(36),
            organization_type VARCHAR(40) NOT NULL DEFAULT 'department',
            status VARCHAR(32) NOT NULL DEFAULT 'active',
            sort_order INT NOT NULL DEFAULT 0,
            leader VARCHAR(120),
            phone VARCHAR(64),
            address VARCHAR(500),
            administrative_division_code VARCHAR(32),
            data_scopes JSON,
            properties JSON,
            created_at DATETIME(6) NOT NULL,
            updated_at DATETIME(6) NOT NULL,
            deleted_at DATETIME(6),
            UNIQUE KEY uq_admin_organizations_code (organization_code),
            KEY idx_admin_organizations_parent (parent_id, sort_order),
            KEY idx_admin_organizations_status (status, deleted_at),
            CONSTRAINT fk_admin_organization_parent FOREIGN KEY (parent_id) REFERENCES admin_organizations(id) ON DELETE SET NULL
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS admin_user_roles (
            admin_user_id CHAR(36) NOT NULL,
            admin_role_id CHAR(36) NOT NULL,
            UNIQUE KEY uq_admin_user_role (admin_user_id, admin_role_id),
            KEY idx_admin_user_role_role (admin_role_id),
            CONSTRAINT fk_admin_user_role_user FOREIGN KEY (admin_user_id) REFERENCES admin_users(id) ON DELETE CASCADE,
            CONSTRAINT fk_admin_user_role_role FOREIGN KEY (admin_role_id) REFERENCES admin_roles(id) ON DELETE CASCADE
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS admin_user_credentials (
            id CHAR(36) PRIMARY KEY,
            admin_user_id CHAR(36) NOT NULL,
            password_hash VARCHAR(512) NOT NULL,
            password_changed_at DATETIME(6),
            must_change_password BOOLEAN NOT NULL DEFAULT TRUE,
            failed_login_count SMALLINT UNSIGNED NOT NULL DEFAULT 0,
            locked_until DATETIME(6),
            credential_version INT UNSIGNED NOT NULL DEFAULT 1,
            created_at DATETIME(6) NOT NULL,
            updated_at DATETIME(6) NOT NULL,
            UNIQUE KEY uq_admin_user_credentials_user (admin_user_id),
            CONSTRAINT fk_admin_user_credentials_user FOREIGN KEY (admin_user_id) REFERENCES admin_users(id) ON DELETE CASCADE
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS admin_sessions (
            id CHAR(36) PRIMARY KEY,
            admin_user_id CHAR(36) NOT NULL,
            token_hash CHAR(64) NOT NULL,
            csrf_token_hash CHAR(64) NOT NULL,
            credential_version INT UNSIGNED NOT NULL,
            ip_address VARCHAR(64),
            user_agent VARCHAR(512),
            issued_at DATETIME(6) NOT NULL,
            last_seen_at DATETIME(6) NOT NULL,
            expires_at DATETIME(6) NOT NULL,
            revoked_at DATETIME(6),
            UNIQUE KEY uq_admin_sessions_token_hash (token_hash),
            KEY idx_admin_sessions_user (admin_user_id),
            KEY idx_admin_sessions_expiry (expires_at, revoked_at),
            CONSTRAINT fk_admin_sessions_user FOREIGN KEY (admin_user_id) REFERENCES admin_users(id) ON DELETE CASCADE
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS platform_runtime_config (
            config_key VARCHAR(64) PRIMARY KEY,
            config_digest CHAR(64) NOT NULL,
            release_commit CHAR(40),
            updated_at DATETIME(6) NOT NULL
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS operations_notification_reads (
            user_id VARCHAR(128) NOT NULL,
            notification_id VARCHAR(191) NOT NULL,
            read_at DATETIME(6) NOT NULL,
            PRIMARY KEY (user_id, notification_id),
            KEY idx_operations_notification_reads_time (read_at)
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS import_batches (
            id CHAR(36) PRIMARY KEY,
            file_name VARCHAR(512) NOT NULL,
            file_type VARCHAR(32) NOT NULL,
            status VARCHAR(64) NOT NULL,
            total_rows INT UNSIGNED NOT NULL DEFAULT 0,
            valid_rows INT UNSIGNED NOT NULL DEFAULT 0,
            invalid_rows INT UNSIGNED NOT NULL DEFAULT 0,
            review_status VARCHAR(32) NOT NULL DEFAULT 'pending',
            acceptance_status VARCHAR(32) NOT NULL DEFAULT 'pending',
            quality_status VARCHAR(32) NOT NULL DEFAULT 'pending',
            publish_risk_status VARCHAR(32) NOT NULL DEFAULT 'unknown',
            created_by VARCHAR(128),
            report_json JSON,
            created_at DATETIME(6) NOT NULL,
            completed_at DATETIME(6),
            deleted_at DATETIME(6),
            KEY idx_import_batches_status_time (status, created_at),
            KEY idx_import_batches_workflow (review_status, acceptance_status, quality_status, publish_risk_status),
            KEY idx_import_batches_deleted (deleted_at),
            KEY idx_import_batches_file_name (file_name(191))
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS import_batch_events (
            import_batch_id CHAR(36) NOT NULL,
            event_type VARCHAR(32) NOT NULL,
            event_id VARCHAR(191) NOT NULL,
            action VARCHAR(64),
            status VARCHAR(64),
            actor VARCHAR(128),
            event_at DATETIME(6),
            summary VARCHAR(512),
            event_json JSON NOT NULL,
            PRIMARY KEY (import_batch_id, event_type, event_id),
            KEY idx_import_batch_events_time (event_at),
            KEY idx_import_batch_events_action (event_type, action, status),
            KEY idx_import_batch_events_actor (actor),
            CONSTRAINT fk_import_batch_event_batch FOREIGN KEY (import_batch_id) REFERENCES import_batches(id) ON DELETE CASCADE
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS import_batch_block_links (
            import_batch_id CHAR(36) NOT NULL,
            forest_block_id CHAR(36) NOT NULL,
            import_action VARCHAR(32),
            target_json JSON,
            UNIQUE KEY uq_import_batch_block (import_batch_id, forest_block_id),
            KEY idx_import_batch_block_block (forest_block_id),
            CONSTRAINT fk_import_batch_block_batch FOREIGN KEY (import_batch_id) REFERENCES import_batches(id) ON DELETE CASCADE,
            CONSTRAINT fk_import_batch_block_block FOREIGN KEY (forest_block_id) REFERENCES forest_blocks(id) ON DELETE CASCADE
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS import_batch_right_links (
            import_batch_id CHAR(36) NOT NULL,
            forest_right_id CHAR(36) NOT NULL,
            target_json JSON,
            UNIQUE KEY uq_import_batch_right (import_batch_id, forest_right_id),
            KEY idx_import_batch_right_right (forest_right_id),
            CONSTRAINT fk_import_batch_right_batch FOREIGN KEY (import_batch_id) REFERENCES import_batches(id) ON DELETE CASCADE,
            CONSTRAINT fk_import_batch_right_right FOREIGN KEY (forest_right_id) REFERENCES forest_rights(id) ON DELETE CASCADE
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS import_batch_scene_links (
            import_batch_id CHAR(36) NOT NULL,
            scene_id VARCHAR(160) NOT NULL,
            UNIQUE KEY uq_import_batch_scene (import_batch_id, scene_id),
            KEY idx_import_batch_scene_scene (scene_id),
            CONSTRAINT fk_import_batch_scene_batch FOREIGN KEY (import_batch_id) REFERENCES import_batches(id) ON DELETE CASCADE
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS forest_block_scene_links (
            forest_block_id CHAR(36) NOT NULL,
            scene_id VARCHAR(160) NOT NULL,
            relation_type VARCHAR(32) NOT NULL DEFAULT 'coverage',
            captured_at DATETIME(6),
            confidence DECIMAL(8,5),
            created_at DATETIME(6) NOT NULL,
            UNIQUE KEY uq_forest_block_scene (forest_block_id, scene_id, relation_type),
            KEY idx_forest_block_scene_scene (scene_id),
            CONSTRAINT fk_forest_block_scene_block FOREIGN KEY (forest_block_id) REFERENCES forest_blocks(id) ON DELETE CASCADE
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS remote_sensing_scenes (
            id VARCHAR(160) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'active',
            delivery_status VARCHAR(32) NOT NULL DEFAULT 'pending',
            published BOOLEAN NOT NULL DEFAULT FALSE,
            project_id VARCHAR(128),
            area_code VARCHAR(32),
            satellite VARCHAR(128),
            sensor VARCHAR(128),
            captured_at VARCHAR(64),
            created_at DATETIME(6),
            updated_at DATETIME(6),
            deleted_at DATETIME(6),
            scene JSON NOT NULL,
            KEY idx_remote_sensing_scene_status (status, delivery_status, published),
            KEY idx_remote_sensing_scene_project (project_id),
            KEY idx_remote_sensing_scene_area (area_code),
            KEY idx_remote_sensing_scene_satellite (satellite),
            KEY idx_remote_sensing_scene_updated (updated_at),
            KEY idx_remote_sensing_scene_deleted (deleted_at)
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS remote_sensing_scene_events (
            scene_id VARCHAR(160) NOT NULL,
            event_type VARCHAR(32) NOT NULL,
            event_id VARCHAR(191) NOT NULL,
            action VARCHAR(64),
            status VARCHAR(64),
            actor VARCHAR(128),
            event_at DATETIME(6),
            layer_id VARCHAR(160),
            issue_id VARCHAR(191),
            message VARCHAR(1000),
            event_json JSON NOT NULL,
            PRIMARY KEY (scene_id, event_type, event_id),
            KEY idx_remote_scene_events_time (event_at),
            KEY idx_remote_scene_events_action (event_type, action, status),
            KEY idx_remote_scene_events_layer (layer_id),
            KEY idx_remote_scene_events_issue (issue_id),
            CONSTRAINT fk_remote_scene_event_scene FOREIGN KEY (scene_id) REFERENCES remote_sensing_scenes(id) ON DELETE CASCADE
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS remote_sensing_scene_geometries (
            scene_id VARCHAR(160) PRIMARY KEY,
            footprint POLYGON NOT NULL SRID 4326,
            min_longitude DECIMAL(11,8) NOT NULL,
            min_latitude DECIMAL(11,8) NOT NULL,
            max_longitude DECIMAL(11,8) NOT NULL,
            max_latitude DECIMAL(11,8) NOT NULL,
            SPATIAL INDEX idx_remote_sensing_scene_footprint (footprint),
            KEY idx_remote_sensing_scene_bbox (min_longitude, min_latitude, max_longitude, max_latitude),
            CONSTRAINT fk_remote_sensing_scene_geometry_scene FOREIGN KEY (scene_id) REFERENCES remote_sensing_scenes(id) ON DELETE CASCADE
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS remote_sensing_tasks (
            id VARCHAR(160) PRIMARY KEY,
            status VARCHAR(32),
            type VARCHAR(64),
            scene_id VARCHAR(160),
            progress INT NOT NULL DEFAULT 0,
            archived_at DATETIME(6),
            created_at DATETIME(6),
            updated_at DATETIME(6),
            task JSON NOT NULL,
            KEY idx_remote_sensing_task_status (status, archived_at),
            KEY idx_remote_sensing_task_scene (scene_id),
            KEY idx_remote_sensing_task_created (created_at)
        ) {table_options}
        """,
        f"""
        CREATE TABLE IF NOT EXISTS remote_sensing_task_events (
            task_id VARCHAR(160) NOT NULL,
            event_id VARCHAR(191) NOT NULL,
            action VARCHAR(64),
            status VARCHAR(64),
            actor VARCHAR(128),
            progress INT,
            event_at DATETIME(6),
            message VARCHAR(1000),
            event_json JSON NOT NULL,
            PRIMARY KEY (task_id, event_id),
            KEY idx_remote_task_events_time (event_at),
            KEY idx_remote_task_events_action (action, status),
            CONSTRAINT fk_remote_task_event_task FOREIGN KEY (task_id) REFERENCES remote_sensing_tasks(id) ON DELETE CASCADE
        ) {table_options}
        """,
    ]


def mysql_catalog_schema_statements() -> list[str]:
    return [
        statement
        for statement in mysql_schema_statements()
        if any(f"CREATE TABLE IF NOT EXISTS {table}" in statement for table in REMOTE_SENSING_MYSQL_TABLES)
    ]


def mysql_platform_schema_statements() -> list[str]:
    return [
        statement
        for statement in mysql_schema_statements()
        if any(f"CREATE TABLE IF NOT EXISTS {table}" in statement for table in PLATFORM_CORE_MYSQL_TABLES)
    ]
