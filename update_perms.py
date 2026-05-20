#!/usr/bin/env python3
"""Add Supplement_Inquiry__c FLS to permission sets matching Dispo_Level_1__c."""

import xml.etree.ElementTree as ET
import os
import sys
from pathlib import Path

# Register namespace to preserve formatting
ET.register_namespace('', 'http://soap.sforce.com/2006/04/metadata')

def add_supplement_inquiry_fls(perm_set_path):
    """Add Supplement_Inquiry__c FLS matching Dispo_Level_1__c in a permission set."""
    tree = ET.parse(perm_set_path)
    root = tree.getroot()

    ns = {'ps': 'http://soap.sforce.com/2006/04/metadata'}

    # Find all fieldPermissions
    field_perms = root.findall('ps:fieldPermissions', ns) if ns['ps'] in root.tag else root.findall('fieldPermissions')

    dispo_level_index = None
    supplement_exists = False
    dispo_level_editable = None

    # Search for Dispo_Level_1__c and check if Supplement_Inquiry__c exists
    for i, fp in enumerate(field_perms):
        field_elem = fp.find('ps:field', ns) if ns['ps'] in root.tag else fp.find('field')
        if field_elem is not None:
            if field_elem.text == 'Case.Dispo_Level_1__c':
                dispo_level_index = i
                editable_elem = fp.find('ps:editable', ns) if ns['ps'] in root.tag else fp.find('editable')
                if editable_elem is not None:
                    dispo_level_editable = editable_elem.text.lower() == 'true'
            elif field_elem.text == 'Case.Supplement_Inquiry__c':
                supplement_exists = True

    if dispo_level_index is None:
        print(f"  ✗ {perm_set_path.name}: Dispo_Level_1__c not found, skipping")
        return False

    if supplement_exists:
        print(f"  ✓ {perm_set_path.name}: Supplement_Inquiry__c already exists")
        return False

    # Create new fieldPermissions element for Supplement_Inquiry__c
    dispo_fp = field_perms[dispo_level_index]

    # Clone the Dispo_Level_1__c element structure
    new_fp = ET.Element('fieldPermissions')

    editable_elem = ET.SubElement(new_fp, 'editable')
    editable_elem.text = 'true' if dispo_level_editable else 'false'

    field_elem = ET.SubElement(new_fp, 'field')
    field_elem.text = 'Case.Supplement_Inquiry__c'

    readable_elem = ET.SubElement(new_fp, 'readable')
    readable_elem.text = 'true'

    # Insert after Dispo_Level_1__c
    root.insert(list(root).index(dispo_fp) + 1, new_fp)

    # Write back with proper formatting
    tree.write(perm_set_path, encoding='UTF-8', xml_declaration=True)

    # Restore namespace declaration
    with open(perm_set_path, 'r') as f:
        content = f.read()

    if 'xmlns=' not in content:
        content = content.replace('<?xml version=\'1.0\' encoding=\'UTF-8\'?>',
                                '<?xml version=\'1.0\' encoding=\'UTF-8\'?>\n<PermissionSet xmlns="http://soap.sforce.com/2006/04/metadata">')

    with open(perm_set_path, 'w') as f:
        f.write(content)

    print(f"  ✓ {perm_set_path.name}: Added Supplement_Inquiry__c (editable={dispo_level_editable})")
    return True

def main():
    temp_perm_dir = Path('temp_perm_sets/permissionsets')
    force_app_perm_dir = Path('force-app/main/default/permissionsets')

    if not temp_perm_dir.exists():
        print(f"Error: {temp_perm_dir} not found")
        sys.exit(1)

    print("Updating permission sets in temp_perm_sets/...")
    for perm_file in sorted(temp_perm_dir.glob('*.permissionset-meta.xml')):
        add_supplement_inquiry_fls(perm_file)

    print("\nUpdating permission sets in force-app/...")
    for perm_file in sorted(force_app_perm_dir.glob('*.permissionset-meta.xml')):
        add_supplement_inquiry_fls(perm_file)

if __name__ == '__main__':
    main()
