"""Isolated service records and transactional messaging tables."""
from alembic import op
import sqlalchemy as sa

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('records', sa.Column('kind', sa.String(60), primary_key=True), sa.Column('id', sa.String(120), primary_key=True), sa.Column('payload', sa.JSON(), nullable=False))
    op.create_table('outbox', sa.Column('sequence', sa.Integer(), primary_key=True, autoincrement=True), sa.Column('event_id', sa.String(36), nullable=False, unique=True), sa.Column('routing_key', sa.String(120), nullable=False), sa.Column('payload', sa.JSON(), nullable=False), sa.Column('sent', sa.Boolean(), nullable=False))
    op.create_table('inbox', sa.Column('event_id', sa.String(36), primary_key=True))


def downgrade():
    op.drop_table('inbox')
    op.drop_table('outbox')
    op.drop_table('records')
