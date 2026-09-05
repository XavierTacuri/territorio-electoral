CAMPAIGN_EXECUTIVE_ROLES = frozenset({'CANDIDATE', 'CAMPAIGN_MANAGER'})


def has_campaign_executive_role(user) -> bool:
    return bool(CAMPAIGN_EXECUTIVE_ROLES.intersection(role.code for role in user.roles))
