CREATE TABLE IF NOT EXISTS historian_meta.system_alerts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES historian_meta.users(id),
    alert_type TEXT, -- 'ACCOUNT_LOCKOUT'
    message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_read BOOLEAN DEFAULT FALSE
);
