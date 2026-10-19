/* ui-dashboard LOCAL schema: full docai catalog tables.
 *
 * Creates/upgrades BOTH tables with the identical column set:
 *   LIVE_PHOTO_LOGS          - recent data (last LIVE_WINDOW_DAYS days)
 *   LIVE_PHOTO_LOGS_ARCHIVE  - older data
 *
 * Mirrors the real DocAI catalog that the dashboard reads (column list is the
 * authoritative set from the old Streamlit uidb_client.CATALOG_COLUMNS, plus
 * FRAUD_ATTEMPT / USER_REVIEW).
 *
 * Idempotent and *additive*: if a table already exists (e.g. the trimmed
 * 4-column version created by livephoto-review's seed) it is upgraded in place
 * via ALTER TABLE ADD -- existing rows/data are preserved. Safe to re-run.
 *
 * Run either:
 *   sqlcmd -S localhost,1433 -U sa -P 'LocalDev123!' -i live_photo_logs_schema.sql
 *   <venv>/bin/python dba/local_dev_seed.py    (no sqlcmd needed; pyodbc)
 */
USE docai;
GO

SET NOCOUNT ON;
GO

DECLARE @tables TABLE (name SYSNAME);
INSERT INTO @tables (name) VALUES ('LIVE_PHOTO_LOGS'), ('LIVE_PHOTO_LOGS_ARCHIVE');

DECLARE @columns TABLE (col SYSNAME, def NVARCHAR(200));
INSERT INTO @columns (col, def) VALUES
 ('ID','INT NULL'),
 ('REQUEST_HIT_DATETIME','DATETIME2 NULL'),
 ('BLINK_REQUEST','BIT NULL'),
 ('BLINK_RESPONSE','BIT NULL'),
 ('BLINK_FACE_IN_CENTRE','BIT NULL'),
 ('BLINK_MULTIFACE','BIT NULL'),
 ('BLINK_STATUS','VARCHAR(50) NULL'),
 ('BLINK_RESPONSE_DURATION','FLOAT NULL'),
 ('HEAD_NOD_REQUEST_HIT_DATETIME','DATETIME2 NULL'),
 ('HEAD_NOD_REQUEST','BIT NULL'),
 ('HEAD_NOD_RESPONSE','BIT NULL'),
 ('HEAD_NOD_STATUS','VARCHAR(50) NULL'),
 ('HEAD_NOD_RESPONSE_DURATION','FLOAT NULL'),
 ('AUTHENTICITY_REQUEST','BIT NULL'),
 ('AUTHENTICITY_RESPONSE','BIT NULL'),
 ('AUTHENTICITY_STATUS','VARCHAR(50) NULL'),
 ('AUTHENTICITY_RESPONSE_DURATION','FLOAT NULL'),
 ('IMAGE_SEG_REQUEST','BIT NULL'),
 ('IMAGE_SEG_RESPONSE','BIT NULL'),
 ('IMAGE_SEG_STATUS','VARCHAR(50) NULL'),
 ('IMAGE_SEG_RESPONSE_DURATION','FLOAT NULL'),
 ('VERIFYTOKEN_REQ','BIT NULL'),
 ('VERIFYTOKEN_RES','BIT NULL'),
 ('VERIFYTOKEN_STATUS','VARCHAR(50) NULL'),
 ('VERIFY_TOKEN_RES_DURATION','FLOAT NULL'),
 ('CALLBACK_REQ','BIT NULL'),
 ('CALLBACK_RES','BIT NULL'),
 ('CALLBACK_STATUS','VARCHAR(50) NULL'),
 ('CALLBACK_RES_DURATION','FLOAT NULL'),
 ('EXCEPTION_MESSAGE','VARCHAR(MAX) NULL'),
 ('HEAD_NOD_EXCEPTION_MESSAGE','VARCHAR(MAX) NULL'),
 ('VERIFY_TOKEN_EXCEPTION','VARCHAR(MAX) NULL'),
 ('CALLBACK_EXCEPTION','VARCHAR(MAX) NULL'),
 ('SOURCE','VARCHAR(50) NULL'),
 ('TRACKING_ID','VARCHAR(50) NULL'),
 ('FRAUD_ATTEMPT','BIT NULL'),
 ('USER_REVIEW','VARCHAR(20) NULL DEFAULT ''REVIEW PENDING''');

DECLARE @name SYSNAME, @col SYSNAME, @def NVARCHAR(200), @sql NVARCHAR(MAX);

/* 1. Create any missing table with the full column set. */
DECLARE create_cur CURSOR LOCAL FAST_FORWARD FOR SELECT name FROM @tables;
OPEN create_cur;
FETCH NEXT FROM create_cur INTO @name;
WHILE @@FETCH_STATUS = 0
BEGIN
    IF OBJECT_ID(@name, 'U') IS NULL
    BEGIN
        SET @sql = N'
CREATE TABLE ' + QUOTENAME(@name) + N' (
    TXN_ID                         VARCHAR(100) NOT NULL PRIMARY KEY,
    ID                             INT NULL,
    REQUEST_HIT_DATETIME           DATETIME2 NULL,

    BLINK_REQUEST                  BIT NULL,
    BLINK_RESPONSE                 BIT NULL,
    BLINK_FACE_IN_CENTRE           BIT NULL,
    BLINK_MULTIFACE                BIT NULL,
    BLINK_STATUS                   VARCHAR(50) NULL,
    BLINK_RESPONSE_DURATION        FLOAT NULL,

    HEAD_NOD_REQUEST_HIT_DATETIME  DATETIME2 NULL,
    HEAD_NOD_REQUEST               BIT NULL,
    HEAD_NOD_RESPONSE              BIT NULL,
    HEAD_NOD_STATUS                VARCHAR(50) NULL,
    HEAD_NOD_RESPONSE_DURATION     FLOAT NULL,

    AUTHENTICITY_REQUEST           BIT NULL,
    AUTHENTICITY_RESPONSE          BIT NULL,
    AUTHENTICITY_STATUS            VARCHAR(50) NULL,
    AUTHENTICITY_RESPONSE_DURATION FLOAT NULL,

    IMAGE_SEG_REQUEST              BIT NULL,
    IMAGE_SEG_RESPONSE             BIT NULL,
    IMAGE_SEG_STATUS               VARCHAR(50) NULL,
    IMAGE_SEG_RESPONSE_DURATION    FLOAT NULL,

    VERIFYTOKEN_REQ                BIT NULL,
    VERIFYTOKEN_RES                BIT NULL,
    VERIFYTOKEN_STATUS             VARCHAR(50) NULL,
    VERIFY_TOKEN_RES_DURATION      FLOAT NULL,

    CALLBACK_REQ                   BIT NULL,
    CALLBACK_RES                   BIT NULL,
    CALLBACK_STATUS                VARCHAR(50) NULL,
    CALLBACK_RES_DURATION          FLOAT NULL,

    EXCEPTION_MESSAGE              VARCHAR(MAX) NULL,
    HEAD_NOD_EXCEPTION_MESSAGE     VARCHAR(MAX) NULL,
    VERIFY_TOKEN_EXCEPTION         VARCHAR(MAX) NULL,
    CALLBACK_EXCEPTION             VARCHAR(MAX) NULL,
    SOURCE                         VARCHAR(50) NULL,
    TRACKING_ID                    VARCHAR(50) NULL,

    FRAUD_ATTEMPT                  BIT NULL,
    USER_REVIEW                    VARCHAR(20) NULL DEFAULT ''REVIEW PENDING''
);';
        EXEC sp_executesql @sql;
    END
    FETCH NEXT FROM create_cur INTO @name;
END
CLOSE create_cur;
DEALLOCATE create_cur;

/* 2. Additively upgrade every table (add any column still missing). */
DECLARE upgrade_cur CURSOR LOCAL FAST_FORWARD FOR
    SELECT t.name, c.col, c.def FROM @tables t CROSS JOIN @columns c;
OPEN upgrade_cur;
FETCH NEXT FROM upgrade_cur INTO @name, @col, @def;
WHILE @@FETCH_STATUS = 0
BEGIN
    IF COL_LENGTH(@name, @col) IS NULL
    BEGIN
        SET @sql = N'ALTER TABLE ' + QUOTENAME(@name) + N' ADD ' + QUOTENAME(@col) + N' ' + @def;
        EXEC sp_executesql @sql;
    END
    FETCH NEXT FROM upgrade_cur INTO @name, @col, @def;
END
CLOSE upgrade_cur;
DEALLOCATE upgrade_cur;
GO
