from server.modules.mysql_schema import mysql_platform_schema_statements


def test_mysql_schema_contains_auth_secret_tables():
    sql = "\n".join(mysql_platform_schema_statements())

    assert "CREATE TABLE IF NOT EXISTS admin_user_credentials" in sql
    assert "CREATE TABLE IF NOT EXISTS admin_sessions" in sql
    assert "CREATE TABLE IF NOT EXISTS platform_runtime_config" in sql
    assert "UNIQUE KEY uq_admin_user_credentials_user" in sql
    assert "UNIQUE KEY uq_admin_sessions_token_hash" in sql
    assert "KEY idx_admin_sessions_expiry" in sql


def test_mysql_schema_contains_normalized_dictionary_tables():
    sql = "\n".join(mysql_platform_schema_statements())

    assert "CREATE TABLE IF NOT EXISTS dictionary_types" in sql
    assert "CREATE TABLE IF NOT EXISTS dictionary_items" in sql
    assert "UNIQUE KEY uq_dictionary_type_code" in sql
    assert "UNIQUE KEY uq_dictionary_item_code" in sql
    assert "CONSTRAINT fk_dictionary_item_type" in sql
    assert "CONSTRAINT fk_dictionary_item_parent" in sql
    assert "KEY idx_dictionary_item_lookup" in sql
