-- Why a run exists. The console's Fix & re-test step runs extra experiments
-- (two per fix trial, two per defense check); without this they were
-- indistinguishable from the assessments an operator launched, and buried
-- them in the run history. Additive: every existing row is an assessment.

ALTER TABLE experiments
    ADD COLUMN origin TEXT NOT NULL DEFAULT 'assessment'
    CHECK (origin IN ('assessment', 'fix_trial', 'defense_check'));

CREATE INDEX ix_experiments_origin_created_at ON experiments (origin, created_at DESC);
