"""Reusable deterministic catalog query fragments."""

from __future__ import annotations

# All callers use ``resources r`` and expose the selected row as ``local_files lf``.
# Values are never interpolated into this fixed fragment.
PREFERRED_LOCAL_FILE_JOIN = """
LEFT JOIN local_files lf ON lf.file_id = (
  SELECT preferred_lf.file_id
  FROM local_files preferred_lf
  WHERE preferred_lf.resource_id = r.resource_id
  ORDER BY
    CASE
      WHEN preferred_lf.quarantine_reason IS NULL
       AND REPLACE(preferred_lf.relative_path, CHAR(92), '/') NOT LIKE 'data/quarantine/%'
      THEN 0 ELSE 1
    END,
    CASE WHEN preferred_lf.duplicate_of_file_id IS NULL THEN 0 ELSE 1 END,
    CASE WHEN preferred_lf.verified_at IS NOT NULL THEN 0 ELSE 1 END,
    preferred_lf.file_id
  LIMIT 1
)
"""

# Classification review states currently emitted by the project are
# ``needs_review`` and ``auto_accepted``. The expression deliberately encodes
# precedence rather than relying on lexical MIN/MAX ordering.
RESOURCE_REVIEW_STATE_SQL = """
CASE
  WHEN EXISTS (
    SELECT 1 FROM resource_classifications review_rc
    WHERE review_rc.resource_id = r.resource_id
      AND review_rc.review_state = 'needs_review'
  ) THEN 'needs_review'
  WHEN EXISTS (
    SELECT 1 FROM resource_classifications review_rc
    WHERE review_rc.resource_id = r.resource_id
      AND review_rc.review_state = 'auto_accepted'
  ) THEN 'auto_accepted'
  ELSE NULL
END
"""
