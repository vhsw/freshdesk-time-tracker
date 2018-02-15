CREATE TABLE TimeEntries (
  id            INTEGER PRIMARY KEY,
  agent_id      INTEGER  NOT NULL,
  ticket_id     INTEGER UNIQUE,
  billable      INTEGER  NOT NULL,
  timer_running INTEGER  NOT NULL,
  time_spent    DATETIME NOT NULL,
  created_at    DATETIME NOT NULL,
  updated_at    DATETIME NOT NULL,
  executed_at   DATETIME NOT NULL,
  start_time    DATETIME NOT NULL
);