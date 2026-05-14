SELECT 'CREATE DATABASE windmill'
WHERE NOT EXISTS (
    SELECT FROM pg_database WHERE datname = 'windmill'
)\gexec

