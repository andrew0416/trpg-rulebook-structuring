"""Explicit user permissions, separate from selected rulebook/homebrew sources."""
KEY = 'personal_type_settings'
SOURCE = 'personal-setting/typeless-terastal'
NEUTRAL_SOURCE = 'personal-setting/shared-typeless-type'
TYPELESS = '타입 없음'  # One personal neutral identity, including an empty native type list.
OPTIONS = {'ordinary_stellar', 'typeless_tera'}


def validate(profile):
    settings = profile.get(KEY, {})
    if (not isinstance(settings, dict) or set(settings) - OPTIONS
            or any(type(value) is not bool for value in settings.values())):
        raise ValueError('personal_type_settings requires named boolean permissions')
    return settings


def enabled(rules, permission):
    if permission not in OPTIONS:
        raise ValueError('unknown personal type permission')
    return validate(rules.ruleset.profile).get(permission, False)
