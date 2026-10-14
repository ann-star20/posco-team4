"""At-least-once ROS command dispatch; device-side command ID is idempotent."""

import psycopg


def claim_due_commands(connection: psycopg.Connection, limit: int = 50) -> list[dict]:
    if not 1 <= limit <= 100:
        raise ValueError("invalid command batch limit")
    with connection.transaction():
        rows = connection.execute(
            "SELECT command_id,payload FROM commands "
            "WHERE status IN ('pending','sent') AND next_attempt_at<=now() "
            "ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT %s", (limit,),
        ).fetchall()
        for command_id, _ in rows:
            connection.execute(
                "UPDATE commands SET status='sent',attempt_count=attempt_count+1,"
                "next_attempt_at=now()+interval '2 seconds' WHERE command_id=%s",
                (command_id,),
            )
        return [payload for _, payload in rows]
