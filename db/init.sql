-- ============================================================
-- init.sql  —  runs automatically when Postgres container starts
-- ============================================================

-- SOURCE TABLE  (raw / unfiltered data)
CREATE TABLE IF NOT EXISTS table_a (
    id         SERIAL PRIMARY KEY,
    name       VARCHAR(100) NOT NULL,
    age        INT          NOT NULL,
    status     VARCHAR(20)  NOT NULL,   -- 'active' | 'inactive'
    department VARCHAR(50),
    salary     NUMERIC(10,2),
    created_at TIMESTAMP DEFAULT NOW()
);

-- DESTINATION TABLE  (only filtered, clean records)
CREATE TABLE IF NOT EXISTS table_b (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100),
    age         INT,
    status      VARCHAR(20),
    department  VARCHAR(50),
    salary      NUMERIC(10,2),
    filtered_at TIMESTAMP DEFAULT NOW()
);

-- PIPELINE LOG TABLE  (track every run)
CREATE TABLE IF NOT EXISTS pipeline_log (
    id          SERIAL PRIMARY KEY,
    step        VARCHAR(50),    -- 'load' | 'process' | 'store' | 'notify'
    status      VARCHAR(20),    -- 'success' | 'error'
    message     TEXT,
    rows_count  INT DEFAULT 0,
    ran_at      TIMESTAMP DEFAULT NOW()
);

-- ── Seed sample data into table_a ──────────────────────────────
INSERT INTO table_a (name, age, status, department, salary) VALUES
  ('Alice',   28, 'active',   'Engineering', 75000.00),
  ('Bob',     17, 'inactive', 'Intern',       15000.00),
  ('Charlie', 35, 'active',   'Engineering',  90000.00),
  ('Diana',   15, 'active',   'Intern',       12000.00),
  ('Eve',     42, 'inactive', 'HR',           60000.00),
  ('Frank',   30, 'active',   'Marketing',    65000.00),
  ('Grace',   26, 'active',   'Engineering',  80000.00),
  ('Hank',    19, 'inactive', 'Support',      30000.00),
  ('Ivy',     33, 'active',   'Finance',      70000.00),
  ('Jack',    45, 'active',   'Engineering',  95000.00);
