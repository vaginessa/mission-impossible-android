"""
Create and configure a definition in the current workspace using the provided
template.

Usage:
    mia definition create [--cpu=<cpu>] [--force] [--template=<template>]
                          [<definition>]
    mia definition configure <definition>
    mia definition lock [--force-latest] <definition>
    mia definition dl-apps <definition>
    mia definition dl-os <definition>

Command options:
    --template=<template>  The template to use. [default: mia-default]
    --cpu=<cpu>            The device CPU architecture. [default: armeabi]
    --force                Delete existing definition.

    --force-latest         Force using the latest versions.

Notes:
    A valid <definition> name consists of lowercase letters, digits and hyphens.
    And it must start with a letter name.

"""

import re
import shutil
from urllib.request import urlretrieve

# Import non-standard libraries.
from lxml import html as lxml_html

# Import custom helpers.
from mia.helpers.android import *
from mia.helpers.utils import *


def main():
    # Get the MIA handler singleton.
    handler = MiaHandler()

    # The definition name is optional, this is helpful for new users.
    if handler.args['<definition>'] is None:
        msg = 'Please provide a definition name'
        handler.args['<definition>'] = input_ask(msg)

    if not re.search(r'^[a-z][a-z0-9-]+$', handler.args['<definition>']):
        # raise Exception('Definition "%s" already exists!' % definition)
        print('ERROR: Please provide a valid definition name! '
              'See: mia help definition')
        sys.exit(1)

    # Create the definition.
    if handler.args['create']:
        create_definition()

    # Configure the definition.
    if handler.args['configure']:
        configure_definition()

    # Create the apps lock file.
    if handler.args['lock']:
        create_apps_lock_file()

    # Download the CyanogenMod OS.
    if handler.args['dl-os']:
        download_os()

    # Download apps.
    if handler.args['dl-apps']:
        download_apps()

    return None


def create_definition():
    # Get the MIA handler singleton.
    handler = MiaHandler()

    definition_path = handler.get_definition_path()
    print('Destination directory is:\n - %s\n' % definition_path)

    # Make sure the definition does not exist.
    if os.path.exists(definition_path):
        if handler.args['--force']:
            print('Removing the old definition folder...')
            shutil.rmtree(definition_path)
        else:
            # raise Exception('Definition "%s" already exists!' % definition)
            print('ERROR: Definition "%s" already exists!' %
                  handler.args['<definition>'])
            sys.exit(1)

    template = handler.args['--template']
    template_path = os.path.join(handler.get_root_path(), 'templates', template)
    print('Using template:\n - %s\n' % template_path)

    # Check if the template exists.
    if not os.path.exists(template_path):
        # raise Exception('Template "%s" does not exist!' % template)
        print('ERROR: Template "%s" does not exist!' % template)
        sys.exit(1)

    # Make sure the definitions folder exists.
    os.makedirs(os.path.join(handler.get_workspace_path, 'definitions'),
                mode=0o755, exist_ok=True)

    # Create the definition using the provided template.
    shutil.copytree(template_path, definition_path)

    # Configure the definition.
    if input_confirm('Configure now?', True):
        print()
        configure_definition()


def configure_definition():
    # Get the MIA handler singleton.
    handler = MiaHandler()

    # Detect the device codename.
    cm_device_codename = get_cyanogenmod_codename()
    print('Using device codename: %s\n' % cm_device_codename)

    # Detect the CyanogenMod release type.
    if input_confirm('Use recommended CyanogenMod release type?', True):
        cm_release_type = get_cyanogenmod_release_type(True)
    else:
        cm_release_type = get_cyanogenmod_release_type(False)
    print('Using release type: %s\n' % cm_release_type)

    # Detect the CyanogenMod release version.
    if input_confirm('Use recommended CyanogenMod release version?', True):
        cm_release_version = get_cyanogenmod_release_version(True)
    else:
        cm_release_version = get_cyanogenmod_release_version(False)
    print('Using release version: %s\n' % cm_release_version)

    # The path to the definition settings.yaml file.
    definition_path = handler.get_definition_path()
    settings_file = os.path.join(definition_path, 'settings.yaml')
    settings_file_backup = os.path.join(definition_path, 'settings.orig.yaml')

    # Create a backup of the settings file.
    shutil.copy(settings_file, settings_file_backup)

    # Update the settings file.
    update_settings(settings_file, {'general': {
        'update': {
            'cm_device_codename': cm_device_codename,
            'cm_release_type': cm_release_type,
            'cm_release_version': cm_release_version,
        },
    }})

    # Create the apps lock file.
    create_apps_lock_file()

    # Download the CyanogenMod OS.
    if input_confirm('Download CyanogenMod OS now?', True):
        download_os()

    # Download apps.
    if input_confirm('Download apps now?', True):
        download_apps()


# TODO: Implement the APK lock functionality.
def create_apps_lock_file():
    # Get the MIA handler singleton.
    handler = MiaHandler()

    # Read the definition settings.
    settings = handler.get_definition_settings()

    # Generate APK lock files for all repositories.
    lock_data = {}
    for repo_info in settings['repositories']:
        apps_key = repo_info['apps_key']
        lock_data[apps_key] = get_apps_lock_info(repo_info, settings[apps_key])

    definition_path = handler.get_definition_path()
    lock_file_path = os.path.join(definition_path, 'apps_lock.yaml')
    print("Creating lock file:\n - %s\n" % lock_file_path)

    import yaml

    try:
        fd = open(lock_file_path, 'w')
        fd.write(yaml.dump(lock_data, default_flow_style=False))
        fd.close()
    except yaml.YAMLError:
        fd.close()
        print('ERROR: Could not save the lock file!')
        return None

    # Download apps.
    if handler.args['lock'] and input_confirm('Download apps now?', True):
        download_apps()


def get_apps_lock_info(repo_info, repo_apps):
    # Get the MIA handler singleton.
    handler = MiaHandler()

    index_path = os.path.join(handler.get_root_path(), 'resources',
                              repo_info['apps_key'] + '.index.xml')

    # Download the repository index.xml file.
    if not os.path.isfile(index_path):
        index_url = '%s/%s' % (repo_info['base_url'], 'index.xml')
        print('Downloading the %s repository information from:\n - %s' %
              (repo_info['name'], index_url))
        urlretrieve(index_url, index_path)

    # Read the whole file index in memory?!?
    try:
        with open(index_path, 'r') as index_fd:
            index_data = index_fd.read()

        xml_document = lxml_html.fromstring(index_data)
        index_fd.close()
    except FileNotFoundError:
        print('File not found:\n - %s' % index_path)

    print('Looking for APKs for repo %s' % repo_info['name'])
    for key, app_info in enumerate(repo_apps):
        if handler.args['--force-latest'] or app_info['code'] == 'latest':
            # Get information about the latest version of the application.
            latest_name_xpath = "//application[@id='%s']/package[0]/apkname/text()" % \
                                (app_info['name'])
            app_package_names = xml_document.xpath(latest_name_xpath)

            code_xpath = "//application[@id='%s']/marketvercode/text()" % \
                         app_info['name']
            app_version_codes = xml_document.xpath(code_xpath)
        else:
            # Get information about an exact version of the application.
            name_xpath = "//application[@id='%s']/package/apkname/text()[../../versioncode/text() = %s]" % \
                         (app_info['name'], app_info['code'])
            app_package_names = xml_document.xpath(name_xpath)
            app_version_codes = None

        if len(app_package_names):
            print(' - found: %s:%s' % (app_info['name'], app_info['code']))
        else:
            print(' - not found: %s' % app_info['name'])
            del repo_apps[key]
            continue

        app_info['package_name'] = "%s" % app_package_names[0]
        app_info['package_url'] = "%s/%s" % (repo_info['base_url'],
                                             app_package_names[0])
        if app_version_codes is not None and len(app_version_codes):
            app_info['code'] = app_version_codes[0]

    return repo_apps


def download_apps():
    # Get the MIA handler singleton.
    handler = MiaHandler()

    # Read the definition apps lock data.
    lock_data = handler.get_definition_apps_lock_data()

    # Path where to download the APK files.
    user_apps_folder = os.path.join(handler.get_definition_path(), 'user-apps')
    if not os.path.isdir(user_apps_folder):
        os.mkdir(user_apps_folder, mode=0o755)

    for repo_group in lock_data:
        print('Downloading %s...' % repo_group)
        for apk_info in lock_data[repo_group]:
            print(' - downloaded: %s:' % apk_info['package_url'])
            apk_path = os.path.join(user_apps_folder, apk_info['package_name'])
            urlretrieve(apk_info['package_url'], apk_path)


def download_os():
    print('\nNOTE: Command not finished yet; See instructions!\n')

    # Get the MIA handler singleton.
    handler = MiaHandler()

    # Read the definition settings.
    settings = handler.get_definition_settings()

    url = 'https://download.cyanogenmod.org/?device=%s&type=%s' % (
        settings['general']['cm_device_codename'],
        settings['general']['cm_release_type']
    )

    file_name = '%s.%s.%s-%s.zip' % (
        handler.args['<definition>'],
        settings['general']['cm_device_codename'],
        settings['general']['cm_release_type'],
        settings['general']['cm_release_version']
    )

    print("Download CyanogenMod for and save the file as\n - %s\n"
          "into the resources folder, then verify the file checksum.\n - %s\n"
          % (file_name, url))

    input_pause('Please follow the instructions before continuing!')
