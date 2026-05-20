<?xml version="1.0" encoding="UTF-8"?>
<Workflow xmlns="http://soap.sforce.com/2006/04/metadata">
    <alerts>
        <fullName>CX_Case_Closed</fullName>
        <description>CX Case Closed</description>
        <protected>false</protected>
        <recipients>
            <field>ContactId</field>
            <type>contactLookup</type>
        </recipients>
        <recipients>
            <field>SuppliedEmail</field>
            <type>email</type>
        </recipients>
        <senderAddress>support@10xhealthsystem.com</senderAddress>
        <senderType>OrgWideEmailAddress</senderType>
        <template>CXEmailTemplates/Closed_Case_Template_1774306958188</template>
    </alerts>
</Workflow>
