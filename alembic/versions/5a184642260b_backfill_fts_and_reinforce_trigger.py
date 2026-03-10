"""backfill_fts_and_reinforce_trigger

Revision ID: 5a184642260b
Revises: 52ae85da6f66
Create Date: 2026-03-09 13:43:17.772335

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5a184642260b'
down_revision: Union[str, None] = '52ae85da6f66'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Reinforce the Trigger (creates it if missing, replaces if broken)
    op.execute("""
        CREATE OR REPLACE FUNCTION users_search_vector_trigger() RETURNS trigger AS $$
        begin
          new.search_vector :=
            setweight(to_tsvector('pg_catalog.english', coalesce(new.full_name,'')), 'A') ||
            setweight(to_tsvector('pg_catalog.simple', coalesce(new.email,'')), 'B');
          return new;
        end
        $$ LANGUAGE plpgsql;
    """)

    op.execute("DROP TRIGGER IF EXISTS tsvectorupdate ON users;")
    
    op.execute("""
        CREATE TRIGGER tsvectorupdate BEFORE INSERT OR UPDATE
        ON users FOR EACH ROW EXECUTE FUNCTION users_search_vector_trigger();
    """)

    # 2. BACKFILL DATA: Forcefully update all existing users to calculate their search_vector
    op.execute("""
        UPDATE users SET search_vector = 
            setweight(to_tsvector('pg_catalog.english', coalesce(full_name,'')), 'A') ||
            setweight(to_tsvector('pg_catalog.simple', coalesce(email,'')), 'B');
    """)

def downgrade() -> None:
    # We don't need a downgrade for a data backfill, but we can drop the trigger
    op.execute("DROP TRIGGER IF EXISTS tsvectorupdate ON users;")
    op.execute("DROP FUNCTION IF EXISTS users_search_vector_trigger();")