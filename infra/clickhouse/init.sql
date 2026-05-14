-- Rankings daily time series (main analytics table)
CREATE TABLE IF NOT EXISTS analytics.rankings_daily (
    date Date,
    project_id String,
    page_url String,
    keyword_id String,
    query String,
    position Float32,
    impressions UInt32,
    clicks UInt32,
    ctr Float32,
    -- Computed deltas (filled by tracker agent)
    position_delta Float32 DEFAULT 0,
    impressions_delta Int32 DEFAULT 0,
    clicks_delta Int32 DEFAULT 0,
    INDEX idx_project (project_id) TYPE bloom_filter GRANULARITY 1,
    INDEX idx_keyword (keyword_id) TYPE bloom_filter GRANULARITY 1
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(date)
ORDER BY (project_id, keyword_id, date)
TTL date + INTERVAL 2 YEAR;

-- Content performance (joins content version to ranking outcome)
CREATE TABLE IF NOT EXISTS analytics.content_performance (
    date Date,
    project_id String,
    content_version_id String,
    page_url String,
    target_keyword String,
    avg_position Float32,
    impressions UInt32,
    clicks UInt32,
    ctr Float32,
    conversions UInt32 DEFAULT 0,
    content_type String,
    edit_types Array(String)  -- ["faq_added", "entity_expanded"] for feedback loop
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(date)
ORDER BY (project_id, content_version_id, date)
TTL date + INTERVAL 2 YEAR;

-- Crawl audit snapshots (lightweight; just summary per crawl run)
CREATE TABLE IF NOT EXISTS analytics.crawl_summaries (
    crawl_date DateTime,
    project_id String,
    total_pages UInt32,
    indexable_pages UInt32,
    pages_with_issues UInt32,
    avg_lcp_ms Float32,
    avg_performance_score Float32,
    redirect_chains UInt16,
    missing_meta UInt16,
    duplicate_titles UInt16
)
ENGINE = MergeTree()
ORDER BY (project_id, crawl_date)
TTL toDate(crawl_date) + INTERVAL 1 YEAR;

-- Feedback loop signals (what edit-type correlated with rank improvement)
CREATE TABLE IF NOT EXISTS analytics.feedback_signals (
    recorded_at DateTime,
    project_id String,
    content_version_id String,
    edit_type String,
    position_before Float32,
    position_after Float32,
    position_delta Float32,
    days_to_measure UInt8,
    keyword String
)
ENGINE = MergeTree()
ORDER BY (project_id, edit_type, recorded_at);
