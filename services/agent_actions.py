from datetime import datetime
from database import get_db
from models import AgentAction
from services.events import track_event, _clean_payload
from flask import current_app

ALLOWLIST_ACTION_TYPES = {
    "draft_followup_email",
    "draft_sms",
    "schedule_reminder",
    "update_listing_highlights",
    "recommend_upgrade"
}

EXECUTION_ALLOWLIST = {
    "draft_followup_email",
    "draft_sms",
    "schedule_reminder"
}

def propose_action(*, user_id, created_by_type, created_by_id=None,
                  action_type, requires_approval=True,
                  property_id=None, lead_id=None, sign_asset_id=None, order_id=None,
                  proposal=None, policy_snapshot=None, input_event_refs=None, execute_after=None):
    """
    Propose a new agent action using strict safety defaults.
    """
    if action_type not in ALLOWLIST_ACTION_TYPES:
        raise ValueError(f"Invalid action_type: {action_type}")
        
    # Safety: Clean PII
    safe_proposal, _ = _clean_payload(proposal or {})
    safe_policy, _ = _clean_payload(policy_snapshot or {})
    
    # Input refs validation
    if input_event_refs:
        if not isinstance(input_event_refs, list):
             input_event_refs = []
        # Ensure minimal structure
        # (Could validate further but list of dicts is DB requirement mostly)
    else:
        input_event_refs = []

    status = "proposed" if requires_approval else "approved"
    
    action = AgentAction.create(
        user_id=user_id,
        created_by_type=created_by_type,
        created_by_id=created_by_id,
        action_type=action_type,
        status=status,
        requires_approval=requires_approval,
        property_id=property_id,
        lead_id=lead_id,
        sign_asset_id=sign_asset_id,
        order_id=order_id,
        proposal=safe_proposal,
        policy_snapshot=safe_policy,
        input_event_refs=input_event_refs,
        execute_after=execute_after
    )
    
    return action

def approve_action(action_id, approved_by_user_id):
    """
    Transition proposed -> approved.
    """
    db = get_db()
    action = AgentAction.get(action_id)
    if not action:
        raise ValueError("Action not found")
        
    if action.status != 'proposed':
        raise ValueError(f"Cannot approve action in status {action.status}")
        
    # TODO: Verify user ownership? "Only the owning user can approve"
    # We assume caller checks auth, but we can verify match
    if action.user_id != approved_by_user_id:
        # Strict ownership check
        raise PermissionError("User does not own this action")

    action.status = 'approved'
    action.approved_by_user_id = approved_by_user_id
    action.approved_at = datetime.utcnow() # timezone naive? Models usually want tz aware or we convert.
    # Postgres TIMESTAMPTZ handles naive as local, better use UTC ISO or naive UTC.
    # Codebase uses 'now()' in SQL mostly.
    # Let's use SQL update for atomicity + correct time
    
    db.execute("""
        UPDATE agent_actions 
        SET status = 'approved', 
            approved_by_user_id = %s, 
            approved_at = CURRENT_TIMESTAMP, 
            updated_at = CURRENT_TIMESTAMP 
        WHERE id = %s
    """, (approved_by_user_id, action_id))
    db.commit()
    
    return AgentAction.get(action_id)

def reject_action(action_id, rejected_by_user_id, reason):
    """
    Transition proposed -> rejected.
    """
    db = get_db()
    action = AgentAction.get(action_id)
    if not action:
        raise ValueError("Action not found")
        
    if action.status != 'proposed':
        raise ValueError(f"Cannot reject action in status {action.status}")

    # Ownership check
    if action.user_id != rejected_by_user_id:
        raise PermissionError("User does not own this action")

    db.execute("""
        UPDATE agent_actions 
        SET status = 'rejected', 
            rejected_by_user_id = %s, 
            rejected_at = CURRENT_TIMESTAMP, 
            rejection_reason = %s,
            updated_at = CURRENT_TIMESTAMP 
        WHERE id = %s
    """, (rejected_by_user_id, reason, action_id))
    db.commit()
    
    return AgentAction.get(action_id)

def execute_action(action_id):
    """
    Internal execution stub.
    """
    db = get_db()
    action = AgentAction.get(action_id)
    if not action:
        raise ValueError("Action not found")
        
    if action.status != 'approved':
        raise ValueError(f"Cannot execute action in status {action.status}")
        
    if action.action_type not in EXECUTION_ALLOWLIST:
        # Mark failed? Or just raise?
        # Logic says: "Allowed action_types for execution...". Implies others cannot be executed.
        raise ValueError(f"Action type {action.action_type} not executable in this phase")

    # Transition to executing? Or just do it?
    # Spec says "approved -> executing -> executed OR failed"
    
    try:
        # 1. Start
        db.execute("UPDATE agent_actions SET status = 'executing', updated_at = CURRENT_TIMESTAMP WHERE id = %s", (action_id,))
        db.commit()
        
        # 2. "Do Work" (Internal Stub)
        result_payload = {"result": "draft_created", "stub": True}
        
        # 3. Finish
        from psycopg2.extras import Json
        db.execute("""
            UPDATE agent_actions 
            SET status = 'executed', 
                executed_at = CURRENT_TIMESTAMP, 
                execution = %s,
                updated_at = CURRENT_TIMESTAMP 
            WHERE id = %s
        """, (Json(result_payload), action_id))
        db.commit()
        
        # 4. Audit Event
        track_event(
            "agent_action_executed",
            actor_type="system",
            subject_type="agent_action",
            subject_id=action_id,
            user_id=action.user_id,
            payload={
                "action_type": action.action_type,
                "status": "executed"
            }
        )
        
        return AgentAction.get(action_id)
        
    except Exception as e:
        # Fail
        db.rollback()
        db.execute("""
            UPDATE agent_actions 
            SET status = 'failed', 
                error_detail = %s,
                updated_at = CURRENT_TIMESTAMP 
            WHERE id = %s
        """, (str(e), action_id))
        db.commit()
        
        track_event(
            "agent_action_failed",
            actor_type="system",
            subject_type="agent_action",
            subject_id=action_id,
            user_id=action.user_id,
            payload={
                "action_type": action.action_type,
                "error": str(e)
            }
        )
        raise e
