Id patientRtId = [
    SELECT Id
    FROM RecordType
    WHERE SobjectType = 'Account'
    AND DeveloperName = 'Patient_Account_Record_Type'
    LIMIT 1
].Id;

Id labsRtId = [
    SELECT Id
    FROM RecordType
    WHERE SobjectType = 'Opportunity'
    AND DeveloperName = 'Lab_Opportunity_Record_Type'
    LIMIT 1
].Id;

Account acct = new Account(
    RecordTypeId = patientRtId,
    LastName = 'CaseOps HEAL-33054 Test',
    Cardone_Ventures_Employee__c = true
);
insert acct;

Opportunity opp = new Opportunity(
    Name = 'CaseOps HEAL-33054 Test Opportunity',
    AccountId = acct.Id,
    RecordTypeId = labsRtId,
    StageName = 'Open',
    CloseDate = Date.today().addDays(7)
);
insert opp;

Opportunity insertedOpp = [
    SELECT Id, Cardone_Ventures_Employee__c
    FROM Opportunity
    WHERE Id = :opp.Id
];
System.debug('HEAL33054_FORMULA_TRUE=' + insertedOpp.Cardone_Ventures_Employee__c);
System.assertEquals(true, insertedOpp.Cardone_Ventures_Employee__c);

acct.Cardone_Ventures_Employee__c = false;
update acct;

Opportunity updatedOpp = [
    SELECT Id, Cardone_Ventures_Employee__c
    FROM Opportunity
    WHERE Id = :opp.Id
];
System.debug('HEAL33054_FORMULA_FALSE=' + updatedOpp.Cardone_Ventures_Employee__c);
System.assertEquals(false, updatedOpp.Cardone_Ventures_Employee__c);

delete opp;
delete acct;
