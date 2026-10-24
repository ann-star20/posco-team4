"""Authenticated Unity application receipts, distinct from display delivery."""
from datetime import datetime,timezone
from uuid import UUID,uuid5
from .contracts import EventCreate
from .repository import EventRepository


class UnityConflict(ValueError):pass


def accept_applied(db, ack):
    command_id=UUID(ack['command_id']);run_id=UUID(ack['run_id'])
    with db.transaction():
        db.execute('SELECT pg_advisory_xact_lock(4184,1)')
        row=db.execute("SELECT payload,status,applied_event_id FROM commands WHERE command_id=%s "
                       "AND run_id=%s AND delivery_target='unity' FOR UPDATE",(command_id,run_id)).fetchone()
        if not row:raise UnityConflict('unknown Unity command')
        payload,status,event_id=row
        if (ack.get('effective_from_lot')!=payload['effective_from_lot']
                or ack.get('x_applied')!=payload['x_candidate']):
            raise UnityConflict('applied values do not match approved command')
        if status=='applied':
            return {'command_id':str(command_id),'status':'committed','event_id':str(event_id)}
        if status not in {'pending','sent'}:raise UnityConflict('command cannot be applied')
        event_id=uuid5(command_id,'unity.applied')
        EventRepository(db)._insert_event(EventCreate(schema_version=1,event_id=event_id,
            event_type='correction.applied',source='unity.simulation',severity='info',
            occurred_at=datetime.now(timezone.utc),payload={**payload,'x_applied':ack['x_applied']}),run_id)
        db.execute("UPDATE commands SET status='applied',applied_event_id=%s,applied_at=now() WHERE command_id=%s",
                   (event_id,command_id))
        db.execute("UPDATE correction_proposals SET status='applied' WHERE proposal_id=%s",(UUID(payload['proposal_id']),))
        return {'command_id':str(command_id),'status':'committed','event_id':str(event_id)}
