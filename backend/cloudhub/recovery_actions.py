"""Read-only action hints; commands always recheck their own transaction fences."""
from .errors import HubError
def availability(service,rp):
    status=rp.get('status');busy=bool(rp.get('restore_lock') or rp.get('export_lock') or rp.get('delete_lock'))
    state=status if status not in {'AVAILABLE','DELETE_FAILED'} else None
    reason='BUSY' if busy else state or ('EXPIRED' if rp.get('retain_until',0)<=service.clock() else None)
    # A failed delete may have removed only part of the backup. Only retrying
    # deletion is safe until it has been reconciled; never advertise restore.
    reason=reason or ('DELETE_FAILED' if status=='DELETE_FAILED' else None)
    restore_reason=reason
    if not restore_reason:
        try:
            from .catalog import environment_configuration
            if not service.configuration_is_verified(rp['template_id'],environment_configuration(rp),service.region_for(rp)):restore_reason='CONFIGURATION_UNAVAILABLE'
        except (HubError,KeyError,TypeError):restore_reason='CONFIGURATION_UNAVAILABLE'
    return {'restore':{'allowed':not restore_reason and status=='AVAILABLE','reason':restore_reason},
        'export':{'allowed':not reason and status=='AVAILABLE','reason':reason},
        'delete':{'allowed':not busy and not rp.get('retirement_lock') and status in {'AVAILABLE','DELETE_FAILED'},
                  'reason':'BUSY' if busy else 'PROTECTED' if rp.get('retirement_lock') else state}}
