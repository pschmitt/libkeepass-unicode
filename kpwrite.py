#!/usr/bin/env python
# coding: utf-8


from __future__ import print_function
from datetime import datetime
from lxml.etree import Element
import argparse
import base64
import libkeepass
import logging
import os
import uuid


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-p', '--password',
        help='Password of the KDBX database',
        required=True
    )
    parser.add_argument(
        '-k', '--keyfile',
        help='Keyfile to unlock the KDBX database',
        required=False
    )
    parser.add_argument(
        '-d', '--database',
        # type=argparse.FileType('r'),
        help='Database (KDBX file)',
        required=True
    )
    parser.add_argument(
        '-D', '--destination',
        help='Group where to write the new entry to',
        required=True
    )
    parser.add_argument(
        '-e', '--entry',
        help='Name of the new entry',
        required=True
    )
    parser.add_argument(
        '-U', '--entry-username',
        help='Username to put in the new entry',
        required=True
    )
    parser.add_argument(
        '-P', '--entry-password',
        help='Password to put in the new entry',
        required=True
    )
    return parser.parse_args()


def find_group_by_path(etree, group_name):
    xp = '/KeePassFile/Root/Group'
    for s in group_name.split('/'):
        xp += '/Group/Name[text()="{}"]/..'.format(s)
    result = etree.xpath(xp)
    # FIXME This raises a FutureWarning:
    # kpwrite.py:217: FutureWarning: The behavior of this method will change in
    # future versions. Use specific 'len(elem)' or 'elem is not None' test
    # instead.
    if len(result) > 0:
        return result[0]


def find_group_by_name(etree, group_name):
    '''
    '''
    result = etree.xpath('//Group/Name[text()="{}"]/..'.format(group_name))
    # FIXME This raises a FutureWarning:
    # kpwrite.py:217: FutureWarning: The behavior of this method will change in
    # future versions. Use specific 'len(elem)' or 'elem is not None' test
    # instead.
    if len(result) > 0:
        return result[0]



def find_group(etree, group_name):
    # FIXME: This will create the group in the root folder if it does not exist
    gname = os.path.dirname(group_name) if group_name.contains('/') else group_name
    return find_group_by_name(gname)


def generate_unique_uuid(etree):
    # FIXME This makes the database corrupt
    # "Value does not fall within the expected range"
    # NOTE: The stored value is base64 encoded
    # Eg: "klAHdnpC50mbES2Uk7agSg=="
    # It decodes to something like:
    # "\x92P\x07vzB\xe7I\x9b\x11-\x94\x93\xb6\xa0J"
    uuids = [str(x) for x in etree.xpath('//UUID')]
    while True:
        # rand_uuid = str(uuid.uuid1()).replace('-', '')[:24]
        # rand_uuid = base64.b64encode(bytearray(os.urandom(16)))
        rand_uuid = base64.b64encode(uuid.uuid1().bytes)
        if rand_uuid not in uuids:
            return rand_uuid


def get_uuid_element(etree):
    uuid_el = Element('UUID')
    uuid_el.text = generate_unique_uuid(etree)
    logger.info('New UUID: {}'.format(uuid_el.text))
    return uuid_el


def get_name_element(name):
    name_el = Element('Name')
    name_el.text = name
    return name_el


def __get_string_element(key, value):
    string_el = Element('String')
    key_el = Element('Key')
    key_el.text = key
    value_el = Element('Value')
    value_el.text = value
    string_el.append(key_el)
    string_el.append(value_el)
    return string_el

def get_title_element(title):
    return __get_string_element('Title', title)


def get_username_element(username):
    return __get_string_element('UserName', username)


def get_password_element(password):
    string_el = Element('String')
    key_el = Element('Key')
    key_el.text = 'Password'
    value_el = Element('Value')
    value_el.text = password
    value_el.set('Protected', 'False')
    # TODO FIXME
    value_el.set('ProtectedValue', '???')
    string_el.append(key_el)
    string_el.append(value_el)
    return string_el


def get_url_element(url):
    return __get_string_element('URL', url)


def get_notes_element(notes):
    return __get_string_element('Notes', notes)


def get_time_element(expires=False, expiry_time=None):
    dformat = '%Y-%m-%dT%H:%M:%SZ'
    now_str = datetime.strftime(datetime.now(), format=dformat)
    if expiry_time:
        expiry_time_str = datetime.strftime(datetime.now, format=dformat)
    else:
        expiry_time_str = now_str

    times_el = Element('Times')
    ctime_el = Element('CreationTime')
    mtime_el = Element('LastModificationTime')
    atime_el = Element('LastAccessTime')
    etime_el = Element('ExpiryTime')
    expires_el = Element('Expires')
    usage_count_el = Element('UsageCount')
    location_changed_el = Element('LocationChanged')

    ctime_el.text = now_str
    atime_el.text = now_str
    mtime_el.text = now_str
    etime_el.text = expiry_time_str
    location_changed_el.text = now_str
    expires_el.text = str(expires)
    usage_count_el.text = str(0)

    times_el.append(ctime_el)
    times_el.append(mtime_el)
    times_el.append(atime_el)
    times_el.append(etime_el)
    times_el.append(expires_el)
    times_el.append(location_changed_el)

    return times_el

def create_group(etree, group_path):
    # TODO Don't necessarily create the group under the root group
    # root_group = etree.xpath('/KeePassFile/Root/Group')[0]
    parent_path, group_name = os.path.split(group_path)
    parent_group = find_group_by_path(etree, parent_path)
    if parent_group:
        group_el = Element('Group')
        name_el = get_name_element(group_name)
        uuid_el = get_uuid_element(etree)
        group_el.append(uuid_el)
        group_el.append(name_el)
        parent_group.append(group_el)
        return group_el
    else:
        return create_group(etree, parent_path)


def create_entry(etree, group, entry_name, entry_username, entry_password,
                 entry_notes=None, entry_url=None, entry_expires=False,
                 entry_expiration_date=None):
    entry_el = Element('Entry')
    title_el = get_title_element(entry_name)
    uuid_el = get_uuid_element(etree)
    username_el = get_username_element(entry_username)
    password_el = get_password_element(entry_password)
    times_el = get_time_element(entry_expires, entry_expiration_date)
    if entry_url:
        url_el = get_url_element(entry_url)
        entry_el.append(url_el)
    if entry_notes:
        notes_el = get_notes_element(entry_notes)
        entry_el.append(notes_el)
    entry_el.append(title_el)
    entry_el.append(uuid_el)
    entry_el.append(username_el)
    entry_el.append(password_el)
    entry_el.append(times_el)
    group.append(entry_el)
    return entry_el


def write_entry(kdbx_file, kdbx_password, group_destination_name, entry_name,
                entry_username, entry_password, kdbx_keyfile=None):
    logging.info(
        'Atempt to write entry "{}: {}:{}" to {}'.format(
            entry_name, entry_username, entry_password, group_destination_name
        )
    )
    with libkeepass.open(kdbx_file, password=kdbx_password, keyfile=kdbx_keyfile) as kdb:
        et = kdb.tree
        # TODO Paths like FOLDER1/FOLDER2 should be supported
        destination_group = find_group_by_path(et, group_destination_name)
        if not destination_group:
            logging.info(
                'Could not find destination group {}. Create it.'.format(
                    group_destination_name
                )
            )
            destination_group = create_group(et, group_destination_name)
        create_entry(
            et, destination_group, entry_name, entry_username, entry_password
        )
        outstream = open(kdbx_file + 'new.kdbx', 'w+').__enter__()
        kdb.write_to(outstream)


if __name__ == '__main__':
    args = parse_args()
    write_entry(
        kdbx_file=args.database,
        kdbx_password=args.password,
        kdbx_keyfile=args.keyfile,
        group_destination_name=args.destination,
        entry_name=args.entry,
        entry_username=args.entry_username,
        entry_password=args.entry_password
    )