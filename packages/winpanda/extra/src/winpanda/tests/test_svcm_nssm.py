import pytest

from svcm.exceptions import ServiceConfigError
from svcm.nssm import WinSvcManagerNSSM


def test_no_service():
    """
    Empty configuration fails
    """
    conf = {
    }
    opts = {
        'svc_conf': conf
    }
    with pytest.raises(ServiceConfigError) as e:
        WinSvcManagerNSSM(**opts)
    assert 'Section not found: service' in str(e)


def test_no_displayname():
    """
    Missing display name fails
    """
    conf = {
        'service': {
            'application': ''
        }
    }
    opts = {
        'svc_conf': conf
    }
    with pytest.raises(ServiceConfigError) as e:
        WinSvcManagerNSSM(**opts)
    assert 'Required parameter unavailable: displayname/name' in str(e)


def test_no_application():
    """
    Missing application name fails
    """
    conf = {
        'service': {
            'displayname': ''
        }
    }
    opts = {
        'svc_conf': conf
    }
    with pytest.raises(ServiceConfigError) as e:
        WinSvcManagerNSSM(**opts)
    assert 'Required parameter unavailable: application' in str(e)


def test_name_implies_displayname():
    """
    Display name can be derived from name
    """
    conf = {
        'service': {
            'application': '',
            'name': 'a_name',
        }
    }
    opts = {
        'svc_conf': conf
    }
    sm = WinSvcManagerNSSM(**opts)
    assert sm.svc_name == 'a_name'
    assert set(sm.svc_pnames_bulk) == set(('application', 'name'))


def test_displayname_before_name():
    """
    If name and displayname are both set, displayname is used
    """
    conf = {
        'service': {
            'application': 'an_app',
            'displayname': 'a_displayname',
            'name': 'a_name',
        }
    }
    opts = {
        'svc_conf': conf
    }
    sm = WinSvcManagerNSSM(**opts)
    assert sm.svc_name == 'a_displayname'
    assert sm._get_svc_setup_pchain() == [('install', ['a_displayname', 'an_app'])]


def test_all_parameters():
    """
    All parameters get translated to command arguments
    """
    conf = {
        'service': {
            'description': 'the_description',
            'displayname': 'the_displayname',
            'name': 'the_name',
            'application': 'the_application',
            'appdirectory': 'the_appdirectory',
            'appparameters': 'the_appparameters',
            'start': 'the_start',
            'dependonservice': 'the_dependonservice',
            'appstdout': 'the_appstdout',
            'appstderr': 'the_appstderr',
            'appenvironmentextra': 'the_appenvironmentextra',
            'appeventsstartpre': 'the_appevents_start_pre',
            'appeventsstartpost': 'the_appevents_start_post',
            'appeventsstoppre': 'the_appevents_stop_pre',
            'appeventsexitpost': 'the_appevents_exit_post',
            'appeventsrotatepre': 'the_appevents_rotate_pre',
            'appeventsrotatepost': 'the_appevents_rotate_post',
            'appeventspowerchange': 'the_appevents_power_change',
            'appeventspowerresume': 'the_appevents_power_resume',
            'appredirecthook': 'the_appredirecthook',
        }
    }
    opts = {
        'svc_conf': conf
    }
    sm = WinSvcManagerNSSM(**opts)
    assert sm.svc_name == 'the_displayname'
    assert sm.svc_exec == 'the_application'
    expected_names = set(conf['service'].keys())
    # if `displayname` is set, then `name` is removed
    expected_names.remove('name')
    assert set(sm.svc_pnames_bulk) == expected_names

    assert sm._get_svc_setup_pchain() == [
        ('install', ['the_displayname', 'the_application']),
        ('set', ['the_displayname', 'description', 'the_description']),
        ('set', ['the_displayname', 'appdirectory', 'the_appdirectory']),
        ('set', ['the_displayname', 'appparameters', 'the_appparameters']),
        ('set', ['the_displayname', 'start', 'the_start']),
        ('set', ['the_displayname', 'dependonservice', 'the_dependonservice']),
        ('set', ['the_displayname', 'appstdout', 'the_appstdout']),
        ('set', ['the_displayname', 'appstderr', 'the_appstderr']),
        ('set', ['the_displayname', 'appenvironmentextra', 'the_appenvironmentextra']),
        ('set', ['the_displayname', 'appevents', 'start/pre', 'the_appevents_start_pre']),
        ('set', ['the_displayname', 'appevents', 'start/post', 'the_appevents_start_post']),
        ('set', ['the_displayname', 'appevents', 'stop/pre', 'the_appevents_stop_pre']),
        ('set', ['the_displayname', 'appevents', 'exit/post', 'the_appevents_exit_post']),
        ('set', ['the_displayname', 'appevents', 'rotate/pre', 'the_appevents_rotate_pre']),
        ('set', ['the_displayname', 'appevents', 'rotate/post', 'the_appevents_rotate_post']),
        ('set', ['the_displayname', 'appevents', 'power/change', 'the_appevents_power_change']),
        ('set', ['the_displayname', 'appevents', 'power/resume', 'the_appevents_power_resume']),
        ('set', ['the_displayname', 'appredirecthook', 'the_appredirecthook']),
    ]
