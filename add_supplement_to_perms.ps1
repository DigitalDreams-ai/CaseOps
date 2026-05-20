# PowerShell script to add Supplement_Inquiry__c FLS to permission sets

$permSets = @(
    @{
        name = "Office_Manager.permissionset-meta.xml"
        path = "temp_perm_sets/permissionsets/Office_Manager.permissionset-meta.xml"
        editable = "false"
        insertPoint = "Case.Dispo_Level_3__c"
    },
    @{
        name = "Tier_1_Telephony_Agents_Digital_Agents.permissionset-meta.xml"
        path = "temp_perm_sets/permissionsets/Tier_1_Telephony_Agents_Digital_Agents.permissionset-meta.xml"
        editable = "true"
        insertPoint = "Case.Dispo_Level_1__c"
    },
    @{
        name = "Tier_2_PSR.permissionset-meta.xml"
        path = "temp_perm_sets/permissionsets/Tier_2_PSR.permissionset-meta.xml"
        editable = "true"
        insertPoint = "Case.Dispo_Level_1__c"
    },
    @{
        name = "Case_Read_Access_Customer_Experience.permissionset-meta.xml"
        path = "temp_perm_sets/permissionsets/Case_Read_Access_Customer_Experience.permissionset-meta.xml"
        editable = "false"
        insertPoint = "Case.Dispo_Level_1__c"
    },
    @{
        name = "Case_Read_Edit_Access_Customer_Experience.permissionset-meta.xml"
        path = "temp_perm_sets/permissionsets/Case_Read_Edit_Access_Customer_Experience.permissionset-meta.xml"
        editable = "true"
        insertPoint = "Case.Dispo_Level_1__c"
    }
)

foreach ($ps in $permSets) {
    $filePath = $ps.path
    if (!(Test-Path $filePath)) {
        Write-Host "File not found: $filePath"
        continue
    }

    $content = Get-Content $filePath -Raw

    # Check if Supplement_Inquiry__c already exists
    if ($content -match "Case\.Supplement_Inquiry__c") {
        Write-Host "✓ $($ps.name): Already has Supplement_Inquiry__c"
        continue
    }

    # Find the insertion point (after the insertPoint field)
    $pattern = "(<field>Case\.$($ps.insertPoint -replace '\.__c$', '')\.__c</field>.*?</fieldPermissions>)"
    
    if ($content -match $pattern) {
        $newEntry = @"
    </fieldPermissions>
    <fieldPermissions>
        <editable>$($ps.editable)</editable>
        <field>Case.Supplement_Inquiry__c</field>
        <readable>true</readable>
    <fieldPermissions>
"@
        
        $content = $content -replace $pattern, ($matches[1] + $newEntry)
        Set-Content $filePath $content
        Write-Host "✓ $($ps.name): Added Supplement_Inquiry__c with editable=$($ps.editable)"
    } else {
        Write-Host "✗ $($ps.name): Could not find insertion point"
    }
}
