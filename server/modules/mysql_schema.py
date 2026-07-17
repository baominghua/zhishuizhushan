from __future__ import annotations

from typing import Any


PLATFORM_MYSQL_TABLES = [
    "forest_blocks",
    "forest_block_geometries",
    "forest_block_versions",
    "forest_rights",
    "forest_right_versions",
    "forest_right_block_links",
    "map_layers",
    "map_layer_block_links",
    "map_layer_right_links",
    "business_records",
    "business_record_block_links",
    "business_record_right_links",
    "business_record_attributes",
    "admin_roles",
    "admin_role_permissions",
    "admin_role_menu_modules",
    "admin_users",
    "admin_user_roles",
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
        "import_batch_block_links",
        "target_json",
    ): "ALTER TABLE import_batch_block_links ADD COLUMN target_json JSON NULL",
    (
        "import_batch_right_links",
        "target_json",
    ): "ALTER TABLE import_batch_right_links ADD COLUMN target_json JSON NULL",
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


def apply_mysql_schema_upgrades(cur: Any) -> None:
    cur.execute(
        "SELECT table_name, index_name FROM information_schema.statistics "
        "WHERE table_schema = DATABASE()"
    )
    existing_indexes = {(str(row[0]), str(row[1])) for row in cur.fetchall()}
    for statement in mysql_index_upgrade_statements(existing_indexes):
        cur.execute(statement)
    cur.execute(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = DATABASE()"
    )
    existing_columns = {(str(row[0]), str(row[1])) for row in cur.fetchall()}
    for statement in mysql_column_upgrade_statements(existing_columns):
        cur.execute(statement)


def mysql_schema_statements() -> list[str]:
    table_options = "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci"
    return [
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
