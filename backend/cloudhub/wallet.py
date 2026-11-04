"""Account-owned forecast credits. Never money, AWS credits, or a payment rail.

Existing Q#owner and F#/J# records remain authoritative. In particular, an
account's balance is never reduced by another account's reservations.
"""
DEFAULT_CREDIT_MILLIUSD = 10000


def snapshot(service, user):
    # A legacy quota without an explicit cap keeps its former effective cap.
    # New authenticated profiles always persist their explicit signup grant.
    granted = int(user.get('budget_milliusd', service.budget if user else DEFAULT_CREDIT_MILLIUSD))
    committed = int(user.get('reserved_milliusd', 0)) + int(user.get('observed_unreserved_milliusd', 0))
    return {'schema': 1, 'currency': 'USD', 'scope': 'ACCOUNT_LIFETIME_FORECAST',
            'is_money': False, 'is_aws_credit': False,
            'granted_milliusd': granted, 'committed_milliusd': committed,
            'balance_milliusd': max(0, granted - committed),
            'overcommitted_milliusd': max(0, committed - granted),
            'future_reserved_milliusd': int(user.get('future_reserved_milliusd', 0)),
            'accrued_estimate_milliusd': int(user.get('accrued_estimate_milliusd', 0)),
            'legacy_unreconciled_milliusd': int(user.get('legacy_unallocated_milliusd', user.get('reserved_milliusd', 0) if user.get('ledger_schema') != 2 else 0)),
            'unreserved_estimate_milliusd': int(user.get('observed_unreserved_milliusd', 0)),
            'updated_at': user.get('ledger_updated_at', user.get('initialized_at'))}


def budget_refusal(service, user, glob, amount):
    """Return a structured reason without mutating counters or taking funds."""
    wallet = snapshot(service, user)
    platform_remaining = max(0, service.budget - int(glob.get('reserved_milliusd', 0)) - int(glob.get('observed_unreserved_milliusd', 0)))
    scope = ('ACCOUNT_WALLET' if amount > wallet['balance_milliusd'] else
             'PLATFORM' if amount > platform_remaining else None)
    if scope is None:return None
    return {'budget_scope': scope, 'required_milliusd': amount,
            'wallet_balance_milliusd': wallet['balance_milliusd'],
            'platform_remaining_milliusd': platform_remaining, 'currency': 'USD'}
